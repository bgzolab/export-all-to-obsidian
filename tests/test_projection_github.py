from __future__ import annotations

import base64
import json

from db.connection import connect
from db.projections import rebuild_platform
from tests.projection_helpers import business_rows, record_json, record_text

TABLES = ('github_star',)

STAR = {
    'starred_at': '2026-05-23T00:00:00Z',
    'repo': {
        'id': 123,
        'full_name': 'octocat/Hello-World',
        'html_url': 'https://github.com/octocat/Hello-World',
        'description': 'Demo',
        'name': 'Hello-World',
        'owner': {'login': 'octocat'},
        'language': 'Python',
        'topics': ['demo'],
        'stargazers_count': 1,
        'forks_count': 2,
        'open_issues_count': 3,
        'fork': False,
        'archived': False,
        'private': False,
        'homepage': '',
        'license': {'spdx_id': 'MIT'},
        'created_at': '2020-01-01T00:00:00Z',
        'updated_at': '2020-01-02T00:00:00Z',
        'pushed_at': '2020-01-03T00:00:00Z',
    },
}


def test_rebuild_projects_stars_and_readmes():
    connection = connect(':memory:')
    stars_response = record_json(connection, 'github.stars.list', [STAR])
    readme_response = record_text(
        connection,
        'github.repo.readme',
        '# README',
        request={'url': 'https://api.github.com/repos/octocat/Hello-World/readme'},
    )

    result = rebuild_platform(connection, 'github')

    row = connection.execute('SELECT * FROM github_star').fetchone()
    assert row['repo_id'] == 123
    assert row['full_name'] == 'octocat/Hello-World'
    assert row['owner_login'] == 'octocat'
    assert row['license'] == 'MIT'
    assert json.loads(row['topics_json']) == ['demo']
    assert row['fork'] == 0
    assert row['starred_at'] == '2026-05-23T00:00:00Z'
    assert row['readme'] == '# README'
    assert row['readme_response_id'] == readme_response
    assert row['response_id'] == stars_response
    assert result.responses == 2
    assert result.rows == 2
    connection.close()


def test_readme_json_payload_is_decoded():
    connection = connect(':memory:')
    record_json(connection, 'github.stars.list', [STAR])
    encoded = base64.b64encode(b'# Decoded').decode()
    record_json(
        connection,
        'github.repo.readme',
        {'content': encoded},
        request={'url': 'https://api.github.com/repos/octocat/Hello-World/readme'},
    )

    rebuild_platform(connection, 'github')

    assert connection.execute('SELECT readme FROM github_star').fetchone()[0] == (
        '# Decoded'
    )
    connection.close()


def test_repository_rename_updates_the_same_row():
    connection = connect(':memory:')
    record_json(connection, 'github.stars.list', [STAR])
    renamed = json.loads(json.dumps(STAR))
    renamed['repo']['full_name'] = 'octocat/Renamed'
    record_json(connection, 'github.stars.list', [renamed])

    rebuild_platform(connection, 'github')

    rows = business_rows(connection, TABLES)['github_star']
    assert len(rows) == 1
    assert rows[0]['repo_id'] == 123
    assert rows[0]['full_name'] == 'octocat/Renamed'
    connection.close()


def test_unexpected_readme_status_is_skipped():
    connection = connect(':memory:')
    record_json(connection, 'github.stars.list', [STAR])
    record_text(
        connection,
        'github.repo.readme',
        'error',
        request={'url': 'https://api.github.com/repos/octocat/Hello-World/readme'},
        status_code=500,
    )

    result = rebuild_platform(connection, 'github')

    assert result.skipped == 1
    assert connection.execute('SELECT readme FROM github_star').fetchone()[0] == ''
    connection.close()


def test_readme_without_star_is_reported(capsys):
    connection = connect(':memory:')
    record_text(
        connection,
        'github.repo.readme',
        '# README',
        request={'url': 'https://api.github.com/repos/octocat/Hello-World/readme'},
    )

    result = rebuild_platform(connection, 'github')

    assert result.rows == 0
    assert '辅助数据未命中主行' in capsys.readouterr().out
    connection.close()


def test_rebuild_is_idempotent():
    connection = connect(':memory:')
    record_json(connection, 'github.stars.list', [STAR])
    record_text(
        connection,
        'github.repo.readme',
        '# README',
        request={'url': 'https://api.github.com/repos/octocat/Hello-World/readme'},
    )

    rebuild_platform(connection, 'github')
    first = business_rows(connection, TABLES)
    rebuild_platform(connection, 'github')
    second = business_rows(connection, TABLES)

    assert first == second
    connection.close()
