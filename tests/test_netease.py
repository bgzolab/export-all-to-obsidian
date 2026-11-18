"""Client tests: endpoints, encrypted form shape, request metadata and errors."""

from __future__ import annotations

import json

import pytest
import requests

from netease import api_endpoints
from netease import client as netease_client
from netease.client import NeteaseClient, NeteaseClientError


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, json_error=None):
        self._payload = payload
        self.status_code = status_code
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        netease_client,
        'get_cookie_header',
        lambda domains: 'MUSIC_U=secret; __csrf=csrf-token',
    )
    return NeteaseClient()


def _patch_post(monkeypatch, payload, calls, *, status_code=200, json_error=None):
    def fake_encrypt(payload_, secret=None):
        calls.append({'payload': payload_})
        return {'params': 'encrypted-params', 'encSecKey': 'encrypted-key'}

    def fake_post(
        session,
        url,
        *,
        endpoint,
        data=None,
        request_meta=None,
        **kwargs,
    ):
        calls[-1].update(
            url=url,
            endpoint=endpoint,
            data=data,
            meta=request_meta,
            kwargs=kwargs,
        )
        return FakeResponse(payload, status_code=status_code, json_error=json_error)

    monkeypatch.setattr(netease_client, 'weapi_encrypt', fake_encrypt)
    monkeypatch.setattr(netease_client.http, 'post', fake_post)


def test_client_reads_csrf_cookie(client):
    assert client.csrf_token == 'csrf-token'
    assert 'MUSIC_U=secret' in client.session.headers['Cookie']


def test_account_uses_session_post_and_skips_raw(client, monkeypatch):
    calls = []

    def fake_session_post(url, data=None, timeout=None):
        calls.append({'url': url, 'data': data, 'timeout': timeout})
        return FakeResponse({'code': 200, 'account': {'id': 42}})

    monkeypatch.setattr(client.session, 'post', fake_session_post)
    monkeypatch.setattr(
        netease_client.http,
        'post',
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError('account must not be recorded')
        ),
    )

    payload = client.get_account()

    assert payload['account'] == {'id': 42}
    assert calls[0]['url'] == api_endpoints.BASE_URL + api_endpoints.ACCOUNT_PATH
    assert set(calls[0]['data']) == {'params', 'encSecKey'}
    assert calls[0]['timeout'] == 30


def test_list_playlists_payload_endpoint_and_meta(client, monkeypatch):
    calls = []
    _patch_post(monkeypatch, {'code': 200, 'playlist': [], 'more': False}, calls)

    assert client.list_playlists(42, limit=1000, offset=2000) == {
        'code': 200,
        'playlist': [],
        'more': False,
    }
    assert calls[0]['url'] == api_endpoints.BASE_URL + api_endpoints.PLAYLISTS_PATH
    assert calls[0]['endpoint'] == 'netease.playlists.page'
    assert calls[0]['payload'] == {
        'uid': 42,
        'limit': 1000,
        'offset': 2000,
        'csrf_token': 'csrf-token',
    }
    assert calls[0]['data'] == {
        'params': 'encrypted-params',
        'encSecKey': 'encrypted-key',
    }
    assert calls[0]['meta'] == {'uid': 42}


def test_playlist_detail_payload(client, monkeypatch):
    calls = []
    _patch_post(monkeypatch, {'code': 200, 'playlist': {'id': 7}}, calls)

    client.get_playlist_detail(7)

    assert calls[0]['url'] == (
        api_endpoints.BASE_URL + api_endpoints.PLAYLIST_DETAIL_PATH
    )
    assert calls[0]['endpoint'] == 'netease.playlist.detail'
    assert calls[0]['payload'] == {
        'id': 7,
        'n': 1000,
        's': 8,
        'csrf_token': 'csrf-token',
    }
    assert calls[0]['meta'] is None


def test_song_details_serialize_ids_as_json(client, monkeypatch):
    calls = []
    _patch_post(monkeypatch, {'code': 200, 'songs': []}, calls)

    client.get_song_details([1, 2, 3])

    assert calls[0]['url'] == api_endpoints.BASE_URL + api_endpoints.SONG_DETAIL_PATH
    assert calls[0]['endpoint'] == 'netease.songs.detail'
    assert json.loads(calls[0]['payload']['c']) == [{'id': 1}, {'id': 2}, {'id': 3}]


def test_recent_plays_payload(client, monkeypatch):
    calls = []
    _patch_post(monkeypatch, {'code': 200, 'data': {'list': []}}, calls)

    client.get_recent_plays(limit=100)

    assert calls[0]['url'] == api_endpoints.BASE_URL + api_endpoints.RECENT_PLAYS_PATH
    assert calls[0]['endpoint'] == 'netease.play.recent'
    assert calls[0]['payload'] == {'limit': 100, 'csrf_token': 'csrf-token'}


@pytest.mark.parametrize(
    'kind,rank_type,endpoint',
    [
        ('week', 1, 'netease.play.rank.week'),
        ('all', 0, 'netease.play.rank.all'),
    ],
)
def test_play_rank_payload(kind, rank_type, endpoint, client, monkeypatch):
    calls = []
    _patch_post(monkeypatch, {'code': 200}, calls)

    client.get_play_rank(42, kind, limit=1000, offset=0)

    assert calls[0]['url'] == api_endpoints.BASE_URL + api_endpoints.PLAY_RANK_PATH
    assert calls[0]['endpoint'] == endpoint
    assert calls[0]['payload'] == {
        'uid': 42,
        'type': rank_type,
        'limit': 1000,
        'offset': 0,
        'csrf_token': 'csrf-token',
    }


def test_play_rank_rejects_unknown_kind(client):
    with pytest.raises(ValueError, match='Unsupported play rank kind'):
        client.get_play_rank(42, 'month')


def test_non_200_raises_with_status(client, monkeypatch):
    calls = []
    _patch_post(monkeypatch, {}, calls, status_code=429)

    with pytest.raises(NeteaseClientError, match='HTTP 429') as exc_info:
        client.list_playlists(42)

    assert exc_info.value.status_code == 429


def test_invalid_json_raises(client, monkeypatch):
    calls = []
    _patch_post(
        monkeypatch,
        None,
        calls,
        json_error=json.JSONDecodeError('Expecting value', 'doc', 0),
    )

    with pytest.raises(NeteaseClientError, match='响应解析失败'):
        client.list_playlists(42)


def test_non_object_json_raises(client, monkeypatch):
    calls = []
    _patch_post(monkeypatch, [1, 2, 3], calls)

    with pytest.raises(NeteaseClientError, match='非 JSON 对象'):
        client.list_playlists(42)


def test_transport_error_is_wrapped(client, monkeypatch):
    calls = []
    _patch_post(monkeypatch, {}, calls)

    def fail(*args, **kwargs):
        raise requests.Timeout('timed out')

    monkeypatch.setattr(netease_client.http, 'post', fail)

    with pytest.raises(NeteaseClientError, match='请求失败') as exc_info:
        client.list_playlists(42)

    assert exc_info.value.status_code is None
