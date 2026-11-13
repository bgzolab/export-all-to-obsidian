from __future__ import annotations

import json

from cnblog.urls import post_id_from_url
from db.connection import connect
from db.projections import rebuild_platform
from db.projections.cnblog import post_exists, post_pending_count
from tests.projection_helpers import business_rows, record_json, record_text

TABLES = ('cnblog_post', 'cnblog_bookmark')

BOOKMARKS = [
    {
        'WzLinkId': 1,
        'Title': 'Post one',
        'LinkUrl': 'https://www.cnblogs.com/user/p/123.html',
        'Summary': 'Summary one',
        'Tags': ['python'],
        'DateAdded': '2026-01-01T00:00:00+08:00',
        'FromCNBlogs': True,
    },
    {
        'WzLinkId': 2,
        'Title': 'External',
        'LinkUrl': 'https://example.com/',
        'Summary': '',
        'Tags': [],
        'DateAdded': '2026-01-02T00:00:00+08:00',
        'FromCNBlogs': False,
    },
]


def test_rebuild_projects_bookmarks_and_post_bodies():
    connection = connect(':memory:')
    response_id = record_json(
        connection,
        'cnblog.bookmarks.page',
        BOOKMARKS,
        request={'url': 'https://api.cnblogs.com/api/Bookmarks'},
    )
    post_response = record_text(
        connection,
        'cnblog.post.body',
        '<p>post body</p>',
        request={'url': 'https://api.cnblogs.com/api/blogposts/123/body'},
    )

    result = rebuild_platform(connection, 'cnblog')

    bookmarks = business_rows(connection, ('cnblog_bookmark',))['cnblog_bookmark']
    assert [row['wz_link_id'] for row in bookmarks] == [1, 2]
    assert bookmarks[0]['title'] == 'Post one'
    assert bookmarks[0]['date_added'] == '2026-01-01T00:00:00+08:00'
    assert bookmarks[0]['from_cnblogs'] == 1
    assert json.loads(bookmarks[0]['tags_json']) == ['python']
    assert bookmarks[1]['from_cnblogs'] == 0
    assert all(row['response_id'] == response_id for row in bookmarks)

    post = connection.execute('SELECT * FROM cnblog_post').fetchone()
    assert post['post_id'] == 123
    assert post['source_url'] == 'https://www.cnblogs.com/user/p/123.html'
    assert post['body'] == '<p>post body</p>'
    assert post['response_id'] == post_response
    assert result.responses == 2
    assert result.rows == 3
    connection.close()


def test_single_bookmark_object_is_supported():
    connection = connect(':memory:')
    record_json(connection, 'cnblog.bookmarks.page', BOOKMARKS[0])

    rebuild_platform(connection, 'cnblog')

    assert len(business_rows(connection, ('cnblog_bookmark',))['cnblog_bookmark']) == 1
    connection.close()


def test_post_exists_helper():
    connection = connect(':memory:')
    record_json(connection, 'cnblog.bookmarks.page', BOOKMARKS)
    record_text(
        connection,
        'cnblog.post.body',
        '<p>post body</p>',
        request={'url': 'https://api.cnblogs.com/api/blogposts/123/body'},
    )
    rebuild_platform(connection, 'cnblog')

    assert post_exists(connection, BOOKMARKS[0]['LinkUrl']) is True
    assert post_exists(connection, 'https://www.cnblogs.com/user/p/123') is True
    assert post_exists(connection, 'https://www.cnblogs.com/user/p/123/slug') is True
    assert post_exists(connection, 'https://example.com/missing') is False
    assert post_exists(connection, 'https://www.cnblogs.com/user/p/slug.html') is False
    assert post_exists(connection, '') is False
    connection.close()


def test_post_pending_count_uses_url_post_id():
    connection = connect(':memory:')
    bookmarks = [
        dict(BOOKMARKS[0], WzLinkId=10, LinkUrl='https://www.cnblogs.com/user/p/123'),
        dict(BOOKMARKS[0], WzLinkId=11, LinkUrl='https://www.cnblogs.com/user/p/456'),
        dict(
            BOOKMARKS[0],
            WzLinkId=12,
            LinkUrl='https://www.cnblogs.com/user/p/slug-only.html',
        ),
    ]
    record_json(connection, 'cnblog.bookmarks.page', bookmarks)
    record_text(
        connection,
        'cnblog.post.body',
        '<p>post body</p>',
        request={'url': 'https://api.cnblogs.com/api/blogposts/123/body'},
    )

    rebuild_platform(connection, 'cnblog')

    # 456 缺正文；slug-only 无法解析 ID，不再虚报；123 已入库。
    assert post_pending_count(connection) == 1
    assert post_pending_count(connection, {10}) == 1
    assert post_pending_count(connection, {11}) == 0
    post = connection.execute('SELECT * FROM cnblog_post').fetchone()
    assert post['source_url'] == 'https://www.cnblogs.com/user/p/123'
    connection.close()


