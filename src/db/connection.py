"""SQLite connection helpers for the raw sync layer."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from db.migrate import migrate

DEFAULT_DB_PATH = 'data/eto.db'


def resolve_db_path(path: str | os.PathLike[str] | None = None) -> Path:
    """Return the expanded database path."""
    return Path(path or DEFAULT_DB_PATH).expanduser()


def connect(path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    """Open the database, apply pragmas and migrations."""
    db_path = resolve_db_path(path)
    in_memory = str(db_path) == ':memory:'

    if not in_memory:
        parent_existed = db_path.parent.exists()
        db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not parent_existed:
            _chmod(db_path.parent, 0o700)

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA journal_mode = WAL')
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('PRAGMA busy_timeout = 5000')
    connection.execute('PRAGMA synchronous = NORMAL')
    migrate(connection)
    secure_database_files(connection)
    return connection


def secure_database_files(connection: sqlite3.Connection) -> None:
    """Restrict the database and SQLite sidecar files to the owner."""
    for row in connection.execute('PRAGMA database_list'):
        path = row['file'] if isinstance(row, sqlite3.Row) else row[2]
        if not path:
            continue
        for suffix in ('', '-wal', '-shm', '-journal'):
            _chmod(Path(f'{path}{suffix}'), 0o600)


def _chmod(path: Path, mode: int) -> None:
    if os.name == 'nt':
        return
    try:
        os.chmod(path, mode)
    except OSError:
        # Best effort: read-only or unusual filesystems should not block sync.
        pass
