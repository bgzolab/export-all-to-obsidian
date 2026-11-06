from __future__ import annotations

import json

import pytest
import requests

from db.connection import connect
from db.raw import start_run
from export_runtime import http


class FakeResponse:
    def __init__(self, status_code=200, content=b'{"ok": true}'):
        self.status_code = status_code
        self.content = content


class FakeSession:
    def __init__(self, response=None, error=None):
        self.headers = {
            'Cookie': 'SUB=secret',
            'Authorization': 'Bearer secret',
            'User-Agent': 'eto-test',
        }
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self.error is not None:
            raise self.error
        return self.response


def test_get_records_body_and_redacts_auth_headers(tmp_path):
    connection = connect(tmp_path / 'eto.db')
    run_id = start_run(connection, 'github', 'stars', 'octocat')
    session = FakeSession(FakeResponse(200, b'{"items": []}'))

    response = http.get(
        session,
        'https://api.github.com/user/starred',
        endpoint='github.stars.list',
        database=connection,
        run_id=run_id,
        params={'page': 1},
    )

    assert response.status_code == 200
    row = connection.execute('SELECT * FROM sync_response').fetchone()
    request_info = json.loads(row['request'])
    assert request_info['method'] == 'GET'
    assert request_info['params'] == {'page': 1}
    assert request_info['headers']['Cookie'] == '[REDACTED]'
    assert request_info['headers']['Authorization'] == '[REDACTED]'
    assert request_info['headers']['User-Agent'] == 'eto-test'
    assert row['status_code'] == 200
    connection.close()


def test_post_records_json_body(tmp_path):
    connection = connect(tmp_path / 'eto.db')
    run_id = start_run(connection, 'bangumi', 'collections', '1')
    session = FakeSession(FakeResponse(202, b''))

    http.post(
        session,
        'https://api.bgm.tv/v0/users/-/collections/1',
        endpoint='bangumi.collection.upsert',
        database=connection,
        run_id=run_id,
        json={'type': 3},
    )

    row = connection.execute('SELECT * FROM sync_response').fetchone()
    request_info = json.loads(row['request'])
    assert request_info['body'] == {'type': 3}
    assert row['status_code'] == 202
    connection.close()


def test_transport_error_is_recorded_and_reraised(tmp_path):
    connection = connect(tmp_path / 'eto.db')
    run_id = start_run(connection, 'v2ex', 'favorites', None)
    session = FakeSession(error=requests.Timeout('timed out'))

    with pytest.raises(requests.Timeout):
        http.get(
            session,
            'https://www.v2ex.com/my/topics',
            endpoint='v2ex.fav.page',
            database=connection,
            run_id=run_id,
        )

    row = connection.execute('SELECT * FROM sync_response').fetchone()
    assert row['status_code'] is None
    assert row['body'] is None
    assert 'Timeout' in row['error']
    connection.close()


def test_no_active_run_does_not_record(tmp_path):
    connection = connect(tmp_path / 'eto.db')
    session = FakeSession()

    response = http.get(
        session,
        'https://example.com',
        endpoint='example.page',
    )

    assert response.status_code == 200
    assert connection.execute('SELECT COUNT(*) FROM sync_response').fetchone()[0] == 0
    connection.close()
