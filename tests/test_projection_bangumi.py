from __future__ import annotations

import json

import pytest

from db.connection import connect
from db.projections import ProjectionError, rebuild_platform
from db.raw import finish_run, record_response, start_run
from tests.projection_helpers import (
    business_rows,
    record_json,
    record_missing,
    rows,
)

TABLES = ('bangumi_collection', 'bangumi_subject')

SUBJECT = {
    'id': 1,
    'date': '2020-01-01',
    'platform': 'TV',
    'images': {'small': 's', 'grid': 'g', 'large': 'l', 'medium': 'm', 'common': 'c'},
    'summary': 'summary',
    'name': 'Subject',
    'name_cn': '条目',
    'tags': [{'name': '科幻', 'count': 3, 'total_count': 10}],
    'infobox': [{'key': '别名', 'value': 'Alias'}],
    'rating': {'rank': 10, 'total': 100, 'count': {'1': 1}, 'score': 8.0},
    'total_episodes': 12,
    'collection': {
        'wish': 1,
        'collect': 2,
        'doing': 3,
        'on_hold': 0,
        'dropped': 0,
        'total': 6,
    },
    'eps': 12,
    'meta_tags': ['TV'],
    'volumes': 3,
    'series': False,
    'locked': False,
    'nsfw': False,
    'type': 2,
    'redirect': None,
}

COLLECTION = {
    'subject_id': 1,
    'id': 1001,
    'updated_at': '2026-01-02T03:04:05+08:00',
    'comment': 'nice',
    'tags': ['tag1'],
    'vol_status': 1,
    'ep_status': 2,
    'subject_type': 2,
    'rate': 8,
    'type': 3,
    'private': False,
    'subject': {
        'id': 1,
        'date': '2020-01-01',
        'images': {'small': 's'},
        'name': 'Subject',
        'name_cn': '条目',
        'short_summary': 'summary',
        'tags': [],
        'score': 8.0,
        'type': 2,
        'eps': 12,
        'volumes': 3,
        'collection_total': 6,
        'rank': 10,
    },
}

CHARACTERS = [
    {
        'id': 10,
        'name': 'Char',
        'relation': '主角',
        'images': {'small': 's'},
        'actors': [{'id': 20, 'name': 'Actor'}],
        'type': 1,
    }
]


def _seed(connection) -> tuple[int, int, int]:
    collection_id = record_json(
        connection,
        'bangumi.collections.page',
        {'data': [COLLECTION]},
    )
    subject_id = record_json(connection, 'bangumi.subject.detail', SUBJECT)
    characters_id = record_json(
        connection,
        'bangumi.subject.characters',
        CHARACTERS,
        request={'url': 'https://api.bgm.tv/v0/subjects/1/characters'},
    )
    return collection_id, subject_id, characters_id


def test_rebuild_projects_collections_subjects_and_characters():
    connection = connect(':memory:')
    collection_response, subject_response, characters_response = _seed(connection)

    result = rebuild_platform(connection, 'bangumi')

    collection = rows(connection, 'bangumi_collection')[0]
    assert collection['subject_id'] == 1
    assert collection['collection_id'] == 1001
    assert collection['updated_at'] == '2026-01-02T03:04:05+08:00'
    assert collection['comment'] == 'nice'
    assert json.loads(collection['tags_json']) == ['tag1']
    assert collection['subject_type'] == 2
    assert collection['type'] == 3
    assert collection['private'] == 0
    assert json.loads(collection['subject_json'])['id'] == 1
    assert collection['response_id'] == collection_response

    subject = rows(connection, 'bangumi_subject')[0]
    assert subject['subject_id'] == 1
    assert subject['date'] == '2020-01-01'
    assert subject['name'] == 'Subject'
    assert subject['name_cn'] == '条目'
    assert subject['type_id'] == 2
    assert subject['series'] == 0
    assert subject['locked'] == 0
    assert subject['nsfw'] == 0
    assert json.loads(subject['tags_json'])[0]['total_count'] == 10
    assert json.loads(subject['characters_json']) == CHARACTERS
    assert subject['characters_response_id'] == characters_response
    assert subject['response_id'] == subject_response

    assert result.responses == 3
    assert result.rows == 3
    connection.close()


