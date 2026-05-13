"""click 运行时上下文。"""

import click

from export_runtime.index_writer import IndexWriter


def initialize_context(ctx: click.Context, index_file: str | None) -> None:
    """初始化根上下文。"""
    ctx.ensure_object(dict)
    ctx.obj["index_writer"] = IndexWriter(file_path=index_file)


def get_index_writer() -> IndexWriter:
    """从 click 上下文中获取全局索引输出器。"""
    context = click.get_current_context()
    writer = context.find_root().obj.get("index_writer")
    if writer is None:
        raise click.ClickException("索引输出器未初始化")
    return writer