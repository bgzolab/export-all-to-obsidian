#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Twitter 点赞导出流程。

@Author : bGZo
@Date : 2026-08-19
@Links : https://github.com/bGZo
"""
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import re

from export_runtime.exporter_support import add_index_entry
from export_runtime.exporter_support import build_link_target
from export_runtime.exporter_support import stop_if_output_exists
from export_runtime.exporter_support import write_markdown_output
from export_runtime.index_writer import IndexWriter
from utils.file_utils import get_clean_filename
from utils.template import WebPage
from twitter.client import TwitterClient
from twitter.like import get_twitter_like_list

TWITTER_MAX_PAGES = 50

_EN_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _parse_created_at(value: str) -> str:
    """解析 Twitter 时间字符串为 ISO 时间，不依赖运行环境 locale。"""
    if not value:
        return ""
    # 形如 "Thu Aug 15 12:00:00 +0000 2024"
    match = re.fullmatch(
        r"\w+ (\w+) (\d{1,2}) (\d{1,2}):(\d{2}):(\d{2}) ([+-]\d{4}) (\d{4})",
        value,
    )
    if not match:
        return value
    month_name, day, hour, minute, second, tz, year = match.groups()
    month = _EN_MONTHS.get(month_name)
    if month is None:
        return value
    try:
        tz_seconds = int(tz[1:3]) * 3600 + int(tz[3:]) * 60
        tz_sign = 1 if tz[0] == "+" else -1
        dt_obj = datetime(
            int(year),
            month,
            int(day),
            int(hour),
            int(minute),
            int(second),
            tzinfo=timezone(timedelta(seconds=tz_sign * tz_seconds)),
        )
    except ValueError:
        return value
    return dt_obj.strftime("%Y-%m-%dT%H:%M:%S")


def export(output_dir: str, index_writer: IndexWriter, force: bool = False) -> None:
    """导出当前用户点赞 Tweet。"""
    try:
        client = TwitterClient()
    except ValueError as exc:
        print(exc)
        index_writer.flush("twitter")
        return
    cursor: str | None = None
    seen_cursors: set[str] = set()

    while True:
        if len(seen_cursors) >= TWITTER_MAX_PAGES:
            print(f"Twitter 点赞分页已达上限 {TWITTER_MAX_PAGES}，停止导出")
            break
        try:
            page = get_twitter_like_list(client, cursor=cursor)
        except Exception as error:
            print(f"获取 Twitter 点赞列表异常: {error}")
            break
        if page is None:
            print("获取 Twitter 点赞列表失败，请检查接口")
            break

        if len(page.tweets) == 0:
            break

        for tweet in page.tweets:
            try:
                author_key = tweet.author.screen_name or tweet.author.id or "i"
                filename = f"{author_key}-{tweet.id_str}"

                if stop_if_output_exists(
                    output_dir,
                    filename,
                    index_writer=index_writer,
                    section_name="twitter",
                    force=force,
                ):
                    index_writer.flush("twitter")
                    return

                author_name = tweet.author.name or tweet.author.screen_name or tweet.author.id or "i"
                context_digest = get_clean_filename(tweet.full_text[:10]) or tweet.id_str
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

        if page.cursor_bottom is None or not page.cursor_bottom.value:
            break
        next_cursor = page.cursor_bottom.value
        # 游标未推进时视为接口异常或已到末尾，避免 --force 下死循环
        if next_cursor in seen_cursors:
            print("Twitter 点赞游标未推进，停止导出")
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    index_writer.flush("twitter")
