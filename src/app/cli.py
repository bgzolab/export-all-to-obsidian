"""CLI 入口装配。"""

from typing import Optional

import click

from app.context import get_index_writer, initialize_context
from bangumi.exporter import export as export_bangumi
from bangumi.exporter import sync_all_collections
from bilibili.exporter import export as export_bilibili
from cnblog.exporter import export as export_cnblog
from qireader.exporter import export as export_qireader
from v2ex.exporter import export as export_v2ex
from weibo.exporter import export as export_weibo
from zhihu.exporter import export as export_zhihu


@click.group()
@click.option(
    "--index-file",
    type=click.Path(dir_okay=False, path_type=str),
    help="索引输出文件路径；未指定时直接打印到控制台",
)
@click.pass_context
def eto(ctx: click.Context, index_file: Optional[str]) -> None:
    """导出命令组。"""
    initialize_context(ctx, index_file)


@eto.command()
@click.option("--output", "-o", required=True, help="输出目录")
def cnblog(output: str) -> None:
    """导出博客园收藏。"""
    export_cnblog(output, get_index_writer())


@eto.command()
@click.option("--template", "-t", required=True, type=str, help="模板文件")
@click.option("--subject_type", "-s", required=True, type=int, help="主题类型")
@click.option("--output", "-o", required=True, help="输出目录")
@click.option("--collection_type", "-c", required=False, type=int, help="收藏类型")
@click.option("--force", required=False, is_flag=True, help="是否强制覆盖")
def bangumi(
    subject_type: int,
    collection_type: int | None,
    output: str,
    template: str,
    force: bool,
) -> None:
    """导出 Bangumi 收藏。"""
    index_writer = get_index_writer()
    if collection_type:
        export_bangumi(
            subject_type,
            collection_type,
            output,
            template,
            index_writer,
            force,
        )
    else:
        sync_all_collections(
            subject_type,
            output,
            template,
            index_writer,
            force,
        )


@eto.command()
@click.option("--tag", "-t", required=True, type=str, help="收藏夹ID")
@click.option("--output", "-o", required=True, help="输出目录")
def qireader(tag: str, output: str) -> None:
    """导出稍后读列表。"""
    export_qireader(tag, output, get_index_writer())


@eto.command()
@click.option("--output", "-o", required=True, help="输出目录")
def v2ex(output: str) -> None:
    """导出 V2EX 收藏主题。"""
    export_v2ex(output, get_index_writer())


@eto.command()
@click.option("--collection", "-c", required=True, help="收藏夹")
@click.option("--output", "-o", required=True, help="输出目录")
def zhihu(collection: str, output: str) -> None:
    """导出知乎收藏夹。"""
    export_zhihu(collection, output, get_index_writer())


@eto.command()
@click.option("--uid", "-u", required=True, help="用户ID")
@click.option("--output", "-o", required=True, help="输出目录")
@click.option("--force", required=False, is_flag=True, help="是否强制覆盖")
def weibo(uid: int, output: str, force: bool) -> None:
    """导出微博点赞。"""
    export_weibo(uid, output, get_index_writer(), force)


@eto.command()
@click.option("--fid", "-f", required=True, help="收藏夹ID")
@click.option("--output", "-o", required=True, help="输出目录")
@click.option("--force", required=False, is_flag=True, help="是否强制覆盖")
def bilibili(fid: int, output: str, force: bool) -> None:
    """导出 Bilibili 收藏夹。"""
    export_bilibili(fid, output, get_index_writer(), force)