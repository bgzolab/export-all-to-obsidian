"""HTTP requests with optional raw-response recording."""

from __future__ import annotations

import sqlite3
from contextlib import suppress
from typing import Any

import click
import requests

from db import raw

REDACTED = '[REDACTED]'
REDACT_HEADERS = {
    'authorization',
    'cookie',
    'proxy-authorization',
    'x-api-key',
    'x-auth-token',
    'x-csrf-token',
}
REDACT_KEYWORDS = ('auth', 'token', 'csrf', 'session', 'cookie', 'key')


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
        return _send(session, method, url, kwargs)

    try:
        response = _send(session, method, url, kwargs)
    except Exception as exc:
        try:
            raw.record_error(
                database,
                run_id,
                endpoint=endpoint,
                request=request_info,
                error=f'{type(exc).__name__}: {exc}',
            )
        except Exception as record_exc:
            _warn_record_failure(record_exc)
        raise

    try:
        raw.record_response(
            database,
            run_id,
            endpoint=endpoint,
            request=request_info,
            status_code=response.status_code,
            body=response.content,
        )
    except Exception as record_exc:
        _warn_record_failure(record_exc)
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
    headers = dict(getattr(session, 'headers', {}) or {})
    headers.update(kwargs.get('headers') or {})
    return {
        'method': method.upper(),
        'url': url,
        'params': kwargs.get('params'),
        'headers': _redact_headers(headers),
        'body': _request_body(kwargs),
    }


def _send(
    session: requests.Session,
    method: str,
    url: str,
    kwargs: dict[str, Any],
) -> requests.Response:
    sender = getattr(session, method.lower(), None)
    if callable(sender):
        return sender(url, **kwargs)
    return session.request(method, url, **kwargs)


def _redact_headers(headers: dict[str, Any]) -> dict[str, str]:
    return {
        str(name): REDACTED if _is_sensitive_header(str(name)) else str(value)
        for name, value in headers.items()
    }


def _is_sensitive_header(name: str) -> bool:
    lower = name.lower()
    return lower in REDACT_HEADERS or any(
        keyword in lower for keyword in REDACT_KEYWORDS
    )


def _request_body(kwargs: dict[str, Any]) -> Any:
    if 'json' in kwargs:
        return kwargs['json']
    if 'data' in kwargs:
        return kwargs['data']
    return None


def _warn_record_failure(exc: Exception) -> None:
    print(f'原始响应记录失败: {type(exc).__name__}: {exc}')
    try:
        from app.context import mark_run_partial
    except Exception as import_exc:
        print(f'标记 sync_run partial 失败: {type(import_exc).__name__}: {import_exc}')
        return
    with suppress(Exception):
        mark_run_partial()
