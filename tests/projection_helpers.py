"""Helpers for projection tests."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from db.raw import finish_run, record_error, record_response, start_run


def record_json(
    connection: sqlite3.Connection,
    endpoint: str,
    payload: Any,
    request: Any = None,
    status_code: int = 200,
) -> int:
    return _record(
        connection,
        endpoint,
        body=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        request=request,
        status_code=status_code,
    )


def record_text(
    connection: sqlite3.Connection,
    endpoint: str,
    text: str,
    request: Any = None,
    status_code: int = 200,
) -> int:
    return _record(
        connection,
        endpoint,
        body=text.encode('utf-8'),
        request=request,
        status_code=status_code,
    )


def record_missing(
    connection: sqlite3.Connection,
    endpoint: str,
    request: Any = None,
) -> int:
    run_id = start_run(connection, 'test', endpoint)
    response_id = record_error(
        connection,
        run_id,
        endpoint=endpoint,
        request=request,
        error='transport failed',
    )
    finish_run(connection, run_id, 'success')
    return response_id


def _record(
    connection: sqlite3.Connection,
    endpoint: str,
    *,
    body: bytes,
    request: Any,
    status_code: int,
) -> int:
    run_id = start_run(connection, 'test', endpoint)
    response_id = record_response(
        connection,
        run_id,
        endpoint=endpoint,
        request=request or {},
        status_code=status_code,
        body=body,
    )
    finish_run(connection, run_id, 'success')
    return response_id


def rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [
        dict(row) for row in connection.execute(f'SELECT * FROM {table} ORDER BY rowid')
    ]


def business_rows(
    connection: sqlite3.Connection,
    tables: tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    """Return rows without the database-managed timestamp columns."""
    result = {}
    for table in tables:
        result[table] = [
            {
                key: value
                for key, value in row.items()
                if key not in {'db_created_at', 'db_updated_at'}
            }
            for row in rows(connection, table)
        ]
    return result
