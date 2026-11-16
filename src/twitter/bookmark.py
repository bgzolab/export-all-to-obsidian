"""
Twitter Bookmarks API fetch helpers.

@Author : bGZo
@Date : 2026-11-16
@Links : https://github.com/bGZo
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from db import raw
from export_runtime import http
from twitter.api_endpoints import (
    TWITTER_BOOKMARKS_FIELD_TOGGLES,
    TWITTER_BOOKMARKS_PAGE_SIZE,
    TWITTER_BOOKMARKS_PATH,
    TWITTER_LIKES_FEATURES,
)
from twitter.client import TwitterClient
from twitter.entity import BookmarksPage

ENDPOINT = 'twitter.bookmarks.page'


def build_bookmarks_params(
    count: int,
    cursor: str | None = None,
) -> dict[str, str]:
    """Build Bookmarks GraphQL query parameters.

    Bookmarks does not need ``userId`` but does need ``withV2Timeline``.
    Features reuse the Likes timeline set; field toggles are bookmark-specific.
    """
    variables = {
        'count': count,
        'includePromotedContent': False,
        'withClientEventToken': False,
        'withBirdwatchNotes': False,
        'withVoice': True,
        'withV2Timeline': True,
    }
    if cursor:
        variables['cursor'] = cursor
    return {
        'features': json.dumps(TWITTER_LIKES_FEATURES),
        'fieldToggles': json.dumps(TWITTER_BOOKMARKS_FIELD_TOGGLES),
        'variables': json.dumps(variables),
    }


@dataclass
class BookmarksFetch:
    """Result of one Bookmarks page request.

    ``page`` is set only for a 200 response with parsable data. Other failures
    are described by ``status_code`` and ``error`` so the caller can decide
    whether to keep or retry the checkpoint.
    """

    page: BookmarksPage | None
    status_code: int | None
    rate_limit_remaining: int | None = None
    rate_limit_reset: int | None = None
    error: str | None = None


def get_twitter_bookmark_list(
    client: TwitterClient,
    count: int = TWITTER_BOOKMARKS_PAGE_SIZE,
    cursor: str | None = None,
) -> BookmarksFetch:
    """Fetch one bookmark page and record the exchange in the raw layer.

    Non-200, non-JSON, non-object, or missing-data responses return a
    ``BookmarksFetch`` with an error instead of raising. The exporter needs the
    status code and rate-limit headers to choose between partial, stop, and
    maintenance hints.
    """
    response = http.get(
        client.session,
        TWITTER_BOOKMARKS_PATH,
        endpoint=ENDPOINT,
        params=build_bookmarks_params(count, cursor),
        timeout=30,
    )
    remaining = _rate_limit_header(response, 'x-rate-limit-remaining')
    reset = _rate_limit_header(response, 'x-rate-limit-reset')

    if response.status_code != 200:
        return BookmarksFetch(
            page=None,
            status_code=response.status_code,
            rate_limit_remaining=remaining,
            rate_limit_reset=reset,
            error=f'HTTP {response.status_code}',
        )

    try:
        payload = response.json()
    except (ValueError, TypeError) as exc:
        return BookmarksFetch(
            page=None,
            status_code=200,
            rate_limit_remaining=remaining,
            rate_limit_reset=reset,
            error=f'响应解析失败: {exc}',
        )
    if not isinstance(payload, dict):
        return BookmarksFetch(
            page=None,
            status_code=200,
            rate_limit_remaining=remaining,
            rate_limit_reset=reset,
            error='响应解析失败: 非 JSON 对象',
        )
    if 'data' not in payload:
        return BookmarksFetch(
            page=None,
            status_code=200,
            rate_limit_remaining=remaining,
            rate_limit_reset=reset,
            error='响应缺少 data',
        )
    data = payload.get('data')
    if not isinstance(data, dict):
        return BookmarksFetch(
            page=None,
            status_code=200,
            rate_limit_remaining=remaining,
            rate_limit_reset=reset,
            error='响应 data 不是 JSON 对象',
        )
    return BookmarksFetch(
        page=BookmarksPage.from_dict(data),
        status_code=200,
        rate_limit_remaining=remaining,
        rate_limit_reset=reset,
    )


def query_id_maintenance_hint(status_code: int) -> str:
    """Return the manual queryId maintenance hint shared by fetch and probes."""
    return (
        f'HTTP {status_code}；X 的 GraphQL queryId 可能已轮换。请从 '
        'x.com/i/bookmarks 的网络请求中获取新的 Bookmarks queryId，并更新 '
        'src/twitter/api_endpoints.py 的 TWITTER_BOOKMARKS_PATH'
    )


@dataclass(frozen=True)
class BookmarkCheckpoint:
    """Resume position derived from the latest full bookmark response.

    ``in_progress`` means the previous full run did not reach the end, so the
    next ``--full`` run should start from ``cursor`` (or retry the same page
    when the failed request had no recorded cursor).
    """

    cursor: str | None
    in_progress: bool


def latest_bookmark_checkpoint(
    connection: sqlite3.Connection,
) -> BookmarkCheckpoint:
    """Derive the full-run resume cursor from the raw response layer.

    Only ``scope='full'`` responses are considered: incremental runs always
    start at the top and would otherwise overwrite the resume position.
    Failed or unparsable requests resume at their own request cursor; a 200
    response without a bottom cursor means the previous full run reached the
    end.
    """
    response = raw.latest_response(connection, ENDPOINT, scope='full')
    if response is None:
        return BookmarkCheckpoint(cursor=None, in_progress=False)

    request_cursor = _request_cursor(response)
    if (
        response.get('error')
        or response.get('status_code') != 200
        or response.get('body') is None
    ):
        return BookmarkCheckpoint(cursor=request_cursor, in_progress=True)

    try:
        payload = json.loads(response['body'])
    except (TypeError, ValueError):
        return BookmarkCheckpoint(cursor=request_cursor, in_progress=True)
    if not isinstance(payload, dict):
        return BookmarkCheckpoint(cursor=request_cursor, in_progress=True)
    data = payload.get('data')
    if not isinstance(data, dict):
        return BookmarkCheckpoint(cursor=request_cursor, in_progress=True)

    try:
        page = BookmarksPage.from_dict(data)
    except (AttributeError, TypeError):
        # A structurally unexpected 200 body should retry the same page rather
        # than silently restarting the full run from the top.
        return BookmarkCheckpoint(cursor=request_cursor, in_progress=True)

    next_cursor = page.cursor_bottom.value if page.cursor_bottom is not None else ''
    if not next_cursor:
        return BookmarkCheckpoint(cursor=None, in_progress=False)
    if not page.tweets and next_cursor == request_cursor:
        # Some timelines end with an empty cursor-only page that repeats the
        # request cursor. Persisting it would trap every future --full run.
        return BookmarkCheckpoint(cursor=None, in_progress=False)
    return BookmarkCheckpoint(cursor=next_cursor, in_progress=True)


def _request_cursor(response: dict[str, Any]) -> str | None:
    """Extract ``request.params.variables.cursor`` from a recorded response."""
    request = response.get('request')
    if isinstance(request, str):
        try:
            request = json.loads(request)
        except (TypeError, ValueError):
            return None
    if not isinstance(request, dict):
        return None
    params = request.get('params')
    if not isinstance(params, dict):
        return None
    variables = params.get('variables')
    if isinstance(variables, str):
        try:
            variables = json.loads(variables)
        except (TypeError, ValueError):
            return None
    if not isinstance(variables, dict):
        return None
    cursor = variables.get('cursor')
    return cursor if isinstance(cursor, str) and cursor else None


def _rate_limit_header(response: Any, name: str) -> int | None:
    """Read an integer rate-limit header without trusting response shape."""
    headers = getattr(response, 'headers', None) or {}
    try:
        value = headers.get(name)
    except AttributeError:
        return None
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
