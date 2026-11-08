from __future__ import annotations

import json

import pytest

from db.connection import connect
from db.projections import ProjectionError, rebuild_platform
from tests.projection_helpers import business_rows, record_json, record_text

TABLES = ('v2ex_reply', 'v2ex_favorite', 'v2ex_topic')

FAV_HTML = """
<a href="/t/1">one</a>
<a href="/t/1#reply1">duplicate</a>
<a href="/t/2">two</a>
"""


def _topic(topic_id: int, title: str) -> dict:
    return {
        'success': True,
        'message': '',
        'result': {
            'id': topic_id,
            'title': title,
            'content': 'topic body',
            'syntax': 1,
            'url': f'https://www.v2ex.com/t/{topic_id}',
            'replies': 2,
            'last_reply_by': 'member',
            'created': 1_700_000_000,
            'last_modified': 1_700_000_100,
            'last_touched': 1_700_000_200,
            'member': {'id': 1, 'username': 'member'},
            'node': {'id': 2, 'name': 'python'},
            'supplements': [{'content': 'update'}],
        },
    }


REPLIES = {
    'success': True,
    'message': '',
    'result': [
        {
            'id': 11,
            'content': 'reply one',
            'content_rendered': '<p>reply one</p>',
            'thanks': 5,
            'created': 1_700_000_300,
            'last_modified': 1_700_000_400,
            'member': {'id': 3, 'username': 'a'},
        },
        {
            'id': 12,
            'content': 'reply two',
            'content_rendered': '<p>reply two</p>',
            'created': 1_700_000_500,
            'member': {'id': 4, 'username': 'b'},
        },
    ],
}


def _seed(connection):
    record_text(
        connection,
        'v2ex.fav.page',
        FAV_HTML,
        request={'url': 'https://www.v2ex.com/my/topics', 'params': {'p': 1}},
    )
    record_json(
        connection,
        'v2ex.topic.detail',
        _topic(1, 'Topic one'),
        request={'url': 'https://www.v2ex.com/api/v2/topics/1'},
    )
    record_json(
        connection,
        'v2ex.topic.detail',
        _topic(2, 'Topic two'),
        request={'url': 'https://www.v2ex.com/api/v2/topics/2'},
    )
    record_json(
        connection,
        'v2ex.topic.replies.page',
        REPLIES,
        request={
            'url': 'https://www.v2ex.com/api/v2/topics/1/replies',
            'params': {'p': 1},
        },
    )


def test_rebuild_projects_favorites_topics_and_replies():
    connection = connect(':memory:')
    _seed(connection)

    result = rebuild_platform(connection, 'v2ex')

    favorites = business_rows(connection, ('v2ex_favorite',))['v2ex_favorite']
    assert {row['topic_id'] for row in favorites} == {1, 2}

    topic = connection.execute('SELECT * FROM v2ex_topic WHERE topic_id = 1').fetchone()
    assert topic['title'] == 'Topic one'
    assert topic['created'] == 1_700_000_000
    assert topic['last_modified'] == 1_700_000_100
    assert topic['last_touched'] == 1_700_000_200
    assert json.loads(topic['member_json'])['username'] == 'member'
    assert json.loads(topic['node_json'])['name'] == 'python'
    assert json.loads(topic['supplements_json']) == [{'content': 'update'}]

    replies = business_rows(connection, ('v2ex_reply',))['v2ex_reply']
    assert [row['reply_id'] for row in replies] == [11, 12]
    assert replies[0]['thanks'] == 5
    assert replies[0]['last_modified'] == 1_700_000_400
    assert replies[1]['thanks'] == 0
    assert replies[1]['last_modified'] == 0
    assert all(row['topic_id'] == 1 for row in replies)

    hot = connection.execute(
        'SELECT reply_id FROM v2ex_reply WHERE topic_id = 1 ORDER BY thanks DESC'
    ).fetchall()
    assert [row[0] for row in hot] == [11, 12]
    assert result.responses == 4
    assert result.rows == 6
    connection.close()


