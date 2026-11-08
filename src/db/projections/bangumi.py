"""Bangumi raw responses to projection tables."""

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
    update_aux,
    upsert,
)

COLLECTIONS_ENDPOINT = 'bangumi.collections.page'
SUBJECT_ENDPOINT = 'bangumi.subject.detail'
CHARACTERS_ENDPOINT = 'bangumi.subject.characters'

DELETE_ORDER = ('bangumi_collection', 'bangumi_subject')

_CHARACTERS_SUBJECT_RE = re.compile(r'/subjects/(\d+)/characters')


def rebuild(connection: sqlite3.Connection) -> RebuildResult:
    """Rebuild Bangumi collections, subjects and character lists."""
    now = raw.utc_now()
    reset_tables(connection, DELETE_ORDER)
    result = RebuildResult()

    for response, payload in iter_json_responses(
        connection,
        COLLECTIONS_ENDPOINT,
        result=result,
    ):
        result.rows += apply_handler(
            COLLECTIONS_ENDPOINT,
            response,
            _upsert_collections,
            connection,
            payload,
            response['id'],
            now,
        )

    for response, payload in iter_json_responses(
        connection,
        SUBJECT_ENDPOINT,
        result=result,
    ):
        result.rows += apply_handler(
            SUBJECT_ENDPOINT,
            response,
            _upsert_subject,
            connection,
            payload,
            response['id'],
            now,
        )

    for response, payload in iter_json_responses(
        connection,
        CHARACTERS_ENDPOINT,
        result=result,
        skip_invalid_json=True,
    ):
        result.rows += apply_handler(
            CHARACTERS_ENDPOINT,
            response,
            _update_characters,
            connection,
            payload,
            response,
            now,
        )

    return result


def _upsert_collections(
    connection: sqlite3.Connection,
    payload: Any,
    response_id: int,
    now: str,
) -> int:
    rows = 0
    for item in payload['data'] or []:
        values = {
            'collection_id': item.get('id') or None,
            'updated_at': item.get('updated_at'),
            'comment': item.get('comment'),
            'tags_json': json_dumps(item.get('tags', [])),
            'vol_status': item.get('vol_status') or 0,
            'ep_status': item.get('ep_status') or 0,
            'subject_type': item['subject_type'],
            'rate': item.get('rate') or 0,
            'type': item['type'],
            'private': int(bool(item.get('private', False))),
            'subject_json': json_dumps(item['subject']),
        }
        rows += upsert(
            connection,
            'bangumi_collection',
            {'subject_id': item['subject_id']},
            values,
            response_id,
            now,
        )
    return rows


def _upsert_subject(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response_id: int,
    now: str,
) -> int:
    values = {
        'date': payload.get('date'),
        'platform': payload.get('platform'),
        'images_json': json_or_null(payload.get('images')),
        'summary': payload.get('summary') or '',
        'name': payload.get('name') or '',
        'name_cn': payload.get('name_cn') or '',
        'tags_json': json_dumps(payload.get('tags', [])),
        'infobox_json': json_or_null(payload.get('infobox')),
        'rating_json': json_or_null(payload.get('rating')),
        'total_episodes': payload.get('total_episodes') or 0,
        'collection_json': json_or_null(payload.get('collection')),
        'eps': payload.get('eps') or 0,
        'meta_tags_json': json_dumps(payload.get('meta_tags', [])),
        'volumes': payload.get('volumes') or 0,
        'series': int(bool(payload.get('series', False))),
        'locked': int(bool(payload.get('locked', False))),
        'nsfw': int(bool(payload.get('nsfw', False))),
        'type_id': payload.get('type') or 0,
        'redirect': payload.get('redirect'),
    }
    return upsert(
        connection,
        'bangumi_subject',
        {'subject_id': payload['id']},
        values,
        response_id,
        now,
    )


def _update_characters(
    connection: sqlite3.Connection,
    payload: Any,
    response: dict[str, Any],
    now: str,
) -> int:
    url = request_payload(response).get('url') or ''
    match = _CHARACTERS_SUBJECT_RE.search(url)
    if match is None:
        raise ValueError('cannot determine subject id from request URL')
    subject_id = int(match.group(1))
    rows = update_aux(
        connection,
        'bangumi_subject',
        {'subject_id': subject_id},
        {'characters_json': json_dumps(payload)},
        'characters_response_id',
        response['id'],
        now,
    )
    if rows == 0:
        print(f'辅助数据未命中主行: bangumi_subject subject_id={subject_id}')
    return rows
