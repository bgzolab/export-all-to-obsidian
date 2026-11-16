from __future__ import annotations

import json

import pytest

from db.connection import connect
from db.projections import ProjectionError, rebuild_platform
from tests.projection_helpers import business_rows, record_json

TABLES = ('twitter_like', 'twitter_bookmark', 'twitter_tweet')

TWEET = {
    '__typename': 'TweetWithVisibilityResults',
    'tweet': {
        'rest_id': '111',
        'core': {
            'user_results': {
                'result': {
                    'rest_id': '42',
                    'core': {'screen_name': 'alice', 'name': 'Alice'},
                }
            }
        },
        'legacy': {
            'id_str': '111',
            'created_at': 'Thu Aug 15 12:00:00 +0000 2024',
            'full_text': 'Hello Twitter',
            'favorite_count': 5,
            'retweet_count': 2,
            'reply_count': 1,
        },
        'views': {'count': '100'},
    },
}

ENTRY = {
    'entryId': 'tweet-111',
    'content': {
        'entryType': 'TimelineTimelineItem',
        'itemContent': {
            'itemType': 'TimelineTweet',
            'tweet_results': {'result': TWEET},
        },
    },
}

LIKES_PAGE = {
    'data': {
        'user': {
            'result': {
                'timeline': {
                    'timeline': {
                        'instructions': [
                            {'type': 'TimelineAddEntries', 'entries': [ENTRY]}
                        ]
                    }
                }
            }
        }
    }
}

BOOKMARK_PAGE = {
    'data': {
        'bookmark_timeline_v2': {
            'timeline': {
                'instructions': [{'type': 'TimelineAddEntries', 'entries': [ENTRY]}]
            }
        }
    }
}


def test_rebuild_projects_liked_tweets_and_relation():
    connection = connect(':memory:')
    response_id = record_json(connection, 'twitter.likes.page', LIKES_PAGE)

    result = rebuild_platform(connection, 'twitter')

    row = connection.execute('SELECT * FROM twitter_tweet').fetchone()
    assert row['tweet_id'] == '111'
    assert row['created_at'] == 'Thu Aug 15 12:00:00 +0000 2024'
    assert row['full_text'] == 'Hello Twitter'
    assert json.loads(row['author_json']) == {
        'screen_name': 'alice',
        'name': 'Alice',
        'id': '42',
    }
    assert row['favorite_count'] == 5
    assert row['retweet_count'] == 2
    assert row['reply_count'] == 1
    assert row['view_count'] == 100
    assert row['response_id'] == response_id

    like = connection.execute('SELECT * FROM twitter_like').fetchone()
    assert like['tweet_id'] == '111'
    assert like['response_id'] == response_id
    assert (
        connection.execute('SELECT count(*) FROM twitter_bookmark').fetchone()[0] == 0
    )
    assert result.responses == 1
    assert result.rows == 2
    connection.close()


def test_rebuild_projects_bookmarked_tweets_and_relation():
    connection = connect(':memory:')
    response_id = record_json(connection, 'twitter.bookmarks.page', BOOKMARK_PAGE)

    result = rebuild_platform(connection, 'twitter')

    assert connection.execute('SELECT count(*) FROM twitter_tweet').fetchone()[0] == 1
    bookmark = connection.execute('SELECT * FROM twitter_bookmark').fetchone()
    assert bookmark['tweet_id'] == '111'
    assert bookmark['response_id'] == response_id
    assert connection.execute('SELECT count(*) FROM twitter_like').fetchone()[0] == 0
    assert result.responses == 1
    assert result.rows == 2
    connection.close()


def test_rebuild_shares_tweet_row_between_like_and_bookmark():
    connection = connect(':memory:')
    like_response_id = record_json(connection, 'twitter.likes.page', LIKES_PAGE)
    bookmark_response_id = record_json(
        connection, 'twitter.bookmarks.page', BOOKMARK_PAGE
    )

    result = rebuild_platform(connection, 'twitter')

    tweet = connection.execute('SELECT * FROM twitter_tweet').fetchone()
    assert tweet['response_id'] == bookmark_response_id
    like = connection.execute('SELECT * FROM twitter_like').fetchone()
    assert like['response_id'] == like_response_id
    bookmark = connection.execute('SELECT * FROM twitter_bookmark').fetchone()
    assert bookmark['response_id'] == bookmark_response_id
    assert result.responses == 2
    assert result.rows == 4
    connection.close()


def test_rebuild_is_idempotent():
    connection = connect(':memory:')
    record_json(connection, 'twitter.likes.page', LIKES_PAGE)
    record_json(connection, 'twitter.bookmarks.page', BOOKMARK_PAGE)

    rebuild_platform(connection, 'twitter')
    first = business_rows(connection, TABLES)
    rebuild_platform(connection, 'twitter')
    second = business_rows(connection, TABLES)

    assert first == second
    connection.close()


@pytest.mark.parametrize(
    'endpoint',
    ['twitter.likes.page', 'twitter.bookmarks.page'],
)
def test_errors_only_payload_is_skipped(endpoint):
    connection = connect(':memory:')
    record_json(connection, 'twitter.likes.page', LIKES_PAGE)
    rebuild_platform(connection, 'twitter')
    before = business_rows(connection, TABLES)

    record_json(connection, endpoint, {'errors': []})

    result = rebuild_platform(connection, 'twitter')

    assert result.skipped == 1
    assert business_rows(connection, TABLES) == before
    connection.close()


@pytest.mark.parametrize(
    'endpoint,message',
    [
        ('twitter.likes.page', 'invalid likes payload'),
        ('twitter.bookmarks.page', 'invalid bookmarks payload'),
    ],
)
def test_non_dict_payload_rolls_back(endpoint, message):
    connection = connect(':memory:')
    record_json(connection, 'twitter.likes.page', LIKES_PAGE)
    rebuild_platform(connection, 'twitter')
    before = business_rows(connection, TABLES)

    record_json(connection, endpoint, [])

    with pytest.raises(ProjectionError, match=message):
        rebuild_platform(connection, 'twitter')

    assert business_rows(connection, TABLES) == before
    connection.close()
