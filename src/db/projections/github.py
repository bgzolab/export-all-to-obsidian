"""GitHub starred repositories and READMEs to projection tables."""

from __future__ import annotations

import base64
import json
import re
import sqlite3
from typing import Any

from db import raw
from db.projections._upsert import (
    RebuildResult,
    apply_handler,
    iter_body_responses,
    iter_json_responses,
    json_dumps,
    request_payload,
    reset_tables,
    update_aux,
    upsert,
)

STARS_ENDPOINT = 'github.stars.list'
README_ENDPOINT = 'github.repo.readme'

DELETE_ORDER = ('github_star',)

_README_URL_RE = re.compile(r'/repos/([^/]+)/([^/]+)/readme')


def rebuild(connection: sqlite3.Connection) -> RebuildResult:
    """Rebuild GitHub stars and their README bodies."""
    now = raw.utc_now()
    reset_tables(connection, DELETE_ORDER)
    result = RebuildResult()

    for response, payload in iter_json_responses(
        connection,
        STARS_ENDPOINT,
        result=result,
    ):
        result.rows += apply_handler(
            STARS_ENDPOINT,
            response,
            _upsert_stars,
            connection,
            payload,
            response['id'],
            now,
        )

    for response, body in iter_body_responses(
        connection,
        README_ENDPOINT,
        result=result,
    ):
        result.rows += apply_handler(
            README_ENDPOINT,
            response,
            _update_readme,
            connection,
            body,
            response,
            now,
        )

    return result


def _upsert_stars(
    connection: sqlite3.Connection,
    payload: Any,
    response_id: int,
    now: str,
) -> int:
    rows = 0
    for item in payload or []:
        repo = item.get('repo') or item
        owner = repo.get('owner') or {}
        license_data = repo.get('license') or {}
        values = {
            'full_name': repo['full_name'],
            'html_url': repo.get('html_url') or '',
            'description': repo.get('description') or '',
            'owner_login': owner.get('login') or '',
            'repo_name': repo.get('name') or '',
            'language': repo.get('language') or '',
            'topics_json': json_dumps(repo.get('topics') or []),
            'stargazers_count': repo.get('stargazers_count') or 0,
            'forks_count': repo.get('forks_count') or 0,
            'open_issues_count': repo.get('open_issues_count') or 0,
            'fork': int(bool(repo.get('fork', False))),
            'archived': int(bool(repo.get('archived', False))),
            'private': int(bool(repo.get('private', False))),
            'homepage': repo.get('homepage') or '',
            'license': license_data.get('spdx_id') or license_data.get('name') or '',
            'created_at': repo.get('created_at'),
            'updated_at': repo.get('updated_at'),
            'pushed_at': repo.get('pushed_at'),
            'starred_at': item.get('starred_at'),
        }
        rows += upsert(
            connection,
            'github_star',
            {'repo_id': repo['id']},
            values,
            response_id,
            now,
        )
    return rows


def _update_readme(
    connection: sqlite3.Connection,
    body: bytes,
    response: dict[str, Any],
    now: str,
) -> int:
    url = request_payload(response).get('url') or ''
    match = _README_URL_RE.search(url)
    if match is None:
        raise ValueError('cannot determine repository from request URL')
    full_name = f'{match.group(1)}/{match.group(2)}'
    status_code = response.get('status_code')
    if status_code == 404:
        readme = ''
    elif status_code == 200:
        readme = _decode_readme(body)
    else:
        return 0
    return update_aux(
        connection,
        'github_star',
        {'full_name': full_name},
        {'readme': readme},
        'readme_response_id',
        response['id'],
        now,
    )


def _decode_readme(body: bytes) -> str:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return body.decode('utf-8', errors='replace')
    if isinstance(payload, dict) and isinstance(payload.get('content'), str):
        content = payload['content'].replace('\n', '')
        return base64.b64decode(content).decode('utf-8', errors='ignore')
    return body.decode('utf-8', errors='replace')
