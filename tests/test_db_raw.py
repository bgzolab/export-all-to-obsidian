from __future__ import annotations

import hashlib
import json
import zlib

import pytest

from db.connection import connect
from db.raw import (
    finish_run,
    iter_responses,
    record_error,
    record_response,
    start_run,
)


def test_run_and_response_round_trip(tmp_path):
    connection = connect(tmp_path / 'eto.db')
    run_id = start_run(
        connection,
        platform='github',
        operation='stars',
        scope='octocat',
        command='eto --db eto.db github -t template.md -o output',
    )

    body = b'{"hello": "world"}'
    response_id = record_response(
        connection,
        run_id,
        endpoint='github.stars.list',
        request={'method': 'GET', 'url': 'https://api.github.com/user/starred'},
        status_code=200,
        body=body,
    )
    finish_run(connection, run_id, 'success')

    run = connection.execute(
        'SELECT * FROM sync_run WHERE id = ?', (run_id,)
    ).fetchone()
    assert run['status'] == 'success'
    assert run['command'].startswith('eto --db')
    assert run['finished_at'] is not None

    row = connection.execute(
        'SELECT * FROM sync_response WHERE id = ?', (response_id,)
    ).fetchone()
    assert zlib.decompress(row['body']) == body
    assert row['sha256'] == hashlib.sha256(body).hexdigest()
    assert json.loads(row['request'])['method'] == 'GET'
    assert row['status_code'] == 200
    assert row['error'] is None

    connection.close()


def test_iter_responses_decompresses_body(tmp_path):
    connection = connect(tmp_path / 'eto.db')
    run_id = start_run(connection, 'zhihu', 'collection', '123')
    record_response(
        connection,
        run_id,
        endpoint='zhihu.collection.page',
        request={'params': {'offset': 0}},
        status_code=200,
        body=b'{"data": []}',
    )

    rows = list(iter_responses(connection, endpoint='zhihu.collection.page'))
    assert len(rows) == 1
    assert rows[0]['body'] == b'{"data": []}'
    assert list(iter_responses(connection, endpoint='missing')) == []
    connection.close()


def test_record_error_stores_no_body(tmp_path):
    connection = connect(tmp_path / 'eto.db')
    run_id = start_run(connection, 'v2ex', 'favorites', 'octocat')

    response_id = record_error(
        connection,
        run_id,
        endpoint='v2ex.fav.page',
        request={'params': {'p': 1}},
        error='ConnectTimeout: timed out',
    )

    row = connection.execute(
        'SELECT * FROM sync_response WHERE id = ?', (response_id,)
    ).fetchone()
    assert row['body'] is None
    assert row['sha256'] is None
    assert row['status_code'] is None
    assert row['error'] == 'ConnectTimeout: timed out'
    connection.close()


def test_finish_run_rejects_unknown_status(tmp_path):
    connection = connect(tmp_path / 'eto.db')
    run_id = start_run(connection, 'weibo', 'likes', '1')

    with pytest.raises(ValueError, match='Invalid run status'):
        finish_run(connection, run_id, 'done')
    connection.close()


def test_finish_run_can_mark_partial(tmp_path):
    connection = connect(tmp_path / 'eto.db')
    run_id = start_run(connection, 'twitter', 'likes', '1')
    finish_run(connection, run_id, 'partial')

    row = connection.execute(
        'SELECT * FROM sync_run WHERE id = ?', (run_id,)
    ).fetchone()
    assert row['status'] == 'partial'
    assert row['finished_at'] is not None
    connection.close()
