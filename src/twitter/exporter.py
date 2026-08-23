#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Twitter 点赞导出流程。

@Author : bGZo
@Date : 2026-08-19
@Links : https://github.com/bGZo
"""
from datetime import datetime

from export_runtime.exporter_support import add_index_entry
from export_runtime.exporter_support import build_link_target
from export_runtime.exporter_support import stop_if_output_exists
from export_runtime.exporter_support import write_markdown_output
from export_runtime.index_writer import IndexWriter
from utils.file_utils import get_clean_filename
from utils.template import WebPage
from twitter.cilent import TwitterClient
from twitter.like import get_twitter_like_list

TWITTER_CREATED_AT_FORMAT = "%a %b %d %H:%M:%S %z %Y"


def _parse_created_at(value: str) -> str:
    """解析 Twitter 时间字符串为 ISO 时间。"""
    if not value:
        return ""
    try:
        dt_obj = datetime.strptime(value, TWITTER_CREATED_AT_FORMAT)
        return dt_obj.strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return value


def export(output_dir: str, index_writer: IndexWriter, force: bool = False) -> None:
    """导出当前用户点赞 Tweet。"""
    try:
        client = TwitterClient()
    except ValueError as exc:
        print(exc)
        return
    cursor: str | None = None

    while True:
        page = get_twitter_like_list(client, cursor=cursor)
        if page is None:
            print("获取 Twitter 点赞列表失败，请检查接口")
            break

        if len(page.tweets) == 0:
            break

        for tweet in page.tweets:
            try:
                filename = f"{tweet.author.screen_name}-{tweet.id_str}"

                if stop_if_output_exists(
                    output_dir,
                    filename,
                    index_writer=index_writer,
                    section_name="twitter",
                    force=force,
                ):
                    return

                author_name = tweet.author.name or tweet.author.screen_name
                context_digest = get_clean_filename(tweet.full_text[:10])
                title = f"{author_name}:{context_digest}"

                created = _parse_created_at(tweet.created_at)
                webpage = WebPage(
                    comments=True,
                    draft=True,
                    title=title,
                    source=tweet.url,
                    created=created,
                    modified=created,
                    type="archive-web",
                )
                write_markdown_output(
                    output_dir,
                    filename,
                    webpage.__dict__,
                    tweet.full_text,
                )

                print(f"Done: {title}")
                add_index_entry(
                    index_writer,
                    link_target=build_link_target(filename),
                    title=title,
                )

            except Exception as error:
                print(f"处理报文发生错误: {error}，跳过处理")

        if page.cursor_bottom is None:
            break
        cursor = page.cursor_bottom.value

    index_writer.flush("twitter")
