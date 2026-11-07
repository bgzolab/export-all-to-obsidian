from __future__ import annotations

import os
import sqlite3
import stat

import pytest

from db.connection import DEFAULT_DB_PATH, connect
from db.migrate import migrate
from db.raw import record_response, start_run


def test_default_database_path_is_project_data():
    assert DEFAULT_DB_PATH == 'data/eto.db'


def test_connect_creates_raw_tables_and_indexes(tmp_path):
    db_path = tmp_path / 'nested' / 'eto.db'
    connection = connect(db_path)

    tables = {
        row['name']
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    indexes = {
        row['name']
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }

    assert {'sync_run', 'sync_response'} <= tables
    assert {
        'idx_sync_response_run',
        'idx_sync_response_lookup',
        'idx_sync_response_sha256',
    } <= indexes
    assert connection.execute('PRAGMA user_version').fetchone()[0] == 1
    assert connection.execute('PRAGMA foreign_keys').fetchone()[0] == 1

    columns = {row['name'] for row in connection.execute('PRAGMA table_info(sync_run)')}
    assert 'command' in columns
    connection.close()


def test_connect_is_idempotent(tmp_path):
    db_path = tmp_path / 'eto.db'
    connection = connect(db_path)
    migrate(connection)
    migrate(connection)

    assert connection.execute('PRAGMA user_version').fetchone()[0] == 1
    connection.close()


def test_connect_restricts_database_permissions(tmp_path):
    if os.name == 'nt':
        return

    db_path = tmp_path / 'private' / 'eto.db'
    connection = connect(db_path)
    run_id = start_run(connection, 'test', 'permissions')
    record_response(
        connection,
        run_id,
        endpoint='test.page',
        request={},
        status_code=200,
        body=b'data',
    )

    for suffix in ('', '-wal', '-shm'):
        path = db_path.with_name(db_path.name + suffix)
        if path.exists():
            assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0
    connection.close()

    assert stat.S_IMODE(db_path.stat().st_mode) & 0o077 == 0
    assert stat.S_IMODE(db_path.parent.stat().st_mode) & 0o077 == 0


def test_connect_supports_memory_database():
    connection = connect(':memory:')
    tables = {
        row['name']
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {'sync_run', 'sync_response'} <= tables
    connection.close()


def test_connect_default_path_uses_current_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    connection = connect()
    connection.close()

    assert (tmp_path / 'data' / 'eto.db').exists()


def test_connect_does_not_chmod_existing_parent(tmp_path):
    if os.name == 'nt':
        return

    parent = tmp_path / 'notes'
    parent.mkdir()
    os.chmod(parent, 0o755)
    connection = connect(parent / 'eto.db')
    connection.close()

    assert stat.S_IMODE(parent.stat().st_mode) == 0o755


def test_migrate_rolls_back_failed_migration(tmp_path, monkeypatch):
    migrations = tmp_path / 'migrations'
    migrations.mkdir()
    (migrations / '001_bad.sql').write_text(
        'CREATE TABLE ok (id INTEGER);\nALTER TABLE missing ADD COLUMN value TEXT;\n',
        encoding='utf-8',
    )
    monkeypatch.setattr('db.migrate.MIGRATIONS_DIR', migrations)

    connection = sqlite3.connect(tmp_path / 'broken.db')
    try:
        with pytest.raises(sqlite3.OperationalError):
            migrate(connection)
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 0
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert 'ok' not in tables
    finally:
        connection.close()
