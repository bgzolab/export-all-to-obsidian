"""Client tests: endpoints, encrypted form shape, request metadata and errors."""

from __future__ import annotations

import json

import click
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


class FakeNeteaseClient:
    """Scripted client for exporter flow tests."""

    def __init__(
        self,
        *,
        account=None,
        pages=None,
        details=None,
        song_errors=None,
        recent=None,
        recent_error=None,
        ranks=None,
    ):
        self.account = account or {
            'code': 200,
            'account': {'id': 42},
            'profile': {'userId': 42},
        }
        self.pages = pages or [{'code': 200, 'playlist': [], 'more': False}]
        self.details = details or {}
        self.song_errors = list(song_errors or [])
        self.recent = recent or {'code': 200, 'data': {'list': []}}
        self.recent_error = recent_error
        self.ranks = ranks or {
            'week': {'code': 200, 'weekData': []},
            'all': {'code': 200, 'allData': []},
        }
        self.calls = []

    def get_account(self):
        self.calls.append(('account',))
        if isinstance(self.account, Exception):
            raise self.account
        return self.account

    def list_playlists(self, uid, *, limit, offset):
        self.calls.append(('playlists', uid, limit, offset))
        index = offset // limit
        if index < len(self.pages):
            return self.pages[index]
        return {'code': 200, 'playlist': [], 'more': False}

    def get_playlist_detail(self, playlist_id):
        self.calls.append(('detail', playlist_id))
        value = self.details[playlist_id]
        if isinstance(value, Exception):
            raise value
        return value

    def get_song_details(self, song_ids):
        self.calls.append(('songs', list(song_ids)))
        if self.song_errors:
            error = self.song_errors.pop(0)
            if error is not None:
                raise error
        return {'code': 200, 'songs': []}

    def get_recent_plays(self, *, limit):
        self.calls.append(('recent', limit))
        if self.recent_error is not None:
            raise self.recent_error
        return self.recent

    def get_play_rank(self, uid, kind, *, limit, offset=0):
        self.calls.append(('rank', kind, uid, limit, offset))
        value = self.ranks[kind]
        if isinstance(value, Exception):
            raise value
        return value


def _install_exporter(monkeypatch, client, *, states=None):
    from netease import exporter

    partial = []
    monkeypatch.setattr(exporter, 'NeteaseClient', lambda: client)
    monkeypatch.setattr(exporter, '_playlist_states', lambda: states or {})
    monkeypatch.setattr(exporter, 'mark_run_partial', lambda: partial.append(True))
    return exporter, partial


def _playlist(playlist_id, *, creator=42, track_count=0, update_time=1):
    return {
        'id': playlist_id,
        'name': f'playlist-{playlist_id}',
        'creator': {'userId': creator},
        'trackCount': track_count,
        'trackUpdateTime': update_time,
    }


def _detail(playlist_id, song_ids):
    return {
        'code': 200,
        'playlist': {
            'id': playlist_id,
            'trackIds': [{'id': song_id} for song_id in song_ids],
        },
    }


def test_sync_fetches_own_playlists_details_history_and_ranks(monkeypatch):
    client = FakeNeteaseClient(
        pages=[
            {
                'code': 200,
                'playlist': [
                    _playlist(7, track_count=3, update_time=111),
                    _playlist(99, creator=1),
                ],
                'more': True,
            },
            {
                'code': 200,
                'playlist': [_playlist(8)],
                'more': False,
            },
        ],
        details={7: _detail(7, [1, 2, 3]), 8: _detail(8, [])},
        recent={'code': 200, 'data': {'list': [{'playTime': 1}]}},
    )
    exporter, partial = _install_exporter(monkeypatch, client)

    exporter.sync()

    assert [call[0] for call in client.calls] == [
        'account',
        'playlists',
        'playlists',
        'detail',
        'songs',
        'detail',
        'recent',
        'rank',
        'rank',
    ]
    assert client.calls[1] == ('playlists', 42, 1000, 0)
    assert client.calls[2] == ('playlists', 42, 1000, 1000)
    assert client.calls[3] == ('detail', 7)
    assert client.calls[4] == ('songs', [1, 2, 3])
    assert client.calls[5] == ('detail', 8)
    assert client.calls[6] == ('recent', 100)
    assert client.calls[7] == ('rank', 'week', 42, 1000, 0)
    assert client.calls[8] == ('rank', 'all', 42, 1000, 0)
    assert partial == []


