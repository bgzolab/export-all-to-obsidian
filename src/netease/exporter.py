"""NetEase sync orchestration.

The flow fetches the logged-in account, its own playlists, playlist members,
song metadata, the recent-play window and both play ranks. Projection replay
happens afterwards in ``run_action``; this module only fetches raw responses
and marks the run partial when a resource is incomplete.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import click

from app.context import mark_run_partial
from netease.client import NeteaseClient, NeteaseClientError

PLAYLIST_PAGE_SIZE = 1000
MAX_PLAYLIST_PAGES = 20
SONG_DETAIL_BATCH_SIZE = 500
RECENT_PLAY_LIMIT = 100
RANK_LIMIT = 1000


class _RateLimited(Exception):
    """HTTP 429: stop the run so the next invocation can refill the gap."""


def sync(uid: int | None = None, force: bool = False) -> None:
    """Fetch all NetEase data for the logged-in account into the raw layer."""
    client = NeteaseClient()
    account = _load_account(client)
    actual_uid = _account_uid(account)
    if actual_uid is None:
        raise click.ClickException(
            '无法识别网易云账号 uid，请重新登录 music.163.com 并导出 cookies.txt'
        )
    if uid is not None and uid != actual_uid:
        raise click.ClickException(
            f'--uid {uid} 与当前登录账号 {actual_uid} 不一致，拒绝执行'
        )

    # The projection reflects the previous rebuild; a new playlist or a failed
    # detail fetch is absent or has a NULL detail_response_id and gets fetched.
    states = {} if force else _playlist_states()
    try:
        own_playlists = _fetch_own_playlists(client, actual_uid)
        _sync_playlist_details(client, own_playlists, states, force)
        _fetch_recent_plays(client)
        _fetch_play_ranks(client, actual_uid)
    except _RateLimited as exc:
        mark_run_partial()
        print(f'触发网易云限流，停止本轮抓取: {exc}')


def _load_account(client: NeteaseClient) -> dict[str, Any]:
    try:
        payload = client.get_account()
    except NeteaseClientError as exc:
        raise click.ClickException(f'网易云账号校验失败: {exc}') from exc
    if payload.get('code') != 200:
        raise click.ClickException(
            '网易云账号校验失败: '
            f'code={payload.get("code")} {payload.get("message") or ""}'.rstrip()
        )
    return payload


def _account_uid(payload: dict[str, Any]) -> int | None:
    account = payload.get('account')
    if isinstance(account, dict) and isinstance(account.get('id'), int):
        return account['id']
    profile = payload.get('profile')
    if isinstance(profile, dict) and isinstance(profile.get('userId'), int):
        return profile['userId']
    return None


def _playlist_states() -> dict[int, tuple[int, int]]:
    """Return pruning state from the previous projection rebuild.

    Imported lazily so client/exporter tests do not need the projection module
    or a migrated database.
    """
    from app.context import get_database
    from db.projections.netease import playlist_state

    return playlist_state(get_database())


def _fetch_own_playlists(client: NeteaseClient, uid: int) -> list[dict[str, Any]]:
    """Collect playlist metadata for playlists created by ``uid``.

    Upstream returns subscribed playlists in the same list, so the creator id
    filter happens here and again in the projection.
    """
    playlists: list[dict[str, Any]] = []
    for page_number in range(MAX_PLAYLIST_PAGES):
        offset = page_number * PLAYLIST_PAGE_SIZE
        payload = _request(
            '歌单列表',
            lambda offset=offset: client.list_playlists(
                uid,
                limit=PLAYLIST_PAGE_SIZE,
                offset=offset,
            ),
        )
        if payload is None or not _check_code(payload, '歌单列表'):
            return playlists

        if 'playlist' not in payload:
            mark_run_partial()
            print('歌单列表响应缺少 playlist 字段，停止歌单抓取')
            return playlists
        page = payload['playlist']
        if page is None:
            page = []
        if not isinstance(page, list):
            mark_run_partial()
            print('歌单列表响应缺少 playlist 列表，停止歌单抓取')
            return playlists

        playlists.extend(
            playlist
            for playlist in page
            if isinstance(playlist, dict) and _creator_id(playlist) == uid
        )

        if not payload.get('more') or not page:
            return playlists

    mark_run_partial()
    print(
        f'歌单列表达到 {MAX_PLAYLIST_PAGES} 页上限，剩余歌单留待下一轮',
    )
    return playlists


def _sync_playlist_details(
    client: NeteaseClient,
    playlists: list[dict[str, Any]],
    states: dict[int, tuple[int, int]],
    force: bool,
) -> None:
    for playlist in playlists:
        playlist_id = playlist.get('id')
        if not isinstance(playlist_id, int):
            mark_run_partial()
            print('歌单缺少 id，跳过该歌单')
            continue
        if not force and _unchanged(playlist, states):
            continue

        payload = _request(
            f'歌单详情 {playlist_id}',
            lambda playlist_id=playlist_id: client.get_playlist_detail(playlist_id),
        )
        if payload is None or not _check_code(payload, f'歌单详情 {playlist_id}'):
            continue

        body = payload.get('playlist')
        if not isinstance(body, dict):
            mark_run_partial()
            print(f'歌单详情 {playlist_id} 缺少 playlist 对象，跳过')
            continue
        track_items = body.get('trackIds')
        if not isinstance(track_items, list):
            # Missing trackIds must not be treated as an empty playlist; the
            # projection keeps the previous members in that case.
            mark_run_partial()
            print(f'歌单详情 {playlist_id} 缺少 trackIds，跳过')
            continue

        song_ids = _track_ids(track_items)
        for batch in _chunks(song_ids, SONG_DETAIL_BATCH_SIZE):
            songs = _request(
                f'歌曲详情 {playlist_id} ({batch[0]}-{batch[-1]})',
                lambda batch=batch: client.get_song_details(batch),
            )
            if songs is not None:
                _check_code(songs, f'歌曲详情 {playlist_id}')


def _fetch_recent_plays(client: NeteaseClient) -> None:
    payload = _request(
        '最近播放',
        lambda: client.get_recent_plays(limit=RECENT_PLAY_LIMIT),
    )
    if payload is not None:
        _check_code(payload, '最近播放')


def _fetch_play_ranks(client: NeteaseClient, uid: int) -> None:
    for kind, label in (('week', '周榜'), ('all', '总榜')):
        payload = _request(
            label,
            lambda kind=kind: client.get_play_rank(
                uid,
                kind,
                limit=RANK_LIMIT,
            ),
        )
        if payload is not None:
            _check_code(payload, label)


def _request[T](label: str, call: Callable[[], T]) -> T | None:
    """Run one request, marking partial on failure.

    A 429 aborts the whole run because every later request would likely fail
    too; other failures only cost the current resource.
    """
    try:
        return call()
    except NeteaseClientError as exc:
        if exc.status_code == 429:
            raise _RateLimited(f'{label}: {exc}') from exc
        mark_run_partial()
        print(f'{label}失败: {exc}')
        return None


def _check_code(payload: dict[str, Any], label: str) -> bool:
    code = payload.get('code')
    if code == 200:
        return True
    mark_run_partial()
    message = payload.get('message') or ''
    print(f'{label}失败: code={code} {message}'.rstrip())
    if code in {301, 401, 403}:
        print('MUSIC_U 可能已失效，请重新导出 cookies.txt')
    return False


def _creator_id(playlist: dict[str, Any]) -> int | None:
    creator = playlist.get('creator')
    if isinstance(creator, dict) and creator.get('userId') is not None:
        return creator['userId']
    user_id = playlist.get('userId')
    return user_id if isinstance(user_id, int) else None


def _unchanged(playlist: dict[str, Any], states: dict[int, tuple[int, int]]) -> bool:
    """Return whether a playlist's metadata matches its last detail fetch."""
    playlist_id = playlist.get('id')
    track_count = playlist.get('trackCount')
    track_update_time = playlist.get('trackUpdateTime')
    if (
        not isinstance(playlist_id, int)
        or not isinstance(track_count, int)
        or not isinstance(track_update_time, int)
    ):
        return False
    return states.get(playlist_id) == (track_count, track_update_time)


def _track_ids(track_items: list[Any]) -> list[int]:
    """Extract valid song ids from ``trackIds``, dropping malformed entries."""
    ids = []
    for item in track_items:
        if isinstance(item, dict) and isinstance(item.get('id'), int):
            ids.append(item['id'])
    return ids


def _chunks(values: list[int], size: int) -> Iterator[list[int]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]
