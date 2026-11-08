"""Shared helpers for replaying raw responses into projection tables."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from db import raw


class ProjectionError(RuntimeError):
    """A raw response could not be projected."""

    def __init__(
        self,
        endpoint: str,
        response_id: int | None,
        reason: str,
    ) -> None:
        location = endpoint if response_id is None else f'{endpoint} (id={response_id})'
        super().__init__(f'projection failed for {location}: {reason}')
        self.endpoint = endpoint
        self.response_id = response_id
        self.reason = reason


@dataclass
class RebuildResult:
    """Number of raw responses replayed and projection rows written."""

    responses: int = 0
    rows: int = 0


def reset_tables(connection: sqlite3.Connection, tables: tuple[str, ...]) -> None:
    """Delete a platform's projection rows in child-to-parent order."""
    for table in tables:
        connection.execute(f'DELETE FROM {table}')


def iter_json_responses(
    connection: sqlite3.Connection,
    endpoint: str,
) -> Iterator[tuple[dict[str, Any], Any]]:
    """Yield raw responses with a parsed JSON body."""
    for response in raw.iter_responses(connection, endpoint=endpoint):
        if response['body'] is None:
            raise ProjectionError(endpoint, response['id'], 'missing response body')
        try:
            payload = json.loads(response['body'])
        except (TypeError, ValueError) as exc:
            raise ProjectionError(
                endpoint,
                response['id'],
                f'invalid JSON: {exc}',
            ) from exc
        yield response, payload


def iter_body_responses(
    connection: sqlite3.Connection,
    endpoint: str,
) -> Iterator[tuple[dict[str, Any], bytes]]:
    """Yield raw responses with an undecoded body (HTML or text)."""
    for response in raw.iter_responses(connection, endpoint=endpoint):
        if response['body'] is None:
            raise ProjectionError(endpoint, response['id'], 'missing response body')
        yield response, response['body']


def apply_handler(
    endpoint: str,
    response: dict[str, Any],
    handler: Callable[..., int],
    *args: Any,
) -> int:
    """Run a projection handler and wrap failures with response provenance."""
    try:
        return handler(*args)
    except ProjectionError:
        raise
    except Exception as exc:
        raise ProjectionError(
            endpoint,
            response['id'],
            f'{type(exc).__name__}: {exc}',
        ) from exc


def upsert(
    connection: sqlite3.Connection,
    table: str,
    key: dict[str, Any],
    values: dict[str, Any],
    response_id: int,
    now: str,
) -> int:
    """Insert a projection row or update it when the response is newer."""
    columns = [*key, *values, 'response_id', 'db_created_at', 'db_updated_at']
    placeholders = ', '.join('?' for _ in columns)
    conflict_columns = ', '.join(key)
    updated_columns = [*values, 'response_id', 'db_updated_at']
    updates = ', '.join(f'{column} = excluded.{column}' for column in updated_columns)
    sql = (
        f'INSERT INTO {table} ({", ".join(columns)}) VALUES ({placeholders}) '
        f'ON CONFLICT ({conflict_columns}) DO UPDATE SET {updates} '
        f'WHERE excluded.response_id > {table}.response_id'
    )
    params = [*key.values(), *values.values(), response_id, now, now]
    return connection.execute(sql, params).rowcount


def update_aux(
    connection: sqlite3.Connection,
    table: str,
    key: dict[str, Any],
    values: dict[str, Any],
    aux_response_column: str,
    response_id: int,
    now: str,
) -> int:
    """Update auxiliary columns without touching the main provenance row."""
    assignments = [f'{column} = ?' for column in values]
    assignments.extend([f'{aux_response_column} = ?', 'db_updated_at = ?'])
    conditions = ' AND '.join(f'{column} = ?' for column in key)
    sql = f'UPDATE {table} SET {", ".join(assignments)} WHERE {conditions}'
    params = [*values.values(), response_id, now, *key.values()]
    return connection.execute(sql, params).rowcount


def json_dumps(value: Any) -> str:
    """Serialize a nested projection value for a JSON column."""
    return json.dumps(value, ensure_ascii=False)


def json_or_null(value: Any) -> str | None:
    """Serialize JSON columns that allow NULL."""
    if value is None:
        return None
    return json_dumps(value)


def request_payload(response: dict[str, Any]) -> dict[str, Any]:
    """Return the recorded request metadata for a raw response."""
    request = response.get('request')
    if not request:
        return {}
    if isinstance(request, dict):
        return request
    try:
        value = json.loads(request)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}
