from __future__ import annotations

import json
from dataclasses import replace

import pytest

from db.connection import connect
from db.projections import ProjectionError, rebuild_platform
from db.projections.v2ex import (
    replies_complete,
    thanks_page_known,
    tipped_topic_ids,
    topic_reply_count,
)
from tests.projection_helpers import business_rows, record_json, record_text
from v2ex.tipped import parse_balance_page

TABLES = ('v2ex_reply', 'v2ex_favorite', 'v2ex_topic', 'v2ex_thanks')

THANKS_HTML = """
<table class="data">
    <tr>
        <th>时间</th>
        <th>类型</th>
        <th>金额</th>
        <th>余额</th>
        <th>描述</th>
    </tr>
    <tr>
        <td>2026-11-18 10:00:00 +08:00</td>
        <td>发送谢意</td>
        <td>-10.0</td>
        <td>1234.50</td>
        <td>感谢 <a href="/member/alice">alice</a> 的回复
            <span class="fade">›</span>
            <a href="/t/1">Topic one</a></td>
    </tr>
    <tr>
        <td>2026-11-17 09:00:00 +08:00</td>
        <td>发送谢意</td>
        <td>-15.0</td>
        <td>1244.50</td>
        <td>感谢 <a href="/member/bob">bob</a> 的主题
            <span class="fade">›</span>
            <a href="/t/2">Topic two</a></td>
    </tr>
    <tr>
        <td>2026-11-16 08:00:00 +08:00</td>
        <td>每日登录奖励</td>
        <td>19.0</td>
        <td>1259.50</td>
        <td>20261116 的每日登录奖励 19 铜币</td>
    </tr>
</table>
"""

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


def test_projection_helpers_report_known_rows():
    connection = connect(':memory:')
    _seed(connection)
    rebuild_platform(connection, 'v2ex')

    assert topic_reply_count(connection, 1) == 2
    assert topic_reply_count(connection, 99) is None
    assert replies_complete(connection, 1, 2) is True
    assert replies_complete(connection, 1, 3) is False
    assert replies_complete(connection, 99, 1) is False
    connection.close()


def test_rebuild_projects_thanks_transactions():
    connection = connect(':memory:')
    response_id = record_text(
        connection,
        'v2ex.balance.page',
        THANKS_HTML,
        request={'url': 'https://www.v2ex.com/balance', 'params': {'p': 1}},
    )

    result = rebuild_platform(connection, 'v2ex')

    thanks = business_rows(connection, ('v2ex_thanks',))['v2ex_thanks']
    assert result.responses == 1
    assert result.rows == 2
    assert [
        (
            row['thanked_at'],
            row['topic_id'],
            row['content_kind'],
            row['member'],
            row['amount'],
            row['balance'],
            row['topic_title'],
        )
        for row in thanks
    ] == [
        (
            '2026-11-18 10:00:00 +08:00',
            1,
            'reply',
            'alice',
            -10.0,
            1234.5,
            'Topic one',
        ),
        (
            '2026-11-17 09:00:00 +08:00',
            2,
            'topic',
            'bob',
            -15.0,
            1244.5,
            'Topic two',
        ),
    ]
    assert all(row['response_id'] == response_id for row in thanks)
    assert '感谢 alice 的回复' in thanks[0]['description']
    connection.close()


def test_duplicate_balance_pages_are_idempotent():
    connection = connect(':memory:')
    record_text(connection, 'v2ex.balance.page', THANKS_HTML)
    record_text(connection, 'v2ex.balance.page', THANKS_HTML)

    rebuild_platform(connection, 'v2ex')
    first = business_rows(connection, ('v2ex_thanks',))['v2ex_thanks']
    rebuild_platform(connection, 'v2ex')
    second = business_rows(connection, ('v2ex_thanks',))['v2ex_thanks']

    assert len(first) == 2
    assert first == second
    connection.close()


def test_signin_balance_page_rolls_back_thanks():
    connection = connect(':memory:')
    record_text(connection, 'v2ex.balance.page', THANKS_HTML)
    rebuild_platform(connection, 'v2ex')
    before = business_rows(connection, TABLES)

    record_text(
        connection,
        'v2ex.balance.page',
        '<html><form action="/signin" method="post"></form></html>',
    )

    with pytest.raises(ProjectionError, match='signin'):
        rebuild_platform(connection, 'v2ex')

    assert business_rows(connection, TABLES) == before
    connection.close()


def test_thanks_helpers_report_known_rows():
    connection = connect(':memory:')
    record_text(connection, 'v2ex.balance.page', THANKS_HTML)
    rebuild_platform(connection, 'v2ex')
    page = parse_balance_page(THANKS_HTML)

    assert thanks_page_known(connection, page.thanks) is True
    assert thanks_page_known(connection, page.thanks[:1]) is True
    assert thanks_page_known(connection, []) is False
    assert (
        thanks_page_known(connection, [replace(page.thanks[0], balance=1.0)]) is False
    )
    assert (
        thanks_page_known(connection, [replace(page.thanks[0], member='other')])
        is False
    )
    assert tipped_topic_ids(connection) == [1, 2]

    record_text(
        connection,
        'v2ex.balance.page',
        """
        <table class="data">
            <tr><td>2026-11-19 10:00:00 +08:00</td><td>发送谢意</td>
                <td>-10.0</td><td>100.0</td>
                <td>感谢 <a href="/member/carol">carol</a> 的主题
                    <a href="/t/1">Topic one</a></td></tr>
        </table>
        """,
    )
    rebuild_platform(connection, 'v2ex')

    # Same topic thanked as a topic also dedupes, and the newest transaction
    # moves it to the front without duplicating the id.
    assert tipped_topic_ids(connection) == [1, 2]
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


def test_missing_topic_result_key_is_skipped():
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

    result = rebuild_platform(connection, 'v2ex')

    assert result.skipped == 1
    assert business_rows(connection, TABLES) == before
    connection.close()


def test_array_replies_payload_is_skipped():
    connection = connect(':memory:')
    record_json(
        connection,
        'v2ex.topic.replies.page',
        [],
        request={'url': 'https://www.v2ex.com/api/v2/topics/1/replies'},
    )

    result = rebuild_platform(connection, 'v2ex')

    assert result.skipped == 1
    assert business_rows(connection, ('v2ex_reply',))['v2ex_reply'] == []
    connection.close()
