"""click 运行时上下文。"""

import os
import shlex
import sqlite3
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import click

import db
from db import raw
from export_runtime.index_writer import IndexWriter


def initialize_context(
    ctx: click.Context,
    index_file: str | None,
    output_prefix: str,
    cookies_file: str | None = None,
    db_path: str | None = None,
    db_only: bool = False,
) -> None:
    """初始化根上下文。"""
    if db_only and index_file:
        raise click.UsageError('--index-file cannot be used with --db-only')
    if index_file and os.path.isdir(index_file):
        # 与 --cookies-file 指向目录的约定一致：坏路径统一 exit 1（ClickException），
        # 而非 click 参数校验的 exit 2（dir_okay=False 已移除）
        raise click.ClickException(f'Index file is a directory: {index_file}')
    ctx.ensure_object(dict)
    ctx.obj['index_writer'] = IndexWriter(
        file_path=index_file,
        enabled=not db_only,
    )
    ctx.obj['output_prefix'] = output_prefix
    ctx.obj['cookies_file'] = cookies_file
    ctx.obj['command'] = shlex.join(sys.argv)
    ctx.obj['run_partial'] = False
    ctx.obj['db_only'] = db_only
    database = _open_database(db_path)
    ctx.obj['database'] = database
    ctx.call_on_close(database.close)


def _open_database(db_path: str | None) -> sqlite3.Connection:
    if db_path and os.path.isdir(db_path):
        raise click.ClickException(f'Database path is a directory: {db_path}')
    try:
        return db.connect(db_path)
    except (OSError, sqlite3.Error) as exc:
        raise click.ClickException(f'Failed to open database: {exc}') from exc


def get_index_writer() -> IndexWriter:
    """从 click 上下文中获取全局索引输出器。"""
    context = click.get_current_context()
    writer = context.find_root().obj.get('index_writer')
    if writer is None:
        raise click.ClickException('索引输出器未初始化')
    return writer


def get_output_prefix(default: str = '~') -> str:
    """从 click 根上下文中获取统一输出前缀。"""
    context = click.get_current_context(silent=True)
    if context is None:
        return default

    root_context = context.find_root()
    if root_context.obj is None:
        return default

    output_prefix = root_context.obj.get('output_prefix')
    if output_prefix is None:
        return default
    return output_prefix


def get_database() -> sqlite3.Connection:
    """Return the raw database connection from the root context."""
    context = click.get_current_context()
    database = context.find_root().obj.get('database')
    if database is None:
        raise click.ClickException('数据库未初始化')
    return database


def get_run_id() -> int | None:
    """Return the active sync run id, if any."""
    context = click.get_current_context(silent=True)
    if context is None:
        return None
    return context.find_root().obj.get('run_id')


def is_db_only() -> bool:
    """Return whether the current command only writes to the database."""
    context = click.get_current_context(silent=True)
    if context is None:
        return False
    root = context.find_root()
    return bool(root.obj and root.obj.get('db_only'))


def get_command() -> str | None:
    """Return the command that started this process."""
    context = click.get_current_context(silent=True)
    if context is None:
        return None
    return context.find_root().obj.get('command')


@contextmanager
def sync_run(
    platform: str,
    operation: str,
    scope: str | None = None,
) -> Iterator[int]:
    """Create a sync_run around one export action."""
    database = get_database()
    root = click.get_current_context().find_root()
    root.obj['run_partial'] = False
    run_id = raw.start_run(
        database,
        platform=platform,
        operation=operation,
        scope=scope,
        command=root.obj.get('command'),
    )
    root.obj['run_id'] = run_id
    try:
        yield run_id
    except BaseException as exc:
        try:
            raw.finish_run(database, run_id, 'failed', f'{type(exc).__name__}: {exc}')
        except Exception as finish_exc:
            print(f'结束 sync_run 失败: {type(finish_exc).__name__}: {finish_exc}')
        raise
    else:
        status = 'partial' if root.obj.get('run_partial') else 'success'
        try:
            raw.finish_run(database, run_id, status)
        except Exception as finish_exc:
            print(
                f'结束 sync_run 失败: {type(finish_exc).__name__}: '
                f'{finish_exc} (run_id={run_id})'
            )
    finally:
        root.obj['run_id'] = None
        root.obj['run_partial'] = False


def mark_run_partial() -> None:
    """Mark the active sync run as partial, if any."""
    context = click.get_current_context(silent=True)
    if context is None:
        return
    root = context.find_root()
    if root.obj is not None:
        root.obj['run_partial'] = True


def run_action(
    platform: str,
    operation: str,
    scope: str | None,
    action: Callable[[], None],
) -> None:
    """Run an export action inside a sync_run."""
    projection_error: Exception | None = None
    with sync_run(platform, operation, scope):
        action()
        if is_db_only():
            try:
                _rebuild_projection(platform)
            except Exception as exc:
                mark_run_partial()
                projection_error = exc
    if projection_error is not None:
        raise click.ClickException(
            f'投影失败: {projection_error}；请按 docs/usages/db.md 定位/处置坏响应',
        )


def _rebuild_projection(platform: str) -> None:
    from db.projections import SUPPORTED_PLATFORMS, rebuild_platform

    if platform not in SUPPORTED_PLATFORMS:
        print(f'projection not implemented: {platform}')
        return
    result = rebuild_platform(get_database(), platform)
    click.echo(f'投影完成: {result.summary()}')