def test_replies_are_independent_of_topic_detail():
    connection = connect(':memory:')
    record_json(
        connection,
        'v2ex.topic.replies.page',
        REPLIES,
        request={'url': 'https://www.v2ex.com/api/v2/topics/1/replies'},
    )

    rebuild_platform(connection, 'v2ex')

    assert len(business_rows(connection, ('v2ex_reply',))['v2ex_reply']) == 2
    assert business_rows(connection, ('v2ex_topic',))['v2ex_topic'] == []
    connection.close()


def test_signin_page_rolls_back_favorites():
    connection = connect(':memory:')
    _seed(connection)
    rebuild_platform(connection, 'v2ex')
    before = business_rows(connection, TABLES)

    record_text(
        connection,
        'v2ex.fav.page',
        '<html><form action="/signin" method="post"></form></html>',
        request={'url': 'https://www.v2ex.com/my/topics'},
    )

    with pytest.raises(ProjectionError, match='signin'):
        rebuild_platform(connection, 'v2ex')

    assert business_rows(connection, TABLES) == before
    connection.close()


def test_null_replies_result_is_skipped():
    connection = connect(':memory:')
    record_json(
        connection,
        'v2ex.topic.replies.page',
        {'success': True, 'result': None},
        request={'url': 'https://www.v2ex.com/api/v2/topics/1/replies'},
    )

    result = rebuild_platform(connection, 'v2ex')

    assert result.responses == 0
    assert result.skipped == 1
    assert business_rows(connection, ('v2ex_reply',))['v2ex_reply'] == []
    connection.close()


def test_invalid_reply_json_is_skipped():
    connection = connect(':memory:')
    _seed(connection)
    record_text(
        connection,
        'v2ex.topic.replies.page',
        '{',
        request={'url': 'https://www.v2ex.com/api/v2/topics/1/replies'},
    )

    result = rebuild_platform(connection, 'v2ex')

    assert result.skipped == 1
    assert len(business_rows(connection, ('v2ex_reply',))['v2ex_reply']) == 2
    connection.close()


def test_reply_item_without_id_is_skipped():
    connection = connect(':memory:')
    record_json(
        connection,
        'v2ex.topic.replies.page',
        {
            'success': True,
            'result': [
                {'content': 'missing id'},
                {'id': 11, 'content': 'valid', 'created': 1},
            ],
        },
        request={'url': 'https://www.v2ex.com/api/v2/topics/1/replies'},
    )

    result = rebuild_platform(connection, 'v2ex')

    assert result.skipped == 1
    replies = business_rows(connection, ('v2ex_reply',))['v2ex_reply']
    assert [row['reply_id'] for row in replies] == [11]
    connection.close()


def test_rebuild_is_idempotent():
    connection = connect(':memory:')
    _seed(connection)

    rebuild_platform(connection, 'v2ex')
    first = business_rows(connection, TABLES)
    rebuild_platform(connection, 'v2ex')
    second = business_rows(connection, TABLES)

    assert first == second
    connection.close()


def test_null_topic_result_is_skipped():
    connection = connect(':memory:')
    _seed(connection)
    rebuild_platform(connection, 'v2ex')
    before = business_rows(connection, TABLES)

    record_json(
        connection,
        'v2ex.topic.detail',
        {'success': False, 'message': '', 'result': None},
        request={'url': 'https://www.v2ex.com/api/v2/topics/3'},
    )

    result = rebuild_platform(connection, 'v2ex')

    assert result.skipped == 1
    assert business_rows(connection, TABLES) == before
    connection.close()


def test_missing_topic_result_key_rolls_back():
    connection = connect(':memory:')
    _seed(connection)
    rebuild_platform(connection, 'v2ex')
    before = business_rows(connection, TABLES)

    record_json(
        connection,
        'v2ex.topic.detail',
        {'success': False, 'message': ''},
        request={'url': 'https://www.v2ex.com/api/v2/topics/3'},
    )

    with pytest.raises(ProjectionError, match='missing result'):
        rebuild_platform(connection, 'v2ex')

    assert business_rows(connection, TABLES) == before
    connection.close()
