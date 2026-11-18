"""V2EX favourite topics, details and replies to projection tables."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from db import raw
from db.projections._upsert import (
    RebuildResult,
    SkipResponse,
    apply_handler,
    iter_body_responses,
    iter_json_responses,
    json_dumps,
    json_or_null,
    request_payload,
    reset_tables,
    skip_handler_response,
    skip_response,
    upsert,
)
from v2ex.html import is_signin_page, parse_fav_topic_ids
from v2ex.tipped import ThanksEntry, parse_balance_page

FAV_ENDPOINT = 'v2ex.fav.page'
THANKS_ENDPOINT = 'v2ex.balance.page'
TOPIC_ENDPOINT = 'v2ex.topic.detail'
REPLIES_ENDPOINT = 'v2ex.topic.replies.page'

DELETE_ORDER = ('v2ex_reply', 'v2ex_favorite', 'v2ex_thanks', 'v2ex_topic')

_REPLIES_TOPIC_RE = re.compile(r'/topics/(\d+)/replies')


def rebuild(connection: sqlite3.Connection) -> RebuildResult:
    """Rebuild favourites, topic details and reply rows."""
    now = raw.utc_now()
    reset_tables(connection, DELETE_ORDER)
    result = RebuildResult()

    for response, body in iter_body_responses(
        connection,
        FAV_ENDPOINT,
        result=result,
        status_ok_only=True,
    ):
        result.rows += apply_handler(
            FAV_ENDPOINT,
            response,
            _upsert_favorites,
            connection,
            body,
            response['id'],
            now,
        )

    # Balance pages are independent of favourites; replaying them before topic
    # details keeps the fixed endpoint order documented in projection-layer.md.
    for response, body in iter_body_responses(
        connection,
        THANKS_ENDPOINT,
        result=result,
        status_ok_only=True,
    ):
        result.rows += apply_handler(
            THANKS_ENDPOINT,
            response,
            _upsert_thanks,
            connection,
            body,
            response['id'],
            now,
        )

    for response, payload in iter_json_responses(
        connection,
        TOPIC_ENDPOINT,
        result=result,
    ):
        try:
            result.rows += apply_handler(
                TOPIC_ENDPOINT,
                response,
                _upsert_topic,
                connection,
                payload,
                response['id'],
                now,
            )
        except SkipResponse as exc:
            skip_handler_response(result, TOPIC_ENDPOINT, response, str(exc))

    for response, payload in iter_json_responses(
        connection,
        REPLIES_ENDPOINT,
        result=result,
        skip_invalid_json=True,
    ):
        try:
            result.rows += apply_handler(
                REPLIES_ENDPOINT,
                response,
                _upsert_replies,
                connection,
                payload,
                response,
                now,
                result,
            )
        except SkipResponse as exc:
            skip_handler_response(result, REPLIES_ENDPOINT, response, str(exc))

    return result


def _upsert_favorites(
    connection: sqlite3.Connection,
    body: bytes,
    response_id: int,
    now: str,
) -> int:
    rows = 0
    html = body.decode('utf-8', errors='replace')
    if is_signin_page(html):
        raise ValueError('signin page instead of favorites')
    for topic_id in parse_fav_topic_ids(html):
        rows += upsert(
            connection,
            'v2ex_favorite',
            {'topic_id': topic_id},
            {},
            response_id,
            now,
        )
    return rows


def _upsert_thanks(
    connection: sqlite3.Connection,
    body: bytes,
    response_id: int,
    now: str,
) -> int:
    """Project one balance page, including its sent-thanks transactions.

    A signin body must abort the whole rebuild: treating it as an empty page
    would delete every existing thanks row and hide the expired login.
    """
    html = body.decode('utf-8', errors='replace')
    if is_signin_page(html):
        raise ValueError('signin page instead of balance')
    page = parse_balance_page(html)
    if not page.has_table or not page.transaction_keys:
        # 重建侧也要可见：异常页会安静地回放成 0 行，和真正的空历史无法区分。
        reason = '缺少流水表' if not page.has_table else '解析不出任何流水'
        print(f'警告: 余额页响应 id={response_id} {reason}，HTML 结构可能变化')
    rows = 0
    for entry in page.thanks:
        rows += upsert(
            connection,
            'v2ex_thanks',
            {
                'thanked_at': entry.thanked_at,
                'topic_id': entry.topic_id,
                'content_kind': entry.content_kind,
                'member': entry.member,
                'balance': entry.balance,
            },
            {
                'amount': entry.amount,
                'topic_title': entry.topic_title,
                'description': entry.description,
            },
            response_id,
            now,
        )
    return rows


def thanks_page_known(
    connection: sqlite3.Connection,
    entries: list[ThanksEntry],
) -> bool:
    """Return whether every thanks transaction on a page is already stored.

    Callers use this as a pagination stop signal, so an empty page returns
    False: there is no new-transaction evidence, and "all zero entries exist"
    would otherwise stop before the first real page.
    """
    if not entries:
        return False
    for entry in entries:
        row = connection.execute(
            'SELECT 1 FROM v2ex_thanks '
            'WHERE thanked_at = ? AND topic_id = ? AND content_kind = ? '
            'AND member = ? AND balance = ?',
            (
                entry.thanked_at,
                entry.topic_id,
                entry.content_kind,
                entry.member,
                entry.balance,
            ),
        ).fetchone()
        if row is None:
            return False
    return True


def tipped_topic_ids(connection: sqlite3.Connection) -> list[int]:
    """Return deduplicated tipped topic ids, most recently thanked first.

    The exporter scans these after balance paging stops so old topics whose
    details/replies are still incomplete get repaired across runs.
    """
    rows = connection.execute(
        'SELECT topic_id FROM v2ex_thanks '
        'GROUP BY topic_id ORDER BY MAX(thanked_at) DESC, topic_id DESC'
    ).fetchall()
    return [int(row['topic_id']) for row in rows]


def topic_reply_count(
    connection: sqlite3.Connection,
    topic_id: int,
) -> int | None:
    """Return the projected reply count, or None when the topic is unknown."""
    row = connection.execute(
        'SELECT replies FROM v2ex_topic WHERE topic_id = ?',
        (topic_id,),
    ).fetchone()
    return int(row['replies']) if row is not None else None


def replies_complete(
    connection: sqlite3.Connection,
    topic_id: int,
    expected: int,
) -> bool:
    """Return whether the topic has at least ``expected`` projected replies.

    Reply pages are fetched in a loop, so an interrupted run leaves only the
    first pages in raw; the existence of a row cannot prove the thread is whole.
    """
    row = connection.execute(
        'SELECT COUNT(*) AS count FROM v2ex_reply WHERE topic_id = ?',
        (topic_id,),
    ).fetchone()
    return int(row['count']) >= expected


def _upsert_topic(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response_id: int,
    now: str,
) -> int:
    if not isinstance(payload, dict):
        raise SkipResponse('invalid topic payload')
    topic = payload.get('result')
    if topic is None:
        raise SkipResponse('topic result is missing or null')
    if not isinstance(topic, dict):
        raise SkipResponse('invalid topic result')
    return upsert(
        connection,
        'v2ex_topic',
        {'topic_id': topic['id']},
        {
            'title': topic.get('title') or '',
            'content': topic.get('content') or '',
            'syntax': topic.get('syntax') or 0,
            'url': topic.get('url') or '',
            'replies': topic.get('replies') or 0,
            'last_reply_by': topic.get('last_reply_by') or '',
            'created': topic.get('created') or 0,
            'last_modified': topic.get('last_modified') or 0,
            'last_touched': topic.get('last_touched') or 0,
            'member_json': json_or_null(topic.get('member')),
            'node_json': json_or_null(topic.get('node')),
            'supplements_json': json_dumps(topic.get('supplements') or []),
        },
        response_id,
        now,
    )


def _upsert_replies(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response: dict[str, Any],
    now: str,
    result: RebuildResult,
) -> int:
    topic_id = _replies_topic_id(response)
    if not isinstance(payload, dict):
        raise SkipResponse('invalid replies payload')
    replies = payload.get('result')
    if not isinstance(replies, list):
        raise SkipResponse('missing result list')
    rows = 0
    for reply in replies:
        if not isinstance(reply, dict) or 'id' not in reply:
            skip_response(result, REPLIES_ENDPOINT, response, 'reply missing id')
            continue
        rows += upsert(
            connection,
            'v2ex_reply',
            {'reply_id': reply['id']},
            {
                'topic_id': topic_id,
                'content': reply.get('content') or '',
                'content_rendered': reply.get('content_rendered') or '',
                'thanks': reply.get('thanks') or 0,
                'created': reply.get('created') or 0,
                'last_modified': reply.get('last_modified') or 0,
                'member_json': json_or_null(reply.get('member')),
            },
            response['id'],
            now,
        )
    return rows


def _replies_topic_id(response: dict[str, Any]) -> int:
    url = request_payload(response).get('url') or ''
    match = _REPLIES_TOPIC_RE.search(url)
    if match is None:
        raise SkipResponse('cannot determine topic id from request URL')
    return int(match.group(1))