def test_sync_batches_song_details(monkeypatch):
    song_ids = list(range(1201))
    client = FakeNeteaseClient(
        pages=[
            {'code': 200, 'playlist': [_playlist(7, track_count=1201)], 'more': False}
        ],
        details={7: _detail(7, song_ids)},
    )
    exporter, partial = _install_exporter(monkeypatch, client)

    exporter.sync()

    batches = [call[1] for call in client.calls if call[0] == 'songs']
    assert [len(batch) for batch in batches] == [500, 500, 201]
    assert batches[0][0] == 0
    assert batches[-1][-1] == 1200
    assert partial == []


def test_sync_prunes_unchanged_playlists(monkeypatch):
    client = FakeNeteaseClient(
        pages=[
            {
                'code': 200,
                'playlist': [
                    _playlist(7, track_count=3, update_time=111),
                    _playlist(8, track_count=1, update_time=222),
                ],
                'more': False,
            }
        ],
        details={7: _detail(7, [1]), 8: _detail(8, [2])},
    )
    exporter, _ = _install_exporter(monkeypatch, client, states={7: (3, 111)})

    exporter.sync()

    assert ('detail', 7) not in client.calls
    assert ('detail', 8) in client.calls
    assert ('songs', [2]) in client.calls


def test_sync_force_bypasses_pruning(monkeypatch):
    client = FakeNeteaseClient(
        pages=[
            {
                'code': 200,
                'playlist': [_playlist(7, track_count=3, update_time=111)],
                'more': False,
            }
        ],
        details={7: _detail(7, [1])},
    )
    exporter, _ = _install_exporter(monkeypatch, client, states={7: (3, 111)})

    exporter.sync(force=True)

    assert ('detail', 7) in client.calls


def test_sync_playlist_page_error_continues_history_and_ranks(monkeypatch, capsys):
    client = FakeNeteaseClient(
        pages=[{'code': 500, 'message': 'server error'}],
    )
    exporter, partial = _install_exporter(monkeypatch, client)

    exporter.sync()

    assert ('detail',) not in [(call[0],) for call in client.calls]
    assert ('recent', 100) in client.calls
    assert ('rank', 'week', 42, 1000, 0) in client.calls
    assert partial
    assert 'code=500' in capsys.readouterr().out


def test_sync_missing_playlist_list_marks_partial(monkeypatch):
    client = FakeNeteaseClient(pages=[{'code': 200, 'more': False}])
    exporter, partial = _install_exporter(monkeypatch, client)

    exporter.sync()

    assert ('recent', 100) in client.calls
    assert partial


def test_sync_single_playlist_failure_continues(monkeypatch):
    client = FakeNeteaseClient(
        pages=[
            {
                'code': 200,
                'playlist': [_playlist(7), _playlist(8)],
                'more': False,
            }
        ],
        details={
            7: NeteaseClientError('HTTP 500', status_code=500),
            8: _detail(8, [9]),
        },
    )
    exporter, partial = _install_exporter(monkeypatch, client)

    exporter.sync()

    assert ('detail', 7) in client.calls
    assert ('detail', 8) in client.calls
    assert ('songs', [9]) in client.calls
    assert partial
    assert ('recent', 100) in client.calls


def test_sync_missing_track_ids_marks_partial(monkeypatch):
    client = FakeNeteaseClient(
        pages=[{'code': 200, 'playlist': [_playlist(7)], 'more': False}],
        details={7: {'code': 200, 'playlist': {'id': 7}}},
    )
    exporter, partial = _install_exporter(monkeypatch, client)

    exporter.sync()

    assert not [call for call in client.calls if call[0] == 'songs']
    assert partial


