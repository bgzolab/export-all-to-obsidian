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
) -> None:
    """初始化根上下文。"""
    if index_file and os.path.isdir(index_file):
        # 与 --cookies-file 指向目录的约定一致：坏路径统一 exit 1（ClickException），
        # 而非 click 参数校验的 exit 2（dir_okay=False 已移除）
        raise click.ClickException(f'Index file is a directory: {index_file}')
    ctx.ensure_object(dict)
    ctx.obj['index_writer'] = IndexWriter(file_path=index_file)
    ctx.obj['output_prefix'] = output_prefix
    ctx.obj['cookies_file'] = cookies_file
    ctx.obj['command'] = shlex.join(sys.argv)
    ctx.obj['run_partial'] = False
    ctx.obj['database'] = _open_database(db_path)


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
        raw.finish_run(database, run_id, 'failed', f'{type(exc).__name__}: {exc}')
        raise
    else:
        status = 'partial' if root.obj.get('run_partial') else 'success'
        raw.finish_run(database, run_id, status)
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
    with sync_run(platform, operation, scope):
        action()
