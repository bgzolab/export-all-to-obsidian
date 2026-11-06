"""HTTP requests with optional raw-response recording."""

from __future__ import annotations

import sqlite3
from typing import Any

import click
import requests

from db import raw

REDACTED = '[REDACTED]'
REDACT_HEADERS = {'cookie', 'authorization'}


def get(
    session: requests.Session,
    url: str,
    *,
    endpoint: str,
    database: sqlite3.Connection | None = None,
    run_id: int | None = None,
    **kwargs: Any,
) -> requests.Response:
    """GET a URL and record the raw response when a sync run is active."""
    return request(
        session,
        'GET',
        url,
        endpoint=endpoint,
        database=database,
        run_id=run_id,
        **kwargs,
    )


def post(
    session: requests.Session,
    url: str,
    *,
    endpoint: str,
    database: sqlite3.Connection | None = None,
    run_id: int | None = None,
    **kwargs: Any,
) -> requests.Response:
    """POST a URL and record the raw response when a sync run is active."""
    return request(
        session,
        'POST',
        url,
        endpoint=endpoint,
        database=database,
        run_id=run_id,
        **kwargs,
    )


def request(
    session: requests.Session,
    method: str,
    url: str,
    *,
    endpoint: str,
    database: sqlite3.Connection | None = None,
    run_id: int | None = None,
    **kwargs: Any,
) -> requests.Response:
    """Send a request and persist its raw response before returning it."""
    if database is None or run_id is None:
        context_database, context_run = _active_run()
        database = database or context_database
        run_id = run_id or context_run

    request_info = _request_info(session, method, url, kwargs)
    if database is None or run_id is None:
        return session.request(method, url, **kwargs)

    try:
        response = session.request(method, url, **kwargs)
    except Exception as exc:
        raw.record_error(
            database,
            run_id,
            endpoint=endpoint,
            request=request_info,
            error=f'{type(exc).__name__}: {exc}',
        )
        raise

    raw.record_response(
        database,
        run_id,
        endpoint=endpoint,
        request=request_info,
        status_code=response.status_code,
        body=response.content,
    )
    return response


def _active_run() -> tuple[sqlite3.Connection | None, int | None]:
    context = click.get_current_context(silent=True)
    if context is None:
        return None, None
    root = context.find_root()
    if root.obj is None:
        return None, None
    return root.obj.get('database'), root.obj.get('run_id')


def _request_info(
    session: requests.Session,
    method: str,
    url: str,
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    headers = dict(session.headers)
    headers.update(kwargs.get('headers') or {})
    return {
        'method': method.upper(),
        'url': url,
        'params': kwargs.get('params'),
        'headers': _redact_headers(headers),
        'body': _request_body(kwargs),
    }


def _redact_headers(headers: dict[str, Any]) -> dict[str, str]:
    return {
        str(name): REDACTED if str(name).lower() in REDACT_HEADERS else str(value)
        for name, value in headers.items()
    }


def _request_body(kwargs: dict[str, Any]) -> Any:
    if 'json' in kwargs:
        return kwargs['json']
    if 'data' in kwargs:
        return kwargs['data']
    return None
