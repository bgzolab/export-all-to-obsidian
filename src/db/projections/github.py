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
    SkipResponse,
    apply_handler,
    iter_body_responses,
    iter_json_responses,
    json_dumps,
    request_payload,
    reset_tables,
    skip_handler_response,
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
        try:
            result.rows += apply_handler(
                README_ENDPOINT,
                response,
                _update_readme,
                connection,
                body,
                response,
                now,
                result,
            )
        except SkipResponse as exc:
            skip_handler_response(result, README_ENDPOINT, response, str(exc))

    return result


def _upsert_stars(
    connection: sqlite3.Connection,
    payload: Any,
    response_id: int,
    now: str,
) -> int:
    if payload is None:
        return 0
    if not isinstance(payload, list):
        raise TypeError('invalid stars payload')
    rows = 0
    for item in payload:
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


def known_repo_ids(
    connection: sqlite3.Connection,
    repo_ids: list[int],
) -> set[int]:
    """Return the subset of repo ids already present in the projection."""
    if not repo_ids:
        return set()
    placeholders = ','.join('?' for _ in repo_ids)
    rows = connection.execute(
        f'SELECT repo_id FROM github_star WHERE repo_id IN ({placeholders})',
        repo_ids,
    )
    return {row['repo_id'] for row in rows}


def readme_exists(connection: sqlite3.Connection, repo_id: int) -> bool:
    """Return whether the repository README is already projected."""
    return (
        connection.execute(
            'SELECT 1 FROM github_star '
            'WHERE repo_id = ? AND readme_response_id IS NOT NULL',
            (repo_id,),
        ).fetchone()
        is not None
    )


def _update_readme(
    connection: sqlite3.Connection,
    body: bytes,
    response: dict[str, Any],
    now: str,
    result: RebuildResult,
) -> int:
    url = request_payload(response).get('url') or ''
    match = _README_URL_RE.search(url)
    if match is None:
        raise SkipResponse('cannot determine repository from request URL')
    full_name = f'{match.group(1)}/{match.group(2)}'
    status_code = response.get('status_code')
    if status_code == 404:
        readme = ''
    elif status_code == 200:
        readme = _decode_readme(body)
    else:
        raise SkipResponse(f'unexpected HTTP {status_code}')
    matches = connection.execute(
        'SELECT repo_id FROM github_star WHERE full_name = ?',
        (full_name,),
    ).fetchall()
    if len(matches) != 1:
        result.aux_missed += 1
        print(
            '辅助数据未命中或存在歧义: '
            f'github_star full_name={full_name} matches={len(matches)}',
        )
        return 0
    return update_aux(
        connection,
        'github_star',
        {'repo_id': matches[0]['repo_id']},
        {'readme': readme},
        'readme_response_id',
        response['id'],
        now,
    )


def _decode_readme(body: bytes) -> str:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        text = body.decode('utf-8', errors='replace')
        if text.lstrip().lower().startswith(('<!doctype html', '<html')):
            raise SkipResponse('readme payload is HTML')
        return text
    if not isinstance(payload, dict):
        raise SkipResponse('readme payload is not a JSON object')
    content = payload.get('content')
    if not isinstance(content, str):
        raise SkipResponse('readme JSON missing content')
    try:
        decoded = base64.b64decode(content.replace('\n', ''))
    except ValueError as exc:
        raise SkipResponse(f'readme base64 decode failed: {exc}') from exc
    return decoded.decode('utf-8', errors='ignore')