def test_post_id_from_url_forms():
    assert post_id_from_url('https://www.cnblogs.com/user/p/123.html') == 123
    assert post_id_from_url('https://www.cnblogs.com/user/p/123') == 123
    assert post_id_from_url('https://www.cnblogs.com/user/p/123/how-to-fetch') == 123
    assert post_id_from_url('https://news.cnblogs.com/n/456') == 456
    assert post_id_from_url('https://www.cnblogs.com/user/articles/654') == 654
    assert (
        post_id_from_url('https://www.cnblogs.com/user/archive/2007/05/22/789.html')
        == 789
    )
    assert post_id_from_url('https://www.cnblogs.com/user/p/slug-only.html') is None
    assert post_id_from_url('https://www.cnblogs.com/user/p/-/slug') is None
    assert post_id_from_url('https://www.cnblogs.com/user/p/½') is None
    assert post_id_from_url('https://www.cnblogs.com/user/p/².html') is None
    assert post_id_from_url('https://example.org/user/p/999') is None
    assert post_id_from_url('https://www.cnblogs.com/user/archive/2024/01.aspx') is None
    assert post_id_from_url('https://www.cnblogs.com/user/archive/2024') is None
    assert (
        post_id_from_url('https://www.cnblogs.com/user/archive/2024/1/2/789.html')
        is None
    )
    assert post_id_from_url('') is None


def test_ambiguous_source_url_is_left_empty():
    connection = connect(':memory:')
    bookmark = dict(BOOKMARKS[0], LinkUrl='https://example.com/123')
    record_json(connection, 'cnblog.bookmarks.page', [bookmark])
    record_text(
        connection,
        'cnblog.post.body',
        '<p>post body</p>',
        request={'url': 'https://api.cnblogs.com/api/blogposts/123/body'},
    )

    rebuild_platform(connection, 'cnblog')

    post = connection.execute('SELECT * FROM cnblog_post').fetchone()
    assert post['source_url'] == ''
    connection.close()


def test_duplicate_same_source_url_is_not_ambiguous():
    connection = connect(':memory:')
    duplicate = dict(BOOKMARKS[0], WzLinkId=3)
    record_json(connection, 'cnblog.bookmarks.page', [BOOKMARKS[0], duplicate])
    record_text(
        connection,
        'cnblog.post.body',
        '<p>post body</p>',
        request={'url': 'https://api.cnblogs.com/api/blogposts/123/body'},
    )

    rebuild_platform(connection, 'cnblog')

    post = connection.execute('SELECT * FROM cnblog_post').fetchone()
    assert post['source_url'] == BOOKMARKS[0]['LinkUrl']
    connection.close()


def test_non_200_post_body_is_skipped():
    connection = connect(':memory:')
    record_json(connection, 'cnblog.bookmarks.page', BOOKMARKS)
    record_text(
        connection,
        'cnblog.post.body',
        'error',
        request={'url': 'https://api.cnblogs.com/api/blogposts/123/body'},
        status_code=404,
    )

    rebuild_platform(connection, 'cnblog')

    assert business_rows(connection, ('cnblog_post',))['cnblog_post'] == []
    connection.close()


def test_rebuild_is_idempotent():
    connection = connect(':memory:')
    record_json(connection, 'cnblog.bookmarks.page', BOOKMARKS)
    record_text(
        connection,
        'cnblog.post.body',
        '<p>post body</p>',
        request={'url': 'https://api.cnblogs.com/api/blogposts/123/body'},
    )

    rebuild_platform(connection, 'cnblog')
    first = business_rows(connection, TABLES)
    rebuild_platform(connection, 'cnblog')
    second = business_rows(connection, TABLES)

    assert first == second
    connection.close()


def test_invalid_post_url_is_skipped():
    connection = connect(':memory:')
    record_json(connection, 'cnblog.bookmarks.page', BOOKMARKS)
    record_text(
        connection,
        'cnblog.post.body',
        '<p>post body</p>',
        request={'url': 'https://api.cnblogs.com/api/blogposts/body'},
    )

    result = rebuild_platform(connection, 'cnblog')

    assert result.responses == 1
    assert result.skipped == 1
    assert len(business_rows(connection, ('cnblog_bookmark',))['cnblog_bookmark']) == 2
    assert business_rows(connection, ('cnblog_post',))['cnblog_post'] == []
    connection.close()
