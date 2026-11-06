"""Import existing Markdown files into the raw response table."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from db import raw

ENDPOINT = 'import.markdown'


def import_markdown(
    connection: sqlite3.Connection,
    directory: str | Path,
    command: str | None = None,
) -> dict[str, int]:
    """Store every Markdown file under directory as a raw response."""
    root = Path(directory)
    if not root.is_dir():
        raise ValueError(f'Not a directory: {directory}')

    run_id = raw.start_run(
        connection,
        platform='local',
        operation='import.markdown',
        scope=str(root),
        command=command,
    )
    existing = _existing_paths(connection)
    stats = {'imported': 0, 'skipped': 0, 'failed': 0}

    for path in sorted(root.rglob('*.md')):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        try:
            body = path.read_bytes()
        except OSError as exc:
            stats['failed'] += 1
            raw.record_error(
                connection,
                run_id,
                endpoint=ENDPOINT,
                request={'path': relative},
                error=f'{type(exc).__name__}: {exc}',
            )
            continue

        digest = hashlib.sha256(body).hexdigest()
        if (relative, digest) in existing:
            stats['skipped'] += 1
            continue

        raw.record_response(
            connection,
            run_id,
            endpoint=ENDPOINT,
            request={'path': relative, 'size': len(body)},
            status_code=None,
            body=body,
        )
        existing.add((relative, digest))
        stats['imported'] += 1

    status = 'partial' if stats['failed'] else 'success'
    raw.finish_run(connection, run_id, status)
    return {'run_id': run_id, **stats}


def _existing_paths(connection: sqlite3.Connection) -> set[tuple[str, str]]:
    rows = connection.execute(
        'SELECT request, sha256 FROM sync_response WHERE endpoint = ?',
        (ENDPOINT,),
    )
    existing: set[tuple[str, str]] = set()
    for row in rows:
        try:
            request = json.loads(row['request'])
        except (TypeError, ValueError):
            continue
        path = request.get('path') if isinstance(request, dict) else None
        if path and row['sha256']:
            existing.add((path, row['sha256']))
    return existing
