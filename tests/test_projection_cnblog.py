from __future__ import annotations

import json

from db.connection import connect
from db.projections import rebuild_platform
from db.projections.cnblog import post_exists
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
    assert post_exists(connection, 'https://example.com/missing') is False
    assert post_exists(connection, '') is False
    connection.close()


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