def test_rebuild_is_idempotent_except_database_timestamps():
    connection = connect(':memory:')
    _seed(connection)

    rebuild_platform(connection, 'bangumi')
    first = business_rows(connection, TABLES)
    rebuild_platform(connection, 'bangumi')
    second = business_rows(connection, TABLES)

    assert first == second
    connection.close()


def test_missing_collection_id_is_null():
    connection = connect(':memory:')
    collection = dict(COLLECTION)
    collection.pop('id')
    record_json(connection, 'bangumi.collections.page', {'data': [collection]})

    rebuild_platform(connection, 'bangumi')

    assert rows(connection, 'bangumi_collection')[0]['collection_id'] is None
    connection.close()


def test_characters_update_keeps_subject_provenance(monkeypatch):
    connection = connect(':memory:')
    _, subject_response, characters_response = _seed(connection)

    monkeypatch.setattr(
        'db.projections.bangumi.raw.utc_now',
        lambda: '2026-01-01T00:00:00+00:00',
    )
    rebuild_platform(connection, 'bangumi')
    first = rows(connection, 'bangumi_subject')[0]
    assert first['response_id'] == subject_response
    assert first['characters_response_id'] == characters_response
    assert first['db_updated_at'] == '2026-01-01T00:00:00+00:00'

    monkeypatch.setattr(
        'db.projections.bangumi.raw.utc_now',
        lambda: '2026-02-01T00:00:00+00:00',
    )
    rebuild_platform(connection, 'bangumi')
    second = rows(connection, 'bangumi_subject')[0]
    assert second['response_id'] == subject_response
    assert second['characters_response_id'] == characters_response
    assert second['db_updated_at'] == '2026-02-01T00:00:00+00:00'
    connection.close()


def test_bad_json_rolls_back_projection_table():
    connection = connect(':memory:')
    _seed(connection)
    rebuild_platform(connection, 'bangumi')
    before = business_rows(connection, TABLES)

    run_id = start_run(connection, 'test', 'invalid')
    record_response(
        connection,
        run_id,
        endpoint='bangumi.subject.detail',
        request={},
        status_code=200,
        body=b'{',
    )
    finish_run(connection, run_id, 'success')

    with pytest.raises(ProjectionError, match='invalid JSON'):
        rebuild_platform(connection, 'bangumi')

    assert business_rows(connection, TABLES) == before
    connection.close()


def test_missing_body_is_skipped_without_losing_rows():
    connection = connect(':memory:')
    _seed(connection)
    rebuild_platform(connection, 'bangumi')
    before = business_rows(connection, TABLES)

    record_missing(connection, 'bangumi.collections.page')

    result = rebuild_platform(connection, 'bangumi')

    assert result.skipped == 1
    assert business_rows(connection, TABLES) == before
    connection.close()


def test_invalid_characters_payload_is_skipped():
    connection = connect(':memory:')
    record_json(connection, 'bangumi.subject.detail', SUBJECT)
    record_json(
        connection,
        'bangumi.subject.characters',
        {'success': False, 'message': 'auth required'},
        request={'url': 'https://api.bgm.tv/v0/subjects/1/characters'},
    )

    result = rebuild_platform(connection, 'bangumi')

    assert result.skipped == 1
    subject = connection.execute('SELECT * FROM bangumi_subject').fetchone()
    assert subject['characters_json'] == '[]'
    assert subject['characters_response_id'] is None
    connection.close()


def test_characters_without_subject_are_reported(capsys):
    connection = connect(':memory:')
    record_json(
        connection,
        'bangumi.subject.characters',
        CHARACTERS,
        request={'url': 'https://api.bgm.tv/v0/subjects/1/characters'},
    )

    result = rebuild_platform(connection, 'bangumi')

    assert result.rows == 0
    assert result.aux_missed == 1
    assert '辅助未命中 1 条' in result.summary()
    assert '辅助数据未命中主行' in capsys.readouterr().out
    connection.close()


def test_null_collection_page_is_empty():
    connection = connect(':memory:')
    record_json(connection, 'bangumi.collections.page', {'data': None})

    result = rebuild_platform(connection, 'bangumi')

    assert result.rows == 0
    assert (
        business_rows(connection, ('bangumi_collection',))['bangumi_collection'] == []
    )
    connection.close()
