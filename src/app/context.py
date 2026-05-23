"""click 运行时上下文。"""

import click

from export_runtime.index_writer import IndexWriter


def initialize_context(
    ctx: click.Context,
    index_file: str | None,
    output_prefix: str,
) -> None:
    """初始化根上下文。"""
    ctx.ensure_object(dict)
    ctx.obj["index_writer"] = IndexWriter(file_path=index_file)
    ctx.obj["output_prefix"] = output_prefix


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