"""Shared helpers for replaying raw responses into projection tables."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from db import raw


class SkipResponse(Exception):
    """An auxiliary response does not carry usable data."""


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
    """Number of raw responses replayed, rows written and errors skipped."""

    responses: int = 0
    rows: int = 0
    skipped: int = 0
    aux_missed: int = 0

    def summary(self) -> str:
        message = f'{self.responses} 个响应，{self.rows} 行'
        if self.skipped:
            message += f'，跳过 {self.skipped} 条错误响应'
        if self.aux_missed:
            message += f'，辅助未命中 {self.aux_missed} 条'
        return message


def reset_tables(connection: sqlite3.Connection, tables: tuple[str, ...]) -> None:
    """Delete a platform's projection rows in child-to-parent order."""
    for table in tables:
        connection.execute(f'DELETE FROM {table}')


def iter_json_responses(
    connection: sqlite3.Connection,
    endpoint: str,
    *,
    result: RebuildResult | None = None,
    status_ok_only: bool = True,
    skip_invalid_json: bool = False,
) -> Iterator[tuple[dict[str, Any], Any]]:
    """Yield non-error responses with a parsed JSON body.

    Transport errors and non-200 responses are skipped and counted. A 200
    response that is not valid JSON is fatal for main entities, but auxiliary
    endpoints may set ``skip_invalid_json`` to count it and continue.
    """
    for response in raw.iter_responses(connection, endpoint=endpoint):
        if _should_skip(response, status_ok_only):
            if result is not None:
                result.skipped += 1
            continue
        try:
            payload = json.loads(response['body'])
        except (TypeError, ValueError) as exc:
            if skip_invalid_json:
                skip_response(result, endpoint, response, f'invalid JSON: {exc}')
                continue
            raise ProjectionError(
                endpoint,
                response['id'],
                f'invalid JSON: {exc}',
            ) from exc
        if result is not None:
            result.responses += 1
        yield response, payload


def iter_body_responses(
    connection: sqlite3.Connection,
    endpoint: str,
    *,
    result: RebuildResult | None = None,
    status_ok_only: bool = False,
) -> Iterator[tuple[dict[str, Any], bytes]]:
    """Yield non-error responses with an undecoded body (HTML or text).

    Parsers that receive non-200 bodies can decide whether 404 means an empty
    body or another error. Transport errors are always skipped and counted.
    """
    for response in raw.iter_responses(connection, endpoint=endpoint):
        if _should_skip(response, status_ok_only):
            if result is not None:
                result.skipped += 1
            continue
        if result is not None:
            result.responses += 1
        yield response, response['body']


def skip_response(
    result: RebuildResult | None,
    endpoint: str,
    response: dict[str, Any],
    reason: str,
) -> None:
    """Count and report an auxiliary response that was not projected."""
    if result is not None:
        result.skipped += 1
    print(f'投影跳过无效响应: {endpoint} (id={response["id"]}): {reason}')


def skip_handler_response(
    result: RebuildResult | None,
    endpoint: str,
    response: dict[str, Any],
    reason: str,
) -> None:
    """Skip a response that the iterator already counted as processed."""
    if result is not None:
        result.responses -= 1
    skip_response(result, endpoint, response, reason)


def _should_skip(response: dict[str, Any], status_ok_only: bool) -> bool:
    if response['body'] is None or response.get('error'):
        return True
    return status_ok_only and response.get('status_code') != 200


def apply_handler(
    endpoint: str,
    response: dict[str, Any],
    handler: Callable[..., int],
    *args: Any,
) -> int:
    """Run a projection handler and wrap failures with response provenance."""
    try:
        return handler(*args)
    except (ProjectionError, SkipResponse):
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
