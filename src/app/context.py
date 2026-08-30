"""click 运行时上下文。"""

import os

import click

from export_runtime.index_writer import IndexWriter


def initialize_context(
    ctx: click.Context,
    index_file: str | None,
    output_prefix: str,
    cookies_file: str | None = None,
) -> None:
    """初始化根上下文。"""
    if index_file and os.path.isdir(index_file):
        # 与 --cookies-file 指向目录的约定一致：坏路径统一 exit 1（ClickException），
        # 而非 click 参数校验的 exit 2（dir_okay=False 已移除）
        raise click.ClickException(f"Index file is a directory: {index_file}")
    ctx.ensure_object(dict)
    ctx.obj["index_writer"] = IndexWriter(file_path=index_file)
    ctx.obj["output_prefix"] = output_prefix
    ctx.obj["cookies_file"] = cookies_file


def get_index_writer() -> IndexWriter:
    """从 click 上下文中获取全局索引输出器。"""
    context = click.get_current_context()
    writer = context.find_root().obj.get("index_writer")
    if writer is None:
        raise click.ClickException("索引输出器未初始化")
    return writer


def get_output_prefix(default: str = "~") -> str:
    """从 click 根上下文中获取统一输出前缀。"""
    context = click.get_current_context(silent=True)
    if context is None:
        return default

    root_context = context.find_root()
    if root_context.obj is None:
        return default

    output_prefix = root_context.obj.get("output_prefix")
    if output_prefix is None:
        return default
    return output_prefix