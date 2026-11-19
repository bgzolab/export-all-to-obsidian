"""NetEase raw responses to projection tables.

Replay order is fixed: playlist metadata, playlist members, song metadata,
then recent plays. Play ranks are intentionally ignored; their raw responses
remain queryable from the raw layer.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from db import raw
from db.projections._upsert import (
    ProjectionError,
    RebuildResult,
    SkipResponse,
    apply_handler,
    iter_json_responses,
    json_dumps,
    json_or_null,
    request_payload,
    reset_tables,
    skip_handler_response,
    skip_response,
    update_aux,
    upsert,
)

PLAYLISTS_ENDPOINT = 'netease.playlists.page'
DETAIL_ENDPOINT = 'netease.playlist.detail'
SONGS_ENDPOINT = 'netease.songs.detail'
RECENT_ENDPOINT = 'netease.play.recent'

# Relations reference playlists and songs, so they are deleted first.
DELETE_ORDER = (
    'netease_play_record',
    'netease_playlist_song',
    'netease_song',
    'netease_playlist',
)

AUTH_FAILURE_CODES = {301, 401, 403}


def playlist_state(
    connection: sqlite3.Connection,
) -> dict[int, tuple[int, int]]:
    """Return pruning state for playlists whose songs are fully projected.

    The exporter compares ``trackCount`` / ``trackUpdateTime`` against this
    map. A playlist without ``detail_response_id`` is absent, and so is one
    that still has member songs without metadata: placeholder rows point at
    the detail response as their provenance, so a failed song batch keeps the
    playlist pending and retries on the next run. Songs that a successful
    batch reported as unavailable are marked ``metadata_missing`` and do not
    block pruning.
    """
    rows = connection.execute(
        'SELECT p.playlist_id, p.track_count, p.track_update_time '
        'FROM netease_playlist AS p '
        'WHERE p.detail_response_id IS NOT NULL '
        'AND NOT EXISTS ('
        'SELECT 1 FROM netease_playlist_song AS ps '
        'LEFT JOIN netease_song AS s ON s.song_id = ps.song_id '
        'LEFT JOIN sync_response AS r ON r.id = s.response_id '
        'WHERE ps.playlist_id = p.playlist_id '
        "AND COALESCE(r.endpoint, '') != ? "
        'AND COALESCE(s.metadata_missing, 0) = 0)',
        (SONGS_ENDPOINT,),
    )
    return {
        int(row['playlist_id']): (
            int(row['track_count']),
            int(row['track_update_time']),
        )
        for row in rows
    }


def rebuild(connection: sqlite3.Connection) -> RebuildResult:
    """Replay all NetEase raw responses in a fixed endpoint order."""
    now = raw.utc_now()
    reset_tables(connection, DELETE_ORDER)
    result = RebuildResult()

    for response, payload in iter_json_responses(
        connection,
        PLAYLISTS_ENDPOINT,
        result=result,
    ):
        try:
            result.rows += apply_handler(
                PLAYLISTS_ENDPOINT,
                response,
                _upsert_playlists,
                connection,
                payload,
                response,
                now,
                result,
            )
        except SkipResponse as exc:
            skip_handler_response(result, PLAYLISTS_ENDPOINT, response, str(exc))

    for response, payload in iter_json_responses(
        connection,
        DETAIL_ENDPOINT,
        result=result,
        skip_invalid_json=True,
    ):
        try:
            result.rows += apply_handler(
                DETAIL_ENDPOINT,
                response,
                _replace_members,
                connection,
                payload,
                response,
                now,
                result,
            )
        except SkipResponse as exc:
            skip_handler_response(result, DETAIL_ENDPOINT, response, str(exc))

    for response, payload in iter_json_responses(
        connection,
        SONGS_ENDPOINT,
        result=result,
        skip_invalid_json=True,
    ):
        try:
            result.rows += apply_handler(
                SONGS_ENDPOINT,
                response,
                _upsert_songs,
                connection,
                payload,
                response,
                now,
                result,
            )
        except SkipResponse as exc:
            skip_handler_response(result, SONGS_ENDPOINT, response, str(exc))

    for response, payload in iter_json_responses(
        connection,
        RECENT_ENDPOINT,
        result=result,
        skip_invalid_json=True,
    ):
        try:
            result.rows += apply_handler(
                RECENT_ENDPOINT,
                response,
                _upsert_recent,
                connection,
                payload,
                response,
                now,
                result,
            )
        except SkipResponse as exc:
            skip_handler_response(result, RECENT_ENDPOINT, response, str(exc))

    return result


def _upsert_playlists(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response: dict[str, Any],
    now: str,
    result: RebuildResult,
) -> int:
    """Upsert own playlists from one list page.

    ``user/playlist`` also returns subscribed playlists. The current account
    uid is not in the body, so it is read from ``request.meta.uid``; a missing
    meta is fatal because keeping all rows would silently import playlists the
    user does not own.
    """
    if not isinstance(payload, dict):
        raise ProjectionError(
            PLAYLISTS_ENDPOINT,
            response['id'],
            'invalid playlist payload',
        )
    code = payload.get('code')
    if code in AUTH_FAILURE_CODES:
        raise ProjectionError(
            PLAYLISTS_ENDPOINT,
            response['id'],
            f'code={code} message={payload.get("message")}',
        )
    if code != 200:
        raise SkipResponse(f'code={code} message={payload.get("message")}')
    if 'playlist' not in payload:
        raise ProjectionError(
            PLAYLISTS_ENDPOINT,
            response['id'],
            'missing playlist',
        )
    page = payload['playlist']
    if page is None:
        return 0
    if not isinstance(page, list):
        raise ProjectionError(
            PLAYLISTS_ENDPOINT,
            response['id'],
            'invalid playlist list',
        )

    uid = _request_uid(response)
    if uid is None:
        raise ProjectionError(
            PLAYLISTS_ENDPOINT,
            response['id'],
            'missing request.meta.uid',
        )

    rows = 0
    for playlist in page:
        if not isinstance(playlist, dict):
            raise ProjectionError(
                PLAYLISTS_ENDPOINT,
                response['id'],
                'invalid playlist item',
            )
        playlist_id = playlist.get('id')
        if not isinstance(playlist_id, int):
            # One dirty list item must not make every later rebuild fail.
            skip_response(result, PLAYLISTS_ENDPOINT, response, 'playlist missing id')
            continue
        creator_id = _creator_id(playlist)
        if creator_id != uid:
            continue
        rows += upsert(
            connection,
            'netease_playlist',
            {'playlist_id': playlist_id},
            {
                'name': playlist.get('name') or '',
                'cover_img_url': playlist.get('coverImgUrl') or '',
                'description': playlist.get('description') or '',
                'creator_id': creator_id,
                'creator_json': json_or_null(playlist.get('creator')),
                'track_count': _integer(playlist.get('trackCount')),
                'play_count': _integer(playlist.get('playCount')),
                'subscribed_count': _integer(playlist.get('subscribedCount')),
                'create_time': _integer(playlist.get('createTime')),
                'update_time': _integer(playlist.get('updateTime')),
                'track_update_time': _integer(playlist.get('trackUpdateTime')),
                'special_type': _integer(playlist.get('specialType')),
                'subscribed': int(bool(playlist.get('subscribed'))),
                'privacy': _integer(playlist.get('privacy')),
                'ordered': int(bool(playlist.get('ordered'))),
                'tags_json': json_dumps(playlist.get('tags') or []),
            },
            response['id'],
            now,
        )
    return rows


def _replace_members(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response: dict[str, Any],
    now: str,
    result: RebuildResult,
) -> int:
    """Replace one playlist's members with the latest ``trackIds`` list.

    A malformed response never deletes existing members: validation happens
    before the delete so an upstream error cannot empty a playlist. A valid
    empty ``trackIds`` list does replace members, which is how an emptied
    playlist is represented. Malformed entries are dropped like the exporter
    drops them, so both sides agree on what was fetched.
    """
    if not isinstance(payload, dict) or payload.get('code') != 200:
        raise SkipResponse('invalid playlist detail payload')
    body = payload.get('playlist')
    if not isinstance(body, dict):
        raise SkipResponse('missing playlist body')
    playlist_id = body.get('id')
    if not isinstance(playlist_id, int):
        raise SkipResponse('missing playlist id')
    track_items = body.get('trackIds')
    if not isinstance(track_items, list):
        raise SkipResponse('missing trackIds')

    members, invalid = _member_ids(track_items)
    if invalid:
        print(
            '投影忽略无效 trackIds 条目: '
            f'{DETAIL_ENDPOINT} (id={response["id"]}): {invalid} 条'
        )
    if track_items and not members:
        raise SkipResponse('no valid trackIds entries')

    exists = connection.execute(
        'SELECT 1 FROM netease_playlist WHERE playlist_id = ?',
        (playlist_id,),
    ).fetchone()
    if exists is None:
        result.aux_missed += 1
        return 0

    connection.execute(
        'DELETE FROM netease_playlist_song WHERE playlist_id = ?',
        (playlist_id,),
    )
    rows = 0
    for position, song_id in members:
        # Placeholder rows satisfy the membership foreign key; DO NOTHING
        # keeps a full song row if song details were already projected.
        connection.execute(
            'INSERT INTO netease_song '
            '(song_id, response_id, db_created_at, db_updated_at) '
            'VALUES (?, ?, ?, ?) ON CONFLICT (song_id) DO NOTHING',
            (song_id, response['id'], now, now),
        )
        rows += upsert(
            connection,
            'netease_playlist_song',
            {'playlist_id': playlist_id, 'song_id': song_id},
            {'position': position},
            response['id'],
            now,
        )
    rows += update_aux(
        connection,
        'netease_playlist',
        {'playlist_id': playlist_id},
        {},
        'detail_response_id',
        response['id'],
        now,
    )
    return rows


def _upsert_songs(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response: dict[str, Any],
    now: str,
    result: RebuildResult,
) -> int:
    if not isinstance(payload, dict) or payload.get('code') != 200:
        raise SkipResponse('invalid song detail payload')
    songs = payload.get('songs')
    if not isinstance(songs, list):
        raise SkipResponse('missing songs list')

    rows = 0
    returned: set[int] = set()
    for song in songs:
        song_id = song.get('id') if isinstance(song, dict) else None
        if not isinstance(song_id, int):
            skip_response(result, SONGS_ENDPOINT, response, 'song missing id')
            continue
        returned.add(song_id)
        rows += upsert(
            connection,
            'netease_song',
            {'song_id': song_id},
            {
                'name': song.get('name') or '',
                'artists_json': json_dumps(_song_artists(song)),
                'album_json': json_dumps(song.get('al') or song.get('album') or {}),
                'duration': _integer(song.get('dt') or song.get('duration')),
                'publish_time': _integer(song.get('publishTime')),
                'fee': _integer(song.get('fee')),
                'mv': _integer(song.get('mv')),
                'alias_json': json_dumps(song.get('alia') or song.get('alias') or []),
                'trans_names_json': json_dumps(
                    song.get('tns') or song.get('transNames') or []
                ),
                'pop': _integer(song.get('pop')),
                'version': _integer(song.get('version')),
                'metadata_missing': 0,
            },
            response['id'],
            now,
        )
    for song_id in _requested_song_ids(response) - returned:
        _mark_song_missing(connection, song_id, now)
    return rows


def _mark_song_missing(
    connection: sqlite3.Connection,
    song_id: int,
    now: str,
) -> None:
    """Record that a successful batch did not return metadata for a song.

    Only placeholder rows are marked, so a hydrated row is never downgraded by
    an unrelated batch that omitted it.
    """
    connection.execute(
        'UPDATE netease_song SET metadata_missing = 1, db_updated_at = ? '
        'WHERE song_id = ? AND metadata_missing = 0 '
        'AND response_id IN (SELECT id FROM sync_response WHERE endpoint = ?)',
        (now, song_id, DETAIL_ENDPOINT),
    )


def _upsert_recent(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response: dict[str, Any],
    now: str,
    result: RebuildResult,
) -> int:
    """Upsert recent plays, keeping one snapshot per (song, play time).

    History is an independent log: it stores a full song snapshot and never
    inserts into ``netease_song``, so rank/history data cannot pollute the
    song library.
    """
    if not isinstance(payload, dict) or payload.get('code') != 200:
        raise SkipResponse('invalid recent play payload')
    data = payload.get('data')
    if not isinstance(data, dict):
        raise SkipResponse('missing recent play data')
    items = data.get('list')
    if not isinstance(items, list):
        raise SkipResponse('missing recent play list')

    rows = 0
    for item in items:
        if not isinstance(item, dict):
            skip_response(result, RECENT_ENDPOINT, response, 'invalid history item')
            continue
        resource_type = item.get('resourceType')
        if resource_type not in (None, 'SONG'):
            skip_response(
                result,
                RECENT_ENDPOINT,
                response,
                f'unsupported resourceType={resource_type}',
            )
            continue
        song = item.get('data')
        song_id = song.get('id') if isinstance(song, dict) else None
        play_time = item.get('playTime')
        if (
            not isinstance(song, dict)
            or not isinstance(song_id, int)
            or not isinstance(play_time, int)
            or play_time <= 0
        ):
            skip_response(result, RECENT_ENDPOINT, response, 'invalid history item')
            continue
        rows += upsert(
            connection,
            'netease_play_record',
            {'song_id': song_id, 'play_time': play_time},
            {
                'resource_type': resource_type or 'SONG',
                'banned': int(bool(item.get('banned'))),
                'device_json': json_or_null(item.get('multiTerminalInfo')),
                'song_json': json_dumps(song),
            },
            response['id'],
            now,
        )
    return rows


def _request_uid(response: dict[str, Any]) -> int | None:
    meta = request_payload(response).get('meta')
    if not isinstance(meta, dict):
        return None
    uid = meta.get('uid')
    return uid if isinstance(uid, int) else None


def _requested_song_ids(response: dict[str, Any]) -> set[int]:
    """Return the ids a song batch asked for, as recorded in request meta."""
    meta = request_payload(response).get('meta')
    if not isinstance(meta, dict):
        return set()
    song_ids = meta.get('song_ids')
    if not isinstance(song_ids, list):
        return set()
    return {song_id for song_id in song_ids if isinstance(song_id, int)}


def _creator_id(playlist: dict[str, Any]) -> int | None:
    creator = playlist.get('creator')
    if isinstance(creator, dict) and isinstance(creator.get('userId'), int):
        return creator['userId']
    user_id = playlist.get('userId')
    return user_id if isinstance(user_id, int) else None


def _integer(value: Any) -> int:
    """Coerce upstream numbers so STRICT INTEGER columns accept the value."""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _member_ids(track_items: list[Any]) -> tuple[list[tuple[int, int]], int]:
    """Return ``(position, song_id)`` pairs and the malformed entry count.

    Duplicate song ids keep the first position.
    """
    members = []
    invalid = 0
    seen = set()
    for position, item in enumerate(track_items):
        song_id = item.get('id') if isinstance(item, dict) else None
        if not isinstance(song_id, int):
            invalid += 1
            continue
        if song_id in seen:
            continue
        seen.add(song_id)
        members.append((position, song_id))
    return members, invalid


def _song_artists(song: dict[str, Any]) -> Any:
    return song.get('ar') or song.get('artists') or []
