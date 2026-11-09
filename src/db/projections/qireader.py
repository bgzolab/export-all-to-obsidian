"""QiReader read-later entries and article bodies to projection tables."""

from __future__ import annotations

import sqlite3
from typing import Any

from db import raw
from db.projections._upsert import (
    RebuildResult,
    SkipResponse,
    apply_handler,
    iter_json_responses,
    json_dumps,
    json_or_null,
    request_payload,
    reset_tables,
    skip_handler_response,
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

    for response, payload in iter_json_responses(
        connection,
        READLATER_ENDPOINT,
        result=result,
    ):
        result.rows += apply_handler(
            READLATER_ENDPOINT,
            response,
            _upsert_entries,
            connection,
            payload,
            response['id'],
            now,
        )

    for response, payload in iter_json_responses(
        connection,
        ARTICLE_ENDPOINT,
        result=result,
        skip_invalid_json=True,
    ):
        try:
            result.rows += apply_handler(
                ARTICLE_ENDPOINT,
                response,
                _upsert_article,
                connection,
                payload,
                response,
                now,
            )
        except SkipResponse as exc:
            skip_handler_response(result, ARTICLE_ENDPOINT, response, str(exc))

    return result


def _upsert_entries(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response_id: int,
    now: str,
) -> int:
    result = payload.get('result') if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise TypeError('missing result object')
    entries = result.get('entries') or []
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


def known_entry_ids(
    connection: sqlite3.Connection,
    entry_ids: list[str],
) -> set[str]:
    """Return the subset of entry ids already present in the projection."""
    if not entry_ids:
        return set()
    placeholders = ','.join('?' for _ in entry_ids)
    rows = connection.execute(
        f'SELECT entry_id FROM qireader_entry WHERE entry_id IN ({placeholders})',
        entry_ids,
    )
    return {row['entry_id'] for row in rows}


def article_exists(connection: sqlite3.Connection, url: str) -> bool:
    """Return whether the article body is already projected."""
    return (
        connection.execute(
            'SELECT 1 FROM qireader_article WHERE url = ?',
            (url,),
        ).fetchone()
        is not None
    )


def _upsert_article(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response: dict[str, Any],
    now: str,
) -> int:
    content = payload.get('content')
    if not isinstance(content, str):
        raise SkipResponse('missing article content')
    params = request_payload(response).get('params') or {}
    url = params.get('url') if isinstance(params, dict) else None
    if not url:
        raise SkipResponse('cannot determine article URL from request params')
    return upsert(
        connection,
        'qireader_article',
        {'url': url},
        {'content': content},
        response['id'],
        now,
    )
