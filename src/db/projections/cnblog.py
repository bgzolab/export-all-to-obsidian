"""CNBlog bookmarks and post bodies to projection tables."""

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


def post_exists(connection: sqlite3.Connection, source_url: str) -> bool:
    """Return whether the post body is already projected."""
    if not source_url:
        return False
    return (
        connection.execute(
            'SELECT 1 FROM cnblog_post WHERE source_url = ?',
            (source_url,),
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
        'SELECT link_url FROM cnblog_bookmark WHERE link_url LIKE ?',
        (f'%/{post_id}.html',),
    ).fetchall()
    # 多候选说明关联不唯一，宁可留空也不要写一个无法确认的 URL。
    return rows[0]['link_url'] if len(rows) == 1 else ''
