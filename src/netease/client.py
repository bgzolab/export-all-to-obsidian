"""NetEase weapi client for account, playlists, songs, history and ranks.

All data requests go through ``export_runtime.http`` so an active sync run
records them for projection replay. The account call is deliberately not
recorded: it authenticates the run and is never projected, and the credential
probe runs before the sync run exists.
"""

from __future__ import annotations

import json
from typing import Any

import requests

from app.cookies import get_cookie_header
from export_runtime import http
from netease import api_endpoints
from netease.weapi import weapi_encrypt


class NeteaseClientError(RuntimeError):
    """A NetEase request failed before it produced a usable JSON object.

    ``status_code`` is preserved so the credential probe can tell an expired
    login (301/401/403) from an inconclusive transport failure.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class NeteaseClient:
    """Thin synchronous client; callers interpret ``code`` themselves."""

    def __init__(self) -> None:
        self.cookie = get_cookie_header(('music.163.com',))
        self.csrf_token = _cookie_value(self.cookie, '__csrf')
        self.session = requests.Session()
        self.session.headers.update(
            {
                'Cookie': self.cookie,
                'User-Agent': (
                    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
                ),
                'Referer': 'https://music.163.com/',
                'Origin': 'https://music.163.com',
            }
        )

    def get_account(self) -> dict[str, Any]:
        """Return the account envelope used for uid discovery and logout checks."""
        return self._post(
            api_endpoints.ENDPOINT_ACCOUNT,
            api_endpoints.ACCOUNT_PATH,
            {'csrf_token': self.csrf_token},
            record=False,
        )

    def list_playlists(
        self,
        uid: int,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return one page of the user's own and subscribed playlists."""
        return self._post(
            api_endpoints.ENDPOINT_PLAYLISTS,
            api_endpoints.PLAYLISTS_PATH,
            {
                'uid': uid,
                'limit': limit,
                'offset': offset,
                'csrf_token': self.csrf_token,
            },
            request_meta={'uid': uid},
        )

    def get_playlist_detail(self, playlist_id: int) -> dict[str, Any]:
        """Return playlist metadata plus the complete ``trackIds`` list.

        ``n=1000`` / ``s=8`` keep the detail response from trimming track ids;
        ``playlist.tracks`` still only carries a handful of full song objects.
        """
        return self._post(
            api_endpoints.ENDPOINT_PLAYLIST_DETAIL,
            api_endpoints.PLAYLIST_DETAIL_PATH,
            {'id': playlist_id, 'n': 1000, 's': 8, 'csrf_token': self.csrf_token},
        )

    def get_song_details(self, song_ids: list[int]) -> dict[str, Any]:
        """Return full song objects for one batch of ids."""
        payload = {
            'c': json.dumps([{'id': song_id} for song_id in song_ids]),
            'csrf_token': self.csrf_token,
        }
        return self._post(
            api_endpoints.ENDPOINT_SONGS_DETAIL,
            api_endpoints.SONG_DETAIL_PATH,
            payload,
        )

    def get_recent_plays(self, *, limit: int = 100) -> dict[str, Any]:
        """Return the rolling recent-play window (no offset or cursor)."""
        return self._post(
            api_endpoints.ENDPOINT_PLAY_RECENT,
            api_endpoints.RECENT_PLAYS_PATH,
            {'limit': limit, 'csrf_token': self.csrf_token},
        )

    def get_play_rank(
        self,
        uid: int,
        kind: str,
        *,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return the all-time or weekly play rank for one user."""
        if kind not in api_endpoints.PLAY_RANK_TYPES:
            raise ValueError(f'Unsupported play rank kind: {kind}')
        endpoint = {
            'week': api_endpoints.ENDPOINT_PLAY_RANK_WEEK,
            'all': api_endpoints.ENDPOINT_PLAY_RANK_ALL,
        }[kind]
        payload = {
            'uid': uid,
            'type': api_endpoints.PLAY_RANK_TYPES[kind],
            'limit': limit,
            'offset': offset,
            'csrf_token': self.csrf_token,
        }
        return self._post(endpoint, api_endpoints.PLAY_RANK_PATH, payload)

    def _post(
        self,
        endpoint: str,
        path: str,
        payload: dict[str, Any],
        *,
        record: bool = True,
        request_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = weapi_encrypt(payload)
        url = api_endpoints.BASE_URL + path
        try:
            if record:
                response = http.post(
                    self.session,
                    url,
                    endpoint=endpoint,
                    data=data,
                    request_meta=request_meta,
                    timeout=30,
                )
            else:
                response = self.session.post(url, data=data, timeout=30)
        except requests.RequestException as exc:
            raise NeteaseClientError(f'请求失败: {exc}') from exc

        if response.status_code != 200:
            raise NeteaseClientError(
                f'HTTP {response.status_code}',
                status_code=response.status_code,
            )
        try:
            result = response.json()
        except (ValueError, TypeError, AttributeError) as exc:
            raise NeteaseClientError(
                f'响应解析失败: {exc}',
                status_code=200,
            ) from exc
        if not isinstance(result, dict):
            raise NeteaseClientError('响应解析失败: 非 JSON 对象', status_code=200)
        return result


def _cookie_value(header: str, name: str) -> str:
    """Return one cookie value from a Cookie header, or an empty string."""
    for part in header.split(';'):
        key, separator, value = part.strip().partition('=')
        if separator and key == name:
            return value
    return ''
