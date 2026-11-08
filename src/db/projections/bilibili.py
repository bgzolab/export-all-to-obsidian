"""Bilibili favourite list responses to projection tables."""

from __future__ import annotations

import sqlite3
from typing import Any

from db import raw
from db.projections._upsert import (
    RebuildResult,
    apply_handler,
    iter_json_responses,
    json_or_null,
    reset_tables,
    upsert,
)

ENDPOINT = 'bilibili.favlist.page'

DELETE_ORDER = ('bilibili_fav_item', 'bilibili_media', 'bilibili_fav')


def rebuild(connection: sqlite3.Connection) -> RebuildResult:
    """Rebuild favourite folders, videos and their membership rows."""
    now = raw.utc_now()
    reset_tables(connection, DELETE_ORDER)
    result = RebuildResult()

    for response, payload in iter_json_responses(connection, ENDPOINT):
        result.responses += 1
        result.rows += apply_handler(
            ENDPOINT,
            response,
            _upsert_page,
            connection,
            payload,
            response['id'],
            now,
        )

    return result


def _upsert_page(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response_id: int,
    now: str,
) -> int:
    if payload.get('code') != 0:
        raise ValueError(
            f'code={payload.get("code")} message={payload.get("message")}',
        )
    data = payload.get('data')
    if not data:
        raise ValueError('missing data')
    info = data.get('info')
    if not info:
        raise ValueError('missing data.info')

    fav_id = info['id']
    rows = upsert(
        connection,
        'bilibili_fav',
        {'fav_id': fav_id},
        {
            'fid': info['fid'],
            'mid': info['mid'],
            'attr': info.get('attr') or 0,
            'title': info.get('title') or '',
            'cover': info.get('cover') or '',
            'upper_json': json_or_null(info.get('upper')),
            'cover_type': info.get('cover_type') or 0,
            'cnt_info_json': json_or_null(info.get('cnt_info')),
            'type': info.get('type') or 0,
            'intro': info.get('intro') or '',
            'ctime': info.get('ctime') or 0,
            'mtime': info.get('mtime') or 0,
            'state': info.get('state') or 0,
            'fav_state': info.get('fav_state') or 0,
            'like_state': info.get('like_state') or 0,
            'media_count': info.get('media_count') or 0,
            'is_top': int(bool(info.get('is_top', False))),
        },
        response_id,
        now,
    )

    for media in data.get('medias') or []:
        media_id = media['id']
        rows += _upsert_media(connection, media, response_id, now)
        rows += upsert(
            connection,
            'bilibili_fav_item',
            {'fav_id': fav_id, 'media_id': media_id},
            {'fav_time': media.get('fav_time') or 0},
            response_id,
            now,
        )
    return rows


def _upsert_media(
    connection: sqlite3.Connection,
    media: dict[str, Any],
    response_id: int,
    now: str,
) -> int:
    return upsert(
        connection,
        'bilibili_media',
        {'media_id': media['id']},
        {
            'type': media.get('type') or 0,
            'title': media.get('title') or '',
            'cover': media.get('cover') or '',
            'intro': media.get('intro') or '',
            'page': media.get('page') or 0,
            'duration': media.get('duration') or 0,
            'upper_json': json_or_null(media.get('upper')),
            'attr': media.get('attr') or 0,
            'cnt_info_json': json_or_null(media.get('cnt_info')),
            'link': media.get('link') or '',
            'ctime': media.get('ctime') or 0,
            'pubtime': media.get('pubtime') or 0,
            'bv_id': media.get('bv_id') or '',
            'bvid': media.get('bvid') or '',
            'ugc_json': json_or_null(media.get('ugc')),
            'media_list_link': media.get('media_list_link') or '',
            'season_json': json_or_null(media.get('season')),
            'ogv_json': json_or_null(media.get('ogv')),
        },
        response_id,
        now,
    )
