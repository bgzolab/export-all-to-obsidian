"""CNBlog bookmarks and post bodies to projection tables."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Collection
from typing import Any

from cnblog.urls import post_id_from_url
from db import raw
from db.projections._upsert import (
    RebuildResult,
    SkipResponse,
    apply_handler,
    iter_body_responses,
    iter_json_responses,
    json_dumps,
    request_payload,
    reset_tables,
    skip_handler_response,
    upsert,
)

BOOKMARKS_ENDPOINT = 'cnblog.bookmarks.page'
POST_ENDPOINT = 'cnblog.post.body'

DELETE_ORDER = ('cnblog_post', 'cnblog_bookmark')

_POST_URL_RE = re.compile(r'/blogposts/(\d+)/body')


def rebuild(connection: sqlite3.Connection) -> RebuildResult:
    """Rebuild bookmarks and their post bodies."""
    now = raw.utc_now()
    reset_tables(connection, DELETE_ORDER)
    result = RebuildResult()

    for response, payload in iter_json_responses(
        connection,
        BOOKMARKS_ENDPOINT,
        result=result,
    ):
        result.rows += apply_handler(
            BOOKMARKS_ENDPOINT,
            response,
            _upsert_bookmarks,
            connection,
            payload,
            response['id'],
            now,
        )

    for response, body in iter_body_responses(
        connection,
        POST_ENDPOINT,
        result=result,
        status_ok_only=True,
    ):
        try:
            result.rows += apply_handler(
                POST_ENDPOINT,
                response,
                _upsert_post,
                connection,
                body,
                response,
                now,
            )
        except SkipResponse as exc:
            skip_handler_response(result, POST_ENDPOINT, response, str(exc))

    return result


def _upsert_bookmarks(
    connection: sqlite3.Connection,
    payload: Any,
    response_id: int,
    now: str,
) -> int:
    if payload is None:
        raise ValueError('missing bookmark payload')
    if not isinstance(payload, (list, dict)):
        raise TypeError('invalid bookmark payload')
    items = payload if isinstance(payload, list) else [payload]
    rows = 0
    for item in items:
        rows += upsert(
            connection,
            'cnblog_bookmark',
            {'wz_link_id': item['WzLinkId']},
            {
                'title': item.get('Title') or '',
                'link_url': item.get('LinkUrl') or '',
                'summary': item.get('Summary') or '',
                'tags_json': json_dumps(item.get('Tags') or []),
                'date_added': item.get('DateAdded'),
                'from_cnblogs': int(bool(item.get('FromCNBlogs', False))),
            },
            response_id,
            now,
        )
    return rows


def post_pending_count(
    connection: sqlite3.Connection,
    seen_wz_link_ids: Collection[int] = (),
) -> int:
    """Return fetchable CNBlog bookmarks whose post body is still missing."""
    post_ids = {
        row['post_id'] for row in connection.execute('SELECT post_id FROM cnblog_post')
    }
    missing = 0
    rows = connection.execute(
        'SELECT wz_link_id, link_url FROM cnblog_bookmark '
        "WHERE from_cnblogs = 1 AND link_url <> ''",
    )
    for row in rows:
        if row['wz_link_id'] in seen_wz_link_ids:
            continue
        post_id = post_id_from_url(row['link_url'])
        # 无法解析 ID 的 URL 发不出有效请求，不计入 pending。
        if post_id is not None and post_id not in post_ids:
            missing += 1
    return missing


def known_bookmark_ids(
    connection: sqlite3.Connection,
    wz_link_ids: list[int],
) -> set[int]:
    """Return the subset of bookmark ids already present in the projection."""
    if not wz_link_ids:
        return set()
    placeholders = ','.join('?' for _ in wz_link_ids)
    rows = connection.execute(
        f'SELECT wz_link_id FROM cnblog_bookmark WHERE wz_link_id IN ({placeholders})',
        wz_link_ids,
    )
    return {row['wz_link_id'] for row in rows}


def post_exists(connection: sqlite3.Connection, url: str) -> bool:
    """Return whether the post body is already projected."""
    post_id = post_id_from_url(url)
    if post_id is None:
        return False
    return (
        connection.execute(
            'SELECT 1 FROM cnblog_post WHERE post_id = ?',
            (post_id,),
        ).fetchone()
        is not None
    )


def _upsert_post(
    connection: sqlite3.Connection,
    body: bytes,
    response: dict[str, Any],
    now: str,
) -> int:
    url = request_payload(response).get('url') or ''
    match = _POST_URL_RE.search(url)
    if match is None:
        raise SkipResponse('cannot determine post id from request URL')
    post_id = int(match.group(1))
    return upsert(
        connection,
        'cnblog_post',
        {'post_id': post_id},
        {
            'source_url': _source_url(connection, post_id),
            'body': body.decode('utf-8', errors='replace'),
        },
        response['id'],
        now,
    )


def _source_url(connection: sqlite3.Connection, post_id: int) -> str:
    rows = connection.execute(
        'SELECT DISTINCT link_url FROM cnblog_bookmark',
    ).fetchall()
    matches = [
        row['link_url'] for row in rows if post_id_from_url(row['link_url']) == post_id
    ]
    # 多候选说明关联不唯一，宁可留空也不要写一个无法确认的 URL。
    return matches[0] if len(matches) == 1 else ''
