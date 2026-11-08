"""Zhihu collection responses to projection tables."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from db import raw
from db.projections._upsert import (
    RebuildResult,
    apply_handler,
    iter_json_responses,
    json_dumps,
    json_or_null,
    request_payload,
    reset_tables,
    upsert,
)

ENDPOINT = 'zhihu.collection.page'

DELETE_ORDER = ('zhihu_collection_item', 'zhihu_content')

_COLLECTION_URL_RE = re.compile(r'/collections/([^/]+)/items')


def rebuild(connection: sqlite3.Connection) -> RebuildResult:
    """Rebuild Zhihu content and collection membership rows."""
    now = raw.utc_now()
    reset_tables(connection, DELETE_ORDER)
    result = RebuildResult()

    for response, payload in iter_json_responses(
        connection,
        ENDPOINT,
        result=result,
    ):
        result.rows += apply_handler(
            ENDPOINT,
            response,
            _upsert_page,
            connection,
            payload,
            response,
            now,
        )

    return result


def _upsert_page(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response: dict[str, Any],
    now: str,
) -> int:
    if not isinstance(payload, dict):
        raise TypeError('invalid collection payload')
    collection_id = _collection_id(response)
    rows = 0
    for item in payload['data'] or []:
        content = item['content']
        content_id = str(content['id'])
        title, body_html = _title_and_body(content)
        rows += upsert(
            connection,
            'zhihu_content',
            {'content_id': content_id},
            {
                'type': content.get('type') or '',
                'url': content.get('url') or '',
                'title': title,
                'body_html': body_html,
                'content_json': json_dumps(content.get('content')),
                'voteup_count': content.get('voteup_count') or 0,
                'comment_count': content.get('comment_count') or 0,
                'created_time': content.get('created_time') or 0,
                'updated_time': content.get('updated_time') or 0,
                'author_json': json_or_null(content.get('author')),
                'question_json': json_or_null(content.get('question')),
            },
            response['id'],
            now,
        )
        rows += upsert(
            connection,
            'zhihu_collection_item',
            {'collection_id': collection_id, 'content_id': content_id},
            {'created': item.get('created') or ''},
            response['id'],
            now,
        )
    return rows


def _collection_id(response: dict[str, Any]) -> str:
    url = request_payload(response).get('url') or ''
    match = _COLLECTION_URL_RE.search(url)
    if match is None:
        raise ValueError('cannot determine collection id from request URL')
    return match.group(1)


def _title_and_body(content: dict[str, Any]) -> tuple[str, str]:
    raw_content = content.get('content')
    if isinstance(raw_content, list):
        first = raw_content[0] if raw_content else {}
        return first.get('title') or '', first.get('content') or ''
    question = content.get('question') or {}
    title = content.get('title') or question.get('title') or ''
    body = raw_content if isinstance(raw_content, str) else ''
    return title, body
