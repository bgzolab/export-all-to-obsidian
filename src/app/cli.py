"""CLI 入口装配。"""

import click

from app.context import (
    get_command,
    get_database,
    get_index_writer,
    get_output_prefix,
    initialize_context,
    run_action,
)
from app.credential_guard import (
    probe_bangumi_credentials,
    probe_bilibili_credentials,
    probe_cnblog_credentials,
    probe_qireader_credentials,
    probe_twitter_credentials,
    probe_v2ex_credentials,
    probe_weibo_credentials,
    probe_zhihu_credentials,
    run_with_credential_guard,
)
from bangumi.exporter import export as export_bangumi
from bangumi.exporter import sync_all_collections
from bilibili.exporter import export as export_bilibili
from cnblog.exporter import export as export_cnblog
from db.import_markdown import import_markdown
from github.exporter import export as export_github
from qireader.exporter import export as export_qireader
from twitter.exporter import TWITTER_MAX_PAGES
from twitter.exporter import export as export_twitter
from v2ex.exporter import export as export_v2ex
from weibo.exporter import export as export_weibo
from zhihu.exporter import export as export_zhihu


@click.group()
@click.option(
    '--index-file',
    type=click.Path(path_type=str),
    help='索引输出文件路径；未指定时直接打印到控制台',
)
@click.option(
    '--prefix',
    default='~',
    show_default=True,
    help='所有导出文件的统一名前缀；必须放在子命令前',
)
@click.option(
    '--cookies-file',
    type=click.Path(path_type=str),
    default=None,
    help='cookies.txt 文件路径；未指定时读取环境变量 COOKIES',
)
@click.option(
    '--db',
    'db_path',
    type=click.Path(path_type=str),
    default=None,
    help='SQLite 数据库路径；默认 ~/.eto/eto.db',
)
@click.pass_context
def eto(
    ctx: click.Context,
    index_file: str | None,
    prefix: str,
    cookies_file: str | None,
    db_path: str | None,
) -> None:
    """导出命令组。"""
    initialize_context(ctx, index_file, prefix, cookies_file, db_path)


@eto.command()
@click.option('--output', '-o', required=True, help='输出目录')
def cnblog(output: str) -> None:
    """导出博客园收藏。"""
    run_with_credential_guard(
        'cnblog',
        probe_cnblog_credentials,
        lambda: run_action(
            'cnblog',
            'bookmarks',
            None,
            lambda: export_cnblog(output, get_index_writer()),
        ),
    )


@eto.command()
@click.option('--template', '-t', required=True, type=str, help='模板文件')
@click.option('--subject_type', '-s', required=True, type=int, help='主题类型')
@click.option('--output', '-o', required=True, help='输出目录')
@click.option('--collection_type', '-c', required=False, type=int, help='收藏类型')
@click.option('--force', required=False, is_flag=True, help='是否强制覆盖')
def bangumi(
    subject_type: int,
    collection_type: int | None,
    output: str,
    template: str,
    force: bool,
) -> None:
    """导出 Bangumi 收藏。"""

    def export_action() -> None:
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

    run_with_credential_guard(
        'bangumi',
        probe_bangumi_credentials,
        lambda: run_action(
            'bangumi',
            'collections',
            f'{subject_type}:{collection_type or "all"}',
            export_action,
        ),
    )


@eto.command()
@click.option('--tag', '-t', required=True, type=str, help='收藏夹ID')
@click.option('--output', '-o', required=True, help='输出目录')
def qireader(tag: str, output: str) -> None:
    """导出稍后读列表。"""
    run_with_credential_guard(
        'qireader',
        lambda: probe_qireader_credentials(tag),
        lambda: run_action(
            'qireader',
            'readlater',
            tag,
            lambda: export_qireader(tag, output, get_index_writer()),
        ),
    )


@eto.command()
@click.option('--output', '-o', required=True, help='输出目录')
def v2ex(output: str) -> None:
    """导出 V2EX 收藏主题。"""
    run_with_credential_guard(
        'v2ex',
        probe_v2ex_credentials,
        lambda: run_action(
            'v2ex',
            'favorites',
            None,
            lambda: export_v2ex(output, get_index_writer()),
        ),
    )


@eto.command()
@click.option('--output', '-o', required=True, help='输出目录')
@click.option('--force', required=False, is_flag=True, help='是否强制覆盖')
@click.option(
    '--max-pages',
    required=False,
    type=click.IntRange(min=1),
    default=None,
    help=f'Twitter 点赞最大分页数（默认 {TWITTER_MAX_PAGES}，即约 '
    f'{TWITTER_MAX_PAGES * 20} 条）',
)
def twitter(output: str, force: bool, max_pages: int | None) -> None:
    """导出 Twitter 点赞。"""
    run_with_credential_guard(
        'twitter',
        probe_twitter_credentials,
        lambda: run_action(
            'twitter',
            'likes',
            None,
            lambda: export_twitter(output, get_index_writer(), force, max_pages),
        ),
    )


@eto.command()
@click.option('--collection', '-c', required=True, help='收藏夹')
@click.option('--output', '-o', required=True, help='输出目录')
def zhihu(collection: str, output: str) -> None:
    """导出知乎收藏夹。"""
    run_with_credential_guard(
        'zhihu',
        lambda: probe_zhihu_credentials(collection),
        lambda: run_action(
            'zhihu',
            'collection',
            collection,
            lambda: export_zhihu(collection, output, get_index_writer()),
        ),
    )


@eto.command()
@click.option('--uid', '-u', required=True, help='用户ID')
@click.option('--output', '-o', required=True, help='输出目录')
@click.option('--force', required=False, is_flag=True, help='是否强制覆盖')
def weibo(uid: int, output: str, force: bool) -> None:
    """导出微博点赞。"""
    run_with_credential_guard(
        'weibo',
        lambda: probe_weibo_credentials(uid),
        lambda: run_action(
            'weibo',
            'likes',
            str(uid),
            lambda: export_weibo(uid, output, get_index_writer(), force),
        ),
    )


@eto.command()
@click.option('--fid', '-f', required=True, help='收藏夹ID')
@click.option('--output', '-o', required=True, help='输出目录')
@click.option('--force', required=False, is_flag=True, help='是否强制覆盖')
def bilibili(fid: int, output: str, force: bool) -> None:
    """导出 Bilibili 收藏夹。"""
    run_with_credential_guard(
        'bilibili',
        lambda: probe_bilibili_credentials(fid),
        lambda: run_action(
            'bilibili',
            'favlist',
            str(fid),
            lambda: export_bilibili(fid, output, get_index_writer(), force),
        ),
    )


@eto.command()
@click.option('--template', '-t', required=True, type=str, help='模板文件')
@click.option('--output', '-o', required=True, help='输出目录')
@click.option('--force', required=False, is_flag=True, help='是否强制覆盖')
def github(template: str, output: str, force: bool) -> None:
    """导出 GitHub stars。"""
    run_action(
        'github',
        'stars',
        None,
        lambda: export_github(
            output,
            template,
            get_index_writer(),
            force,
            get_output_prefix(),
        ),
    )


@eto.command(name='import-markdown')
@click.argument('path', type=click.Path(path_type=str))
def import_markdown_command(path: str) -> None:
    """把已有 Markdown 文件原样导入数据库。"""
    try:
        stats = import_markdown(
            get_database(),
            path,
            command=get_command(),
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        f'导入完成: {stats["imported"]} 个，'
        f'跳过 {stats["skipped"]} 个，失败 {stats["failed"]} 个'
    )
