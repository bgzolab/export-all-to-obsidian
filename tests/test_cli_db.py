from __future__ import annotations

import sqlite3

from click.testing import CliRunner

from app.credential_guard import CredentialProbeResult
from export_to_obsidian import eto


def _invoke_cnblog(monkeypatch, db_path: str | None):
    monkeypatch.setattr(
        'app.cli.probe_cnblog_credentials',
        lambda: CredentialProbeResult.valid('cnblog'),
    )
    monkeypatch.setattr('app.cli.export_cnblog', lambda output, index_writer: None)
    args = (['--db', db_path] if db_path else []) + [
        'cnblog',
        '-o',
        'output/cnblog',
    ]
    return CliRunner().invoke(eto, args)


def _query_one(db_path, sql, params=()):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(sql, params).fetchone()
    finally:
        connection.close()


def test_cli_db_explicit_path_creates_run_with_command(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    monkeypatch.setattr(
        'app.context.sys.argv',
        ['eto', '--db', db_path, 'cnblog', '-o', 'output/cnblog'],
    )

    result = _invoke_cnblog(monkeypatch, db_path)

    assert result.exit_code == 0, result.output
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['platform'] == 'cnblog'
    assert run['operation'] == 'bookmarks'
    assert run['status'] == 'success'
    assert run['command'].startswith('eto --db')


def test_cli_db_default_path(monkeypatch, tmp_path):
    default_db = tmp_path / 'default' / 'eto.db'
    monkeypatch.setattr('db.connection.DEFAULT_DB_PATH', str(default_db))

    result = _invoke_cnblog(monkeypatch, None)

    assert result.exit_code == 0, result.output
    assert default_db.exists()


def test_cli_db_directory_is_rejected(monkeypatch, tmp_path):
    result = _invoke_cnblog(monkeypatch, str(tmp_path))

    assert result.exit_code == 1
    assert 'Database path is a directory' in result.output


def test_cli_db_help_lists_option():
    result = CliRunner().invoke(eto, ['--help'])

    assert result.exit_code == 0
    assert '--db' in result.output


def test_cli_marks_run_partial(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')

    def fake_export(output, index_writer):
        from app.context import mark_run_partial

        mark_run_partial()

    monkeypatch.setattr(
        'app.cli.probe_cnblog_credentials',
        lambda: CredentialProbeResult.valid('cnblog'),
    )
    monkeypatch.setattr('app.cli.export_cnblog', fake_export)

    result = CliRunner().invoke(
        eto,
        ['--db', db_path, 'cnblog', '-o', 'output/cnblog'],
    )

    assert result.exit_code == 0, result.output
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'partial'


def test_cli_marks_run_failed_on_exception(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')

    def fake_export(output, index_writer):
        raise RuntimeError('boom')

    monkeypatch.setattr(
        'app.cli.probe_cnblog_credentials',
        lambda: CredentialProbeResult.valid('cnblog'),
    )
    monkeypatch.setattr('app.cli.export_cnblog', fake_export)

    result = CliRunner().invoke(
        eto,
        ['--db', db_path, 'cnblog', '-o', 'output/cnblog'],
    )

    assert result.exit_code != 0
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'failed'
    assert 'RuntimeError: boom' in run['error']


def test_cli_import_markdown(tmp_path):
    db_path = str(tmp_path / 'eto.db')
    vault = tmp_path / 'vault'
    vault.mkdir()
    (vault / 'a.md').write_text('# A\n', encoding='utf-8')

    runner = CliRunner()
    first = runner.invoke(eto, ['--db', db_path, 'import-markdown', str(vault)])
    second = runner.invoke(eto, ['--db', db_path, 'import-markdown', str(vault)])

    assert first.exit_code == 0, first.output
    assert '导入完成: 1 个' in first.output
    assert second.exit_code == 0, second.output
    assert '跳过 1 个' in second.output


def test_twitter_failure_marks_run_partial(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    monkeypatch.setattr(
        'app.cli.probe_twitter_credentials',
        lambda: CredentialProbeResult.valid('twitter'),
    )
    monkeypatch.setattr('twitter.exporter.TwitterClient', lambda: object())

    def fail(*args, **kwargs):
        raise RuntimeError('network down')

    monkeypatch.setattr('twitter.exporter.get_twitter_like_list', fail)

    result = CliRunner().invoke(
        eto,
        [
            '--db',
            db_path,
            'twitter',
            '-o',
            str(tmp_path / 'output'),
            '--max-pages',
            '1',
        ],
    )

    assert result.exit_code == 0, result.output
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'partial'
