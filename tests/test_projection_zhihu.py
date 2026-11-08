from __future__ import annotations

import json

import pytest

from db.connection import connect
from db.projections import ProjectionError, rebuild_platform
from tests.projection_helpers import business_rows, record_json

TABLES = ('zhihu_collection_item', 'zhihu_content')

REQUEST = {'url': 'https://www.zhihu.com/api/v4/collections/123/items'}

ANSWER = {
    'created': '2026-01-01T00:00:00+08:00',
    'content': {
        'id': 1,
        'type': 'answer',
        'url': 'https://www.zhihu.com/question/1/answer/1',
        'content': '<p>answer</p>',
        'voteup_count': 5,
        'comment_count': 2,
        'created_time': 1_700_000_000,
        'updated_time': 1_700_000_100,
        'author': {'id': 'u1', 'name': 'Author'},
        'question': {'id': 'q1', 'title': 'Question'},
        'title': None,
    },
}

ARTICLE = {
    'created': '2026-01-02T00:00:00+08:00',
    'content': {
        'id': 2,
        'type': 'article',
        'url': 'https://zhuanlan.zhihu.com/p/2',
        'content': [{'title': 'Article', 'content': '<p>article</p>'}],
        'voteup_count': 6,
        'comment_count': 3,
        'created_time': 1_700_000_200,
        'updated_time': 1_700_000_300,
        'author': {'id': 'u2', 'name': 'Writer'},
        'question': None,
        'title': None,
    },
}


def test_rebuild_projects_content_and_membership():
    connection = connect(':memory:')
    response_id = record_json(
        connection,
        'zhihu.collection.page',
        {'paging': {'is_end': True}, 'data': [ANSWER, ARTICLE]},
        request=REQUEST,
    )

    result = rebuild_platform(connection, 'zhihu')

    answer = connection.execute(
        "SELECT * FROM zhihu_content WHERE content_id = '1'"
    ).fetchone()
    assert answer['type'] == 'answer'
    assert answer['title'] == 'Question'
    assert answer['body_html'] == '<p>answer</p>'
    assert answer['created_time'] == 1_700_000_000
    assert answer['updated_time'] == 1_700_000_100
    assert json.loads(answer['content_json']) == '<p>answer</p>'
    assert json.loads(answer['author_json'])['name'] == 'Author'

    article = connection.execute(
        "SELECT * FROM zhihu_content WHERE content_id = '2'"
    ).fetchone()
    assert article['title'] == 'Article'
    assert article['body_html'] == '<p>article</p>'
    assert json.loads(article['content_json']) == [
        {'title': 'Article', 'content': '<p>article</p>'}
    ]

    items = business_rows(connection, ('zhihu_collection_item',))[
        'zhihu_collection_item'
    ]
    assert {(row['collection_id'], row['content_id']) for row in items} == {
        ('123', '1'),
        ('123', '2'),
    }
    assert {row['created'] for row in items} == {
        '2026-01-01T00:00:00+08:00',
        '2026-01-02T00:00:00+08:00',
    }
    assert all(row['response_id'] == response_id for row in items)
    assert result.responses == 1
    assert result.rows == 4
    connection.close()


def test_same_content_can_belong_to_multiple_collections():
    connection = connect(':memory:')
    record_json(
        connection,
        'zhihu.collection.page',
        {'paging': {}, 'data': [ANSWER]},
        request={'url': 'https://www.zhihu.com/api/v4/collections/123/items'},
    )
    record_json(
        connection,
        'zhihu.collection.page',
        {'paging': {}, 'data': [ANSWER]},
        request={'url': 'https://www.zhihu.com/api/v4/collections/456/items'},
    )

    rebuild_platform(connection, 'zhihu')

    assert len(business_rows(connection, ('zhihu_content',))['zhihu_content']) == 1
    items = business_rows(connection, ('zhihu_collection_item',))[
        'zhihu_collection_item'
    ]
    assert {row['collection_id'] for row in items} == {'123', '456'}
    connection.close()


def test_rebuild_is_idempotent():
    connection = connect(':memory:')
    record_json(
        connection,
        'zhihu.collection.page',
        {'paging': {}, 'data': [ANSWER, ARTICLE]},
        request=REQUEST,
    )

    rebuild_platform(connection, 'zhihu')
    first = business_rows(connection, TABLES)
    rebuild_platform(connection, 'zhihu')
    second = business_rows(connection, TABLES)

    assert first == second
    connection.close()


def test_missing_collection_id_rolls_back():
    connection = connect(':memory:')
    record_json(
        connection,
        'zhihu.collection.page',
        {'paging': {}, 'data': [ANSWER]},
        request={'url': 'https://www.zhihu.com/api/v4/items'},
    )

    with pytest.raises(ProjectionError, match='collection id'):
        rebuild_platform(connection, 'zhihu')

    assert business_rows(connection, TABLES) == {
        'zhihu_collection_item': [],
        'zhihu_content': [],
    }
    connection.close()
