from __future__ import annotations

import json

from db.connection import connect
from db.projections import rebuild_platform
from db.projections.weibo import long_text_exists
from tests.projection_helpers import business_rows, record_json

TABLES = ('weibo_post',)

POST = {
    'created_at': 'Wed Jan 01 00:00:00 +0800 2026',
    'id': 1234567890123456789,
    'idstr': '1234567890123456789',
    'mid': '1234567890123456789',
    'mblogid': 'AbCdEf',
    'user': {'id': 42, 'idstr': '42', 'screen_name': 'user'},
    'text': 'text',
    'text_raw': 'raw',
    'source': 'web',
    'favorited': True,
    'pic_num': None,
    'pic_ids': [],
    'pic_infos': {},
    'reposts_count': 1,
    'comments_count': 2,
    'attitudes_count': 3,
    'isLongText': True,
    'region_name': '上海',
}


def _likes(items=None):
    return {'ok': 1, 'data': {'list': [POST] if items is None else items}}


def test_rebuild_projects_posts_and_long_text():
    connection = connect(':memory:')
    likes_response = record_json(
        connection,
        'weibo.likes.page',
        _likes(),
        request={'url': 'https://weibo.com/ajax/statuses/likelist'},
    )
    longtext_response = record_json(
        connection,
        'weibo.longtext',
        {'data': {'longTextContent': 'full text'}},
        request={
            'url': 'https://weibo.com/ajax/statuses/longtext',
            'params': {'id': 'AbCdEf'},
        },
    )

    result = rebuild_platform(connection, 'weibo')

    row = connection.execute('SELECT * FROM weibo_post').fetchone()
    assert row['post_id'] == '1234567890123456789'
    assert row['numeric_id'] == 1234567890123456789
    assert row['mblogid'] == 'AbCdEf'
    assert row['created_at'] == 'Wed Jan 01 00:00:00 +0800 2026'
    assert json.loads(row['user_json'])['screen_name'] == 'user'
    assert row['favorited'] == 1
    assert row['is_long_text'] == 1
    assert row['region_name'] == '上海'
    assert row['long_text'] == 'full text'
    assert row['long_text_response_id'] == longtext_response
    assert row['response_id'] == likes_response
    assert result.responses == 2
    assert result.rows == 2
    connection.close()


def test_long_text_exists_helper():
    connection = connect(':memory:')
    record_json(connection, 'weibo.likes.page', _likes())
    record_json(
        connection,
        'weibo.longtext',
        {'data': {'longTextContent': 'full text'}},
        request={
            'url': 'https://weibo.com/ajax/statuses/longtext',
            'params': {'id': 'AbCdEf'},
        },
    )
    rebuild_platform(connection, 'weibo')

    assert long_text_exists(connection, 'AbCdEf') is True
    assert long_text_exists(connection, 'missing') is False
    assert long_text_exists(connection, None) is False
    connection.close()


def test_missing_long_text_is_skipped():
    connection = connect(':memory:')
    record_json(connection, 'weibo.likes.page', _likes())
    record_json(
        connection,
        'weibo.longtext',
        {'data': {}},
        request={
            'url': 'https://weibo.com/ajax/statuses/longtext',
            'params': {'id': 'AbCdEf'},
        },
    )

    result = rebuild_platform(connection, 'weibo')

    assert result.responses == 1
    assert result.skipped == 1
    row = connection.execute('SELECT * FROM weibo_post').fetchone()
    assert row['long_text'] is None
    assert row['long_text_response_id'] is None
    connection.close()


def test_long_text_post_without_mblogid_is_reported(capsys):
    connection = connect(':memory:')
    post = dict(POST, mblogid=None)
    record_json(connection, 'weibo.likes.page', _likes([post]))

    result = rebuild_platform(connection, 'weibo')

    assert result.aux_missed == 1
    assert '长文缺少 mblogid' in capsys.readouterr().out
    connection.close()


def test_post_without_idstr_is_skipped():
    connection = connect(':memory:')
    post = dict(POST)
    post.pop('idstr')
    record_json(connection, 'weibo.likes.page', _likes([post]))

    result = rebuild_platform(connection, 'weibo')

    assert result.skipped == 1
    assert business_rows(connection, TABLES) == {'weibo_post': []}
    connection.close()


def test_null_data_is_empty():
    connection = connect(':memory:')
    record_json(connection, 'weibo.likes.page', {'ok': 1, 'data': None})

    result = rebuild_platform(connection, 'weibo')

    assert result.rows == 0
    assert business_rows(connection, TABLES) == {'weibo_post': []}
    connection.close()


def test_long_text_without_post_is_reported(capsys):
    connection = connect(':memory:')
    record_json(
        connection,
        'weibo.longtext',
        {'data': {'longTextContent': 'full text'}},
        request={
            'url': 'https://weibo.com/ajax/statuses/longtext',
            'params': {'id': 'AbCdEf'},
        },
    )

    result = rebuild_platform(connection, 'weibo')

    assert result.rows == 0
    assert result.aux_missed == 1
    assert '辅助数据未命中主行' in capsys.readouterr().out
    connection.close()


def test_rebuild_is_idempotent():
    connection = connect(':memory:')
    record_json(connection, 'weibo.likes.page', _likes())
    record_json(
        connection,
        'weibo.longtext',
        {'data': {'longTextContent': 'full text'}},
        request={
            'url': 'https://weibo.com/ajax/statuses/longtext',
            'params': {'id': 'AbCdEf'},
        },
    )

    rebuild_platform(connection, 'weibo')
    first = business_rows(connection, TABLES)
    rebuild_platform(connection, 'weibo')
    second = business_rows(connection, TABLES)

    assert first == second
    connection.close()


def test_business_error_is_skipped():
    connection = connect(':memory:')
    record_json(connection, 'weibo.likes.page', _likes())
    rebuild_platform(connection, 'weibo')
    before = business_rows(connection, TABLES)

    record_json(
        connection,
        'weibo.likes.page',
        {'ok': 0, 'data': None},
        request={'url': 'https://weibo.com/ajax/statuses/likelist'},
    )

    result = rebuild_platform(connection, 'weibo')

    assert result.skipped == 1
    assert business_rows(connection, TABLES) == before
    connection.close()
