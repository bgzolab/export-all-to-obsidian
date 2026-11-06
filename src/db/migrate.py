"""Apply numbered SQL migrations from the migrations directory."""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).with_name('migrations')


def migrate(connection: sqlite3.Connection) -> None:
    """Apply every migration newer than PRAGMA user_version."""
    current = int(connection.execute('PRAGMA user_version').fetchone()[0])
    for path in sorted(MIGRATIONS_DIR.glob('*.sql')):
        version = _migration_version(path)
        if version <= current:
            continue
        connection.executescript(path.read_text(encoding='utf-8'))
        connection.execute(f'PRAGMA user_version = {version}')
        connection.commit()
        current = version


def _migration_version(path: Path) -> int:
    prefix = path.stem.split('_', 1)[0]
    if not prefix.isdigit():
        raise ValueError(f'Invalid migration filename: {path.name}')
    return int(prefix)
