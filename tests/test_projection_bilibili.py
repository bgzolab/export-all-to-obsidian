from __future__ import annotations

import json

import pytest

from db.connection import connect
from db.projections import ProjectionError, rebuild_platform
from tests.projection_helpers import business_rows, record_json

TABLES = ('bilibili_fav_item', 'bilibili_media', 'bilibili_fav')

INFO = {
    'id': 100,
    'fid': 100,
    'mid': 200,
    'attr': 0,
    'title': 'Favourites',
    'cover': 'cover.jpg',
    'upper': {'mid': 200, 'name': 'Owner', 'face': 'face.jpg'},
    'cover_type': 0,
    'cnt_info': {'collect': 1, 'play': 2, 'thumb_up': 3, 'share': 4},
    'type': 11,
    'intro': 'intro',
    'ctime': 1_700_000_000,
    'mtime': 1_700_000_100,
    'state': 0,
    'fav_state': 0,
    'like_state': 0,
    'media_count': 2,
    'is_top': False,
}

MEDIA = {
    'id': 900,
    'type': 2,
    'title': 'Video',
    'cover': 'video.jpg',
    'intro': 'video intro',
    'page': 1,
    'duration': 120,
    'upper': {'mid': 300, 'name': 'Uploader'},
    'attr': 0,
    'cnt_info': {'collect': 10, 'play': 20, 'danmaku': 30},
    'link': 'bilibili://video/900',
    'ctime': 1_600_000_000,
    'pubtime': 1_600_000_100,
    'fav_time': 1_700_000_200,
    'bv_id': 'BV1xx',
    'bvid': 'BV1xx',
    'ugc': {'first_cid': 11},
    'media_list_link': 'list',
    'season': None,
    'ogv': None,
}


def _page(info=INFO, medias=None):
    return {
        'code': 0,
        'message': '',
        'ttl': 1,
        'data': {
            'info': info,
            'medias': [MEDIA] if medias is None else medias,
            'has_more': False,
            'ttl': 1,
        },
    }


def test_rebuild_projects_favourites_media_and_membership():
    connection = connect(':memory:')
    response_id = record_json(connection, 'bilibili.favlist.page', _page())

    result = rebuild_platform(connection, 'bilibili')

    fav = connection.execute('SELECT * FROM bilibili_fav').fetchone()
    assert fav['fav_id'] == 100
    assert fav['fid'] == 100
    assert fav['ctime'] == 1_700_000_000
    assert fav['mtime'] == 1_700_000_100
    assert json.loads(fav['upper_json'])['name'] == 'Owner'
    assert fav['response_id'] == response_id

    media = connection.execute('SELECT * FROM bilibili_media').fetchone()
    assert media['media_id'] == 900
    assert media['bvid'] == 'BV1xx'
    assert media['ctime'] == 1_600_000_000
    assert media['pubtime'] == 1_600_000_100
    assert json.loads(media['ugc_json']) == {'first_cid': 11}

    item = connection.execute('SELECT * FROM bilibili_fav_item').fetchone()
    assert item['fav_id'] == 100
    assert item['media_id'] == 900
    assert item['fav_time'] == 1_700_000_200

    assert result.responses == 1
    assert result.rows == 3
    connection.close()


def test_media_can_belong_to_multiple_favourites():
    connection = connect(':memory:')
    second_info = dict(INFO, id=101, fid=101, title='Second')
    record_json(connection, 'bilibili.favlist.page', _page())
    record_json(connection, 'bilibili.favlist.page', _page(info=second_info))

    rebuild_platform(connection, 'bilibili')

    assert len(business_rows(connection, ('bilibili_fav',))['bilibili_fav']) == 2
    assert len(business_rows(connection, ('bilibili_media',))['bilibili_media']) == 1
    items = business_rows(connection, ('bilibili_fav_item',))['bilibili_fav_item']
    assert {(row['fav_id'], row['media_id']) for row in items} == {
        (100, 900),
        (101, 900),
    }
    connection.close()


def test_rebuild_is_idempotent():
    connection = connect(':memory:')
    record_json(connection, 'bilibili.favlist.page', _page())

    rebuild_platform(connection, 'bilibili')
    first = business_rows(connection, TABLES)
    rebuild_platform(connection, 'bilibili')
    second = business_rows(connection, TABLES)

    assert first == second
    connection.close()


def test_null_data_is_empty():
    connection = connect(':memory:')
    record_json(
        connection,
        'bilibili.favlist.page',
        {'code': 0, 'message': '', 'ttl': 1, 'data': None},
    )

    result = rebuild_platform(connection, 'bilibili')

    assert result.rows == 0
    assert business_rows(connection, TABLES) == {
        'bilibili_fav_item': [],
        'bilibili_media': [],
        'bilibili_fav': [],
    }
    connection.close()


def test_business_error_rolls_back():
    connection = connect(':memory:')
    record_json(connection, 'bilibili.favlist.page', _page())
    rebuild_platform(connection, 'bilibili')
    before = business_rows(connection, TABLES)

    record_json(
        connection,
        'bilibili.favlist.page',
        {'code': -101, 'message': 'not logged in', 'ttl': 1, 'data': None},
    )

    with pytest.raises(ProjectionError, match='code=-101'):
        rebuild_platform(connection, 'bilibili')

    assert business_rows(connection, TABLES) == before
    connection.close()
