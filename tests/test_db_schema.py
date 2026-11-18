from __future__ import annotations

import os
import sqlite3
import stat

import pytest

from db.connection import DEFAULT_DB_PATH, connect
from db.migrate import MIGRATIONS_DIR, migrate
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
    assert {'twitter_tweet', 'twitter_like', 'twitter_bookmark'} <= tables
    assert {
        'idx_sync_response_run',
        'idx_sync_response_lookup',
        'idx_sync_response_sha256',
    } <= indexes
    assert connection.execute('PRAGMA user_version').fetchone()[0] == 4
    assert connection.execute('PRAGMA foreign_keys').fetchone()[0] == 1

    columns = {row['name'] for row in connection.execute('PRAGMA table_info(sync_run)')}
    assert 'command' in columns
    connection.close()


def test_connect_is_idempotent(tmp_path):
    db_path = tmp_path / 'eto.db'
    connection = connect(db_path)
    migrate(connection)
    migrate(connection)

    assert connection.execute('PRAGMA user_version').fetchone()[0] == 4
    connection.close()


def test_migration_backfills_existing_tweets_as_likes(tmp_path):
    db_path = tmp_path / 'eto.db'
    layer2 = sqlite3.connect(db_path)
    layer2.row_factory = sqlite3.Row
    layer2.execute('PRAGMA foreign_keys = ON')
    layer2.executescript(
        (MIGRATIONS_DIR / '001_raw_layer.sql').read_text(encoding='utf-8')
    )
    layer2.executescript(
        (MIGRATIONS_DIR / '002_projection_layer.sql').read_text(encoding='utf-8')
    )
    layer2.execute('PRAGMA user_version = 2')
    layer2.execute(
        'INSERT INTO sync_run (platform, operation, started_at, status) '
        "VALUES ('twitter', 'likes', '2026-01-01T00:00:00+00:00', 'success')"
    )
    layer2.execute(
        'INSERT INTO sync_response (run_id, endpoint, fetched_at) '
        "VALUES (1, 'twitter.likes.page', '2026-01-01T00:00:00+00:00')"
    )
    layer2.execute(
        'INSERT INTO twitter_tweet '
        '(tweet_id, author_json, response_id, db_created_at, db_updated_at) '
        "VALUES ('111', '{}', 1, 'created', 'updated')"
    )
    layer2.commit()
    layer2.close()

    connection = connect(db_path)

    assert connection.execute('PRAGMA user_version').fetchone()[0] == 4
    like = connection.execute('SELECT * FROM twitter_like').fetchone()
    assert like['tweet_id'] == '111'
    assert like['response_id'] == 1
    assert like['db_created_at'] == 'created'
    assert like['db_updated_at'] == 'updated'
    assert (
        connection.execute('SELECT count(*) FROM twitter_bookmark').fetchone()[0] == 0
    )
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
