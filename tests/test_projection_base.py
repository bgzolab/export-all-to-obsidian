from __future__ import annotations

import pytest

from db.connection import connect
from db.projections import SUPPORTED_PLATFORMS, ProjectionError, rebuild_platform
from db.projections._upsert import update_aux, upsert
from db.raw import finish_run, record_response, start_run
from tests.projection_helpers import record_json, record_missing


def _star_values(full_name: str, description: str) -> dict:
    return {
        'full_name': full_name,
        'description': description,
    }


def test_upsert_inserts_and_skips_older_responses():
    connection = connect(':memory:')
    first = record_json(connection, 'test.first', {})
    second = record_json(connection, 'test.second', {})

    assert (
        upsert(
            connection,
            'github_star',
            {'repo_id': 1},
            _star_values('owner/repo', 'new'),
            second,
            '2026-01-02T00:00:00+00:00',
        )
        == 1
    )
    created_at = connection.execute(
        'SELECT db_created_at FROM github_star WHERE repo_id = 1'
    ).fetchone()[0]

    assert (
        upsert(
            connection,
            'github_star',
            {'repo_id': 1},
            _star_values('owner/repo', 'old'),
            first,
            '2026-01-01T00:00:00+00:00',
        )
        == 0
    )
    row = connection.execute('SELECT * FROM github_star WHERE repo_id = 1').fetchone()
    assert row['description'] == 'new'
    assert row['response_id'] == second
    assert row['db_created_at'] == created_at
    connection.close()


def test_upsert_updates_newer_response_without_resetting_created_at():
    connection = connect(':memory:')
    first = record_json(connection, 'test.first', {})
    second = record_json(connection, 'test.second', {})

    upsert(
        connection,
        'github_star',
        {'repo_id': 1},
        _star_values('owner/repo', 'first'),
        first,
        '2026-01-01T00:00:00+00:00',
    )
    created_at = connection.execute(
        'SELECT db_created_at FROM github_star WHERE repo_id = 1'
    ).fetchone()[0]

    assert (
        upsert(
            connection,
            'github_star',
            {'repo_id': 1},
            _star_values('owner/repo', 'second'),
            second,
            '2026-01-02T00:00:00+00:00',
        )
        == 1
    )
    row = connection.execute('SELECT * FROM github_star WHERE repo_id = 1').fetchone()
    assert row['description'] == 'second'
    assert row['response_id'] == second
    assert row['db_created_at'] == created_at
    assert row['db_updated_at'] == '2026-01-02T00:00:00+00:00'
    connection.close()


def test_update_aux_keeps_main_provenance():
    connection = connect(':memory:')
    main = record_json(connection, 'test.main', {})
    aux = record_json(connection, 'test.aux', {})

    upsert(
        connection,
        'github_star',
        {'repo_id': 1},
        _star_values('owner/repo', 'repo'),
        main,
        '2026-01-01T00:00:00+00:00',
    )
    assert (
        update_aux(
            connection,
            'github_star',
            {'repo_id': 1},
            {'readme': '# README'},
            'readme_response_id',
            aux,
            '2026-01-02T00:00:00+00:00',
        )
        == 1
    )

    row = connection.execute('SELECT * FROM github_star WHERE repo_id = 1').fetchone()
    assert row['readme'] == '# README'
    assert row['readme_response_id'] == aux
    assert row['response_id'] == main
    assert row['db_updated_at'] == '2026-01-02T00:00:00+00:00'
    connection.close()


def test_unsupported_platform_raises():
    connection = connect(':memory:')
    assert 'bangumi' in SUPPORTED_PLATFORMS

    with pytest.raises(ValueError, match='Unsupported platform'):
        rebuild_platform(connection, 'unknown')
    connection.close()


def test_missing_body_raises_with_response_id():
    connection = connect(':memory:')
    response_id = record_missing(connection, 'bangumi.collections.page')

    with pytest.raises(ProjectionError) as error:
        rebuild_platform(connection, 'bangumi')

    assert error.value.endpoint == 'bangumi.collections.page'
    assert error.value.response_id == response_id
    assert str(response_id) in str(error.value)
    connection.close()


def test_invalid_json_raises_with_response_id():
    connection = connect(':memory:')
    run = start_run(connection, 'test', 'invalid')
    response_id = record_response(
        connection,
        run,
        endpoint='bangumi.collections.page',
        request={},
        status_code=200,
        body=b'{',
    )
    finish_run(connection, run, 'success')

    with pytest.raises(ProjectionError, match='invalid JSON'):
        rebuild_platform(connection, 'bangumi')
    assert response_id
    connection.close()
