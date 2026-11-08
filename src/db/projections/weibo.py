"""Weibo liked posts and long text to projection tables."""

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
    skip_response,
    update_aux,
    upsert,
)

LIKES_ENDPOINT = 'weibo.likes.page'
LONGTEXT_ENDPOINT = 'weibo.longtext'

DELETE_ORDER = ('weibo_post',)


def rebuild(connection: sqlite3.Connection) -> RebuildResult:
    """Rebuild liked posts and their long text bodies."""
    now = raw.utc_now()
    reset_tables(connection, DELETE_ORDER)
    result = RebuildResult()

    for response, payload in iter_json_responses(
        connection,
        LIKES_ENDPOINT,
        result=result,
    ):
        result.rows += apply_handler(
            LIKES_ENDPOINT,
            response,
            _upsert_posts,
            connection,
            payload,
            response['id'],
            now,
        )

    for response, payload in iter_json_responses(
        connection,
        LONGTEXT_ENDPOINT,
        result=result,
        skip_invalid_json=True,
    ):
        try:
            result.rows += apply_handler(
                LONGTEXT_ENDPOINT,
                response,
                _update_long_text,
                connection,
                payload,
                response,
                now,
            )
        except SkipResponse as exc:
            skip_response(result, LONGTEXT_ENDPOINT, response, str(exc))

    return result


def _upsert_posts(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response_id: int,
    now: str,
) -> int:
    if payload.get('ok') != 1:
        raise ValueError(f'ok={payload.get("ok")}')
    data = payload.get('data')
    if not data:
        raise ValueError('missing data')

    rows = 0
    for item in data.get('list') or []:
        if item.get('isLongText') and not item.get('mblogid'):
            print(f'长文缺少 mblogid: weibo_post post_id={item["idstr"]}')
        rows += upsert(
            connection,
            'weibo_post',
            {'post_id': item['idstr']},
            {
                'numeric_id': item.get('id'),
                'mid': item.get('mid') or '',
                'mblogid': item.get('mblogid') or None,
                'created_at': item.get('created_at') or '',
                'user_json': json_or_null(item.get('user')),
                'text': item.get('text') or '',
                'text_raw': item.get('text_raw') or '',
                'source': item.get('source') or '',
                'favorited': int(bool(item.get('favorited', False))),
                'pic_num': item.get('pic_num'),
                'pic_ids_json': json_dumps(item.get('pic_ids') or []),
                'pic_infos_json': json_dumps(item.get('pic_infos') or {}),
                'reposts_count': item.get('reposts_count') or 0,
                'comments_count': item.get('comments_count') or 0,
                'attitudes_count': item.get('attitudes_count') or 0,
                'is_long_text': int(bool(item.get('isLongText', False))),
                'region_name': item.get('region_name') or '',
            },
            response_id,
            now,
        )
    return rows


def _update_long_text(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response: dict[str, Any],
    now: str,
) -> int:
    data = payload.get('data') if isinstance(payload, dict) else None
    long_text = data.get('longTextContent') if isinstance(data, dict) else None
    if not isinstance(long_text, str):
        raise SkipResponse('missing long text content')

    params = request_payload(response).get('params') or {}
    mblogid = params.get('id') if isinstance(params, dict) else None
    if not mblogid:
        raise SkipResponse('cannot determine mblogid from request params')
    rows = update_aux(
        connection,
        'weibo_post',
        {'mblogid': mblogid},
        {'long_text': long_text},
        'long_text_response_id',
        response['id'],
        now,
    )
    if rows == 0:
        print(f'辅助数据未命中主行: weibo_post mblogid={mblogid}')
    return rows
