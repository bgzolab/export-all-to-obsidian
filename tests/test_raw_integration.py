from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from click.testing import CliRunner

from export_to_obsidian import eto


class FakeResponse:
    def __init__(self, payload=None, text='', content_type='application/json'):
        self.status_code = 200
        self._payload = payload
        self.text = text
        self.headers = {'Content-Type': content_type}
        if payload is not None:
            self.content = json.dumps(payload).encode()
        else:
            self.content = text.encode()

    def json(self):
        return self._payload


def test_github_cli_records_raw_responses(monkeypatch, tmp_path):
    star = {
        'starred_at': '2026-05-23T00:00:00Z',
        'repo': {
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

    def make_response(url):
        if 'readme' in url:
            return FakeResponse(text='# README', content_type='text/plain')
        page = int(parse_qs(urlparse(url).query).get('page', ['1'])[0])
        return FakeResponse(payload=[star] if page == 1 else [])

    class FakeSession:
        def __init__(self):
            self.headers = {}

        def request(self, method, url, **kwargs):
            return make_response(url)

    monkeypatch.setenv('GITHUB_TOKEN', 'secret-token')
    monkeypatch.setattr('github.client.requests.Session', FakeSession)

    db_path = tmp_path / 'eto.db'
    output_dir = tmp_path / 'output'
    result = CliRunner().invoke(
        eto,
        [
            '--db',
            str(db_path),
            'github',
            '-t',
            str(Path('config/template/github.md')),
            '-o',
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    run = connection.execute('SELECT * FROM sync_run').fetchone()
    assert run['status'] == 'success'
    rows = connection.execute(
        'SELECT endpoint, request FROM sync_response ORDER BY id'
    ).fetchall()
    endpoints = [row['endpoint'] for row in rows]
    assert endpoints.count('github.stars.list') == 2
    assert endpoints.count('github.repo.readme') == 1
    for row in rows:
        headers = json.loads(row['request'])['headers']
        assert headers['Authorization'] == '[REDACTED]'
    connection.close()