def test_sync_rate_limit_stops_remaining_requests(monkeypatch, capsys):
    client = FakeNeteaseClient(
        pages=[{'code': 200, 'playlist': [_playlist(7)], 'more': False}],
        details={7: _detail(7, [1, 2])},
        song_errors=[NeteaseClientError('HTTP 429', status_code=429)],
    )
    exporter, partial = _install_exporter(monkeypatch, client)

    exporter.sync()

    assert not [call for call in client.calls if call[0] in {'recent', 'rank'}]
    assert partial
    assert '限流' in capsys.readouterr().out


def test_sync_recent_failure_does_not_block_ranks(monkeypatch):
    client = FakeNeteaseClient(
        recent_error=NeteaseClientError('HTTP 500', status_code=500),
    )
    exporter, partial = _install_exporter(monkeypatch, client)

    exporter.sync()

    assert ('rank', 'week', 42, 1000, 0) in client.calls
    assert ('rank', 'all', 42, 1000, 0) in client.calls
    assert partial


def test_sync_rank_failure_marks_partial_and_keeps_other_rank(monkeypatch, capsys):
    client = FakeNeteaseClient(
        ranks={
            'week': {'code': 301, 'message': 'need login'},
            'all': {'code': 200, 'allData': []},
        },
    )
    exporter, partial = _install_exporter(monkeypatch, client)

    exporter.sync()

    assert ('rank', 'week', 42, 1000, 0) in client.calls
    assert ('rank', 'all', 42, 1000, 0) in client.calls
    assert partial
    assert 'MUSIC_U' in capsys.readouterr().out


def test_sync_stops_at_playlist_page_cap(monkeypatch, capsys):
    pages = [
        {
            'code': 200,
            'playlist': [_playlist(page_number, update_time=page_number)],
            'more': True,
        }
        for page_number in range(21)
    ]
    client = FakeNeteaseClient(pages=pages)
    states = {page_number: (0, page_number) for page_number in range(21)}
    exporter, partial = _install_exporter(monkeypatch, client, states=states)

    exporter.sync()

    playlist_calls = [call for call in client.calls if call[0] == 'playlists']
    assert len(playlist_calls) == 20
    assert partial
    assert '页上限' in capsys.readouterr().out


def test_sync_falls_back_to_profile_user_id(monkeypatch):
    client = FakeNeteaseClient(
        account={'code': 200, 'account': None, 'profile': {'userId': 77}},
    )
    exporter, _ = _install_exporter(monkeypatch, client)

    exporter.sync()

    assert client.calls[1] == ('playlists', 77, 1000, 0)


def test_sync_uid_mismatch_raises_without_fetching(monkeypatch):
    client = FakeNeteaseClient()
    exporter, partial = _install_exporter(monkeypatch, client)

    with pytest.raises(click.ClickException, match='不一致'):
        exporter.sync(uid=7)

    assert client.calls == [('account',)]
    assert partial == []


def test_sync_empty_account_raises_without_fetching(monkeypatch):
    client = FakeNeteaseClient(
        account={'code': 200, 'account': None, 'profile': None},
    )
    exporter, partial = _install_exporter(monkeypatch, client)

    with pytest.raises(click.ClickException, match='无法识别'):
        exporter.sync()

    assert client.calls == [('account',)]
    assert partial == []


def test_sync_account_http_error_raises_click_exception(monkeypatch):
    client = FakeNeteaseClient(
        account=NeteaseClientError('HTTP 500', status_code=500),
    )
    exporter, _ = _install_exporter(monkeypatch, client)

    with pytest.raises(click.ClickException, match='账号校验失败'):
        exporter.sync()


def test_sync_account_business_error_raises_click_exception(monkeypatch):
    client = FakeNeteaseClient(
        account={'code': 301, 'message': 'need login'},
    )
    exporter, _ = _install_exporter(monkeypatch, client)

    with pytest.raises(click.ClickException, match='code=301'):
        exporter.sync()
