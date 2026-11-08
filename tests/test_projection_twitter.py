from __future__ import annotations

import json

import pytest

from db.connection import connect
from db.projections import ProjectionError, rebuild_platform
from tests.projection_helpers import business_rows, record_json

TABLES = ('twitter_tweet',)

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

PAGE = {
    'data': {
        'user': {
            'result': {
                'timeline': {
                    'timeline': {
                        'instructions': [
                            {
                                'type': 'TimelineAddEntries',
                                'entries': [
                                    {
                                        'entryId': 'tweet-111',
                                        'content': {
                                            'entryType': 'TimelineTimelineItem',
                                            'itemContent': {
                                                'itemType': 'TimelineTweet',
                                                'tweet_results': {'result': TWEET},
                                            },
                                        },
                                    }
                                ],
                            }
                        ]
                    }
                }
            }
        }
    }
}


def test_rebuild_projects_liked_tweets():
    connection = connect(':memory:')
    response_id = record_json(connection, 'twitter.likes.page', PAGE)

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
    assert result.responses == 1
    assert result.rows == 1
    connection.close()


def test_rebuild_is_idempotent():
    connection = connect(':memory:')
    record_json(connection, 'twitter.likes.page', PAGE)

    rebuild_platform(connection, 'twitter')
    first = business_rows(connection, TABLES)
    rebuild_platform(connection, 'twitter')
    second = business_rows(connection, TABLES)

    assert first == second
    connection.close()


def test_missing_data_rolls_back():
    connection = connect(':memory:')
    record_json(connection, 'twitter.likes.page', PAGE)
    rebuild_platform(connection, 'twitter')
    before = business_rows(connection, TABLES)

    record_json(connection, 'twitter.likes.page', {'errors': []})

    with pytest.raises(ProjectionError, match='missing data'):
        rebuild_platform(connection, 'twitter')

    assert business_rows(connection, TABLES) == before
    connection.close()
