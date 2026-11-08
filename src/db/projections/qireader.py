"""QiReader read-later entries and article bodies to projection tables."""

from __future__ import annotations

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

READLATER_ENDPOINT = 'qireader.readlater.page'
ARTICLE_ENDPOINT = 'qireader.article'

DELETE_ORDER = ('qireader_article', 'qireader_entry')


def rebuild(connection: sqlite3.Connection) -> RebuildResult:
    """Rebuild read-later entries and their article bodies."""
    now = raw.utc_now()
    reset_tables(connection, DELETE_ORDER)
    result = RebuildResult()

    for response, payload in iter_json_responses(connection, READLATER_ENDPOINT):
        result.responses += 1
        result.rows += apply_handler(
            READLATER_ENDPOINT,
            response,
            _upsert_entries,
            connection,
            payload,
            response['id'],
            now,
        )

    for response, payload in iter_json_responses(connection, ARTICLE_ENDPOINT):
        result.responses += 1
        result.rows += apply_handler(
            ARTICLE_ENDPOINT,
            response,
            _upsert_article,
            connection,
            payload,
            response,
            now,
        )

    return result


def _upsert_entries(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response_id: int,
    now: str,
) -> int:
    entries = payload['result']['entries']
    rows = 0
    for entry in entries:
        rows += upsert(
            connection,
            'qireader_entry',
            {'entry_id': entry['id']},
            {
                'is_saved': int(bool(entry.get('isSaved', False))),
                'source_entry_id': entry.get('sourceEntryId') or '',
                'origin_json': json_or_null(entry.get('origin')),
                'title': entry.get('title') or '',
                'summary': entry.get('summary') or '',
                'url': entry.get('url') or '',
                'published_at': entry.get('publishedAt') or 0,
                'crawled_at': entry.get('crawledAt') or 0,
                'timestamp': entry.get('timestamp') or '',
                'attachments_json': json_dumps(entry.get('attachments') or []),
                'tag_ids_json': json_dumps(entry.get('tagIds') or []),
            },
            response_id,
            now,
        )
    return rows


def _upsert_article(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response: dict[str, Any],
    now: str,
) -> int:
    if response.get('status_code') != 200:
        return 0
    content = payload.get('content')
    if not isinstance(content, str):
        raise TypeError('missing article content')
    params = request_payload(response).get('params') or {}
    url = params.get('url') if isinstance(params, dict) else None
    if not url:
        raise ValueError('cannot determine article URL from request params')
    return upsert(
        connection,
        'qireader_article',
        {'url': url},
        {'content': content},
        response['id'],
        now,
    )
