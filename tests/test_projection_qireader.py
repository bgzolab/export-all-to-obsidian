from __future__ import annotations

import json

import pytest

from db.connection import connect
from db.projections import ProjectionError, rebuild_platform
from tests.projection_helpers import business_rows, record_json

TABLES = ('qireader_article', 'qireader_entry')

ENTRY = {
    'id': 'entry-1',
    'isSaved': True,
    'sourceEntryId': 'source-1',
    'origin': {'feedId': 'feed-1'},
    'title': 'Article title',
    'summary': 'Summary',
    'url': 'https://example.com/a',
    'publishedAt': 1_700_000_000_000,
    'crawledAt': 1_700_000_100_000,
    'timestamp': '1763974116059279295',
    'attachments': [{'type': 'image'}],
    'tagIds': ['tag-1'],
}

PAGE = {'result': {'id': 'tag-1', 'entries': [ENTRY], 'hasMore': False}}


def test_rebuild_projects_entries_and_articles():
    connection = connect(':memory:')
    response_id = record_json(
        connection,
        'qireader.readlater.page',
        PAGE,
        request={'url': 'https://www.qireader.com/api/streams/tag-1'},
    )
    article_response = record_json(
        connection,
        'qireader.article',
        {'content': '<p>article</p>'},
        request={
            'url': 'https://nettools3.oxyry.com/text',
            'params': {'keep-classes': 1, 'url': 'https://example.com/a'},
        },
    )

    result = rebuild_platform(connection, 'qireader')

    entry = connection.execute('SELECT * FROM qireader_entry').fetchone()
    assert entry['entry_id'] == 'entry-1'
    assert entry['is_saved'] == 1
    assert entry['source_entry_id'] == 'source-1'
    assert entry['published_at'] == 1_700_000_000_000
    assert entry['crawled_at'] == 1_700_000_100_000
    assert entry['timestamp'] == '1763974116059279295'
    assert json.loads(entry['attachments_json']) == [{'type': 'image'}]
    assert json.loads(entry['tag_ids_json']) == ['tag-1']
    assert entry['response_id'] == response_id

    article = connection.execute('SELECT * FROM qireader_article').fetchone()
    assert article['url'] == 'https://example.com/a'
    assert article['content'] == '<p>article</p>'
    assert article['response_id'] == article_response
    assert result.responses == 2
    assert result.rows == 2
    connection.close()


def test_non_200_article_is_skipped():
    connection = connect(':memory:')
    record_json(connection, 'qireader.readlater.page', PAGE)
    record_json(
        connection,
        'qireader.article',
        {'error': 'gone'},
        request={
            'url': 'https://nettools3.oxyry.com/text',
            'params': {'url': 'https://example.com/a'},
        },
        status_code=404,
    )

    rebuild_platform(connection, 'qireader')

    assert business_rows(connection, ('qireader_article',))['qireader_article'] == []
    connection.close()


def test_rebuild_is_idempotent():
    connection = connect(':memory:')
    record_json(connection, 'qireader.readlater.page', PAGE)
    record_json(
        connection,
        'qireader.article',
        {'content': '<p>article</p>'},
        request={
            'url': 'https://nettools3.oxyry.com/text',
            'params': {'url': 'https://example.com/a'},
        },
    )

    rebuild_platform(connection, 'qireader')
    first = business_rows(connection, TABLES)
    rebuild_platform(connection, 'qireader')
    second = business_rows(connection, TABLES)

    assert first == second
    connection.close()


def test_missing_result_rolls_back():
    connection = connect(':memory:')
    record_json(connection, 'qireader.readlater.page', {'error': 'bad'})

    with pytest.raises(ProjectionError, match='KeyError'):
        rebuild_platform(connection, 'qireader')

    assert business_rows(connection, TABLES) == {
        'qireader_article': [],
        'qireader_entry': [],
    }
    connection.close()
