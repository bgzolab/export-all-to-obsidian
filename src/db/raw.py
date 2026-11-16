"""Persist sync runs and raw responses."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

VALID_RUN_STATUSES = {'success', 'partial', 'failed'}


def utc_now() -> str:
    """Return a UTC ISO 8601 timestamp."""
    return datetime.now(UTC).isoformat(timespec='seconds')


def start_run(
    connection: sqlite3.Connection,
    platform: str,
    operation: str,
    scope: str | None = None,
    command: str | None = None,
) -> int:
    """Insert a running sync run and return its id."""
    cursor = connection.execute(
        'INSERT INTO sync_run '
        '(platform, operation, scope, command, started_at, status) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (platform, operation, scope, command, utc_now(), 'running'),
    )
    connection.commit()
    return int(cursor.lastrowid)


def finish_run(
    connection: sqlite3.Connection,
    run_id: int,
    status: str,
    error: str | None = None,
) -> None:
    """Finish a sync run with a final status."""
    if status not in VALID_RUN_STATUSES:
        raise ValueError(f'Invalid run status: {status}')
    connection.execute(
        'UPDATE sync_run SET finished_at = ?, status = ?, error = ? WHERE id = ?',
        (utc_now(), status, error, run_id),
    )
    connection.commit()


def record_response(
    connection: sqlite3.Connection,
    run_id: int,
    endpoint: str,
    request: Any,
    status_code: int | None,
    body: bytes | str | None,
    error: str | None = None,
) -> int:
    """Store one response body, compressed, and return its id."""
    raw_body = body.encode('utf-8') if isinstance(body, str) else body
    compressed = zlib.compress(raw_body, level=6) if raw_body is not None else None
    digest = hashlib.sha256(raw_body).hexdigest() if raw_body is not None else None

    cursor = connection.execute(
        'INSERT INTO sync_response '
        '(run_id, endpoint, request, status_code, fetched_at, body, sha256, error) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (
            run_id,
            endpoint,
            _encode_request(request),
            status_code,
            utc_now(),
            compressed,
            digest,
            error,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def record_error(
    connection: sqlite3.Connection,
    run_id: int,
    endpoint: str,
    request: Any,
    error: str,
) -> int:
    """Store a transport error without a response body."""
    return record_response(
        connection,
        run_id,
        endpoint,
        request,
        status_code=None,
        body=None,
        error=error,
    )


def iter_responses(
    connection: sqlite3.Connection,
    endpoint: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield responses in observation order with decompressed bodies."""
    sql = 'SELECT * FROM sync_response'
    params: list[Any] = []
    if endpoint is not None:
        sql += ' WHERE endpoint = ?'
        params.append(endpoint)
    sql += ' ORDER BY fetched_at, id'

    for row in connection.execute(sql, params):
        item = dict(row)
        item['body'] = _decompress_body(item['body'])
        yield item


def latest_response(
    connection: sqlite3.Connection,
    endpoint: str,
    *,
    scope: str | None = None,
) -> dict[str, Any] | None:
    """Return the newest response for an endpoint with a decompressed body.

    ``scope`` joins ``sync_run`` so a caller can exclude responses from other
    run scopes. Bookmark resume checkpoints rely on this to ignore incremental
    runs that always restart from the top of the list.
    """
    sql = 'SELECT sync_response.* FROM sync_response'
    params: list[Any] = []
    if scope is not None:
        sql += ' JOIN sync_run ON sync_run.id = sync_response.run_id'
    sql += ' WHERE sync_response.endpoint = ?'
    params.append(endpoint)
    if scope is not None:
        sql += ' AND sync_run.scope = ?'
        params.append(scope)
    sql += ' ORDER BY sync_response.id DESC LIMIT 1'

    row = connection.execute(sql, params).fetchone()
    if row is None:
        return None
    item = dict(row)
    item['body'] = _decompress_body(item['body'])
    return item


def _decompress_body(body: bytes | None) -> bytes | None:
    """Decompress a stored body while preserving missing transport responses."""
    return zlib.decompress(body) if body is not None else None


def _encode_request(request: Any) -> str | None:
    if request is None:
        return None
    if isinstance(request, str):
        return request
    return json.dumps(request, ensure_ascii=False, default=str)
