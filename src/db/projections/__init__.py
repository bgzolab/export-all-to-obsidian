"""Rebuild platform projection tables from the raw response layer."""

from __future__ import annotations

import sqlite3
from types import ModuleType

from db.projections import bangumi
from db.projections._upsert import ProjectionError, RebuildResult

_PLATFORMS: dict[str, ModuleType] = {
    'bangumi': bangumi,
}

SUPPORTED_PLATFORMS = tuple(_PLATFORMS)


def rebuild_platform(
    connection: sqlite3.Connection,
    platform: str,
) -> RebuildResult:
    """Rebuild one platform inside a transaction."""
    module = _PLATFORMS.get(platform)
    if module is None:
        raise ValueError(f'Unsupported platform: {platform}')

    try:
        result = module.rebuild(connection)
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return result


__all__ = [
    'SUPPORTED_PLATFORMS',
    'ProjectionError',
    'RebuildResult',
    'rebuild_platform',
]
