"""
Twitter 点赞导出流程。

@Author : bGZo
@Date : 2026-08-19
@Links : https://github.com/bGZo
"""

import re
from datetime import datetime, timedelta, timezone

from app.context import get_database, is_db_only, mark_run_partial
from db.projections import twitter as twitter_projection
from export_runtime.exporter_support import (
    add_index_entry,
    build_link_target,
    stop_if_output_exists,
    stop_if_page_known,
    write_markdown_output,
)
from export_runtime.index_writer import IndexWriter
from twitter.bookmark import (
    BookmarksFetch,
    get_twitter_bookmark_list,
    latest_bookmark_checkpoint,
    query_id_maintenance_hint,
)
from twitter.client import TwitterClient
from twitter.like import get_twitter_like_list
from utils.file_utils import get_clean_filename
from utils.template import WebPage

TWITTER_MAX_PAGES = 50

_EN_MONTHS = {
    'Jan': 1,
    'Feb': 2,
    'Mar': 3,
    'Apr': 4,
    'May': 5,
    'Jun': 6,
    'Jul': 7,
    'Aug': 8,
    'Sep': 9,
    'Oct': 10,
    'Nov': 11,
    'Dec': 12,
}


def _parse_created_at(value: str) -> str:
    """解析 Twitter 时间字符串为 ISO 时间，不依赖运行环境 locale。"""
    if not value:
        return ''
    # 形如 "Thu Aug 15 12:00:00 +0000 2024"
    match = re.fullmatch(
        r'\w+ (\w+) (\d{1,2}) (\d{1,2}):(\d{2}):(\d{2}) ([+-]\d{4}) (\d{4})',
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
        tz_sign = 1 if tz[0] == '+' else -1
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
    return dt_obj.strftime('%Y-%m-%dT%H:%M:%S%z')


def export(
    output_dir: str,
    index_writer: IndexWriter,
    force: bool = False,
    max_pages: int | None = None,
) -> None:
    """导出当前用户点赞 Tweet。"""
    # None 或非法值回退到默认上限，避免误传 0/负数导致静默无输出
    max_pages = max_pages if max_pages and max_pages > 0 else TWITTER_MAX_PAGES
    try:
        client = TwitterClient()
    except ValueError as exc:
        mark_run_partial()
        print(exc)
        index_writer.flush('twitter')
        return
    cursor: str | None = None
    seen_cursors: set[str] = set()

    while True:
        if len(seen_cursors) >= max_pages:
            mark_run_partial()
            print(f'Twitter 点赞分页已达上限 {max_pages}，停止导出')
            break
        try:
            page = get_twitter_like_list(client, cursor=cursor)
        except Exception as error:
            mark_run_partial()
            print(f'获取 Twitter 点赞列表异常: {error}')
            break
        if page is None:
            mark_run_partial()
            print('获取 Twitter 点赞列表失败，请检查接口')
            break

        if len(page.tweets) == 0:
            break

        for tweet in page.tweets:
            try:
                author_key = tweet.author.screen_name or tweet.author.id or 'i'
                filename = f'{author_key}-{tweet.id_str}'

                if stop_if_output_exists(
                    output_dir,
                    filename,
                    index_writer=index_writer,
                    section_name='twitter',
                    force=force,
                ):
                    return

                author_name = (
                    tweet.author.name
                    or tweet.author.screen_name
                    or tweet.author.id
                    or 'i'
                )
                context_digest = (
                    get_clean_filename(tweet.full_text[:10]) or tweet.id_str
                )
                title = f'{author_name}:{context_digest}'

                created = _parse_created_at(tweet.created_at)
                webpage = WebPage(
                    comments=True,
                    draft=True,
                    title=title,
                    source=tweet.url,
                    created=created,
                    modified=created,
                    type='archive-web',
                )
                write_markdown_output(
                    output_dir,
                    filename,
                    webpage.__dict__,
                    tweet.full_text,
                )

                print(f'Done: {title}')
                add_index_entry(
                    index_writer,
                    link_target=build_link_target(filename),
                    title=title,
                )

            except Exception as error:
                mark_run_partial()
                print(f'处理报文发生错误: {error}，跳过处理')

        tweet_ids = [tweet.id_str for tweet in page.tweets]
        if is_db_only() and not force and tweet_ids:
            known = twitter_projection.known_tweet_ids(
                get_database(),
                tweet_ids,
            )
            if stop_if_page_known(tweet_ids, known):
                break

        if page.cursor_bottom is None or not page.cursor_bottom.value:
            break
        next_cursor = page.cursor_bottom.value
        # 游标未推进时视为接口异常或已到末尾，避免 --force 下死循环
        if next_cursor in seen_cursors:
            mark_run_partial()
            print('Twitter 点赞游标未推进，停止导出')
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor

    index_writer.flush('twitter')


def ingest_bookmarks(
    full: bool = False,
    force: bool = False,
    max_pages: int | None = None,
) -> None:
    """Fetch X bookmarks into the raw layer for later projection.

    Incremental mode starts at the top and stops once a whole page is already
    in ``twitter_bookmark``. ``--full`` resumes from the last full run's
    checkpoint and never stops on a known page; ``--force`` implies full but
    ignores the checkpoint. Every truncated or failed run is marked partial so
    ``success`` only means the list end was actually observed.
    """
    full = full or force
    max_pages = max_pages if max_pages and max_pages > 0 else TWITTER_MAX_PAGES
    try:
        client = TwitterClient()
    except ValueError as exc:
        mark_run_partial()
        print(exc)
        return

    connection = get_database()
    checkpoint = latest_bookmark_checkpoint(connection)
    cursor: str | None = None
    if full:
        if not force:
            cursor = checkpoint.cursor
        if checkpoint.in_progress:
            if force:
                print('忽略上次书签断点，从顶部重新全量抓取')
            else:
                print('从上次断点继续全量书签抓取')
    elif checkpoint.in_progress:
        print('存在未完成的全量书签抓取，如需继续请加 --full')

    pages = 0
    empty_pages = 0
    seen_cursors: set[str] = set()

    while True:
        if pages >= max_pages:
            mark_run_partial()
            print(f'Twitter 书签分页已达上限 {max_pages}，停止抓取')
            break
        pages += 1
        try:
            fetch = get_twitter_bookmark_list(client, cursor=cursor)
        except Exception as error:
            mark_run_partial()
            print(f'获取 Twitter 书签列表异常: {error}')
            break

        if fetch.error is not None or fetch.page is None:
            mark_run_partial()
            _print_bookmark_fetch_error(fetch, cursor)
            break

        page = fetch.page
        if page.tweets:
            empty_pages = 0
        else:
            empty_pages += 1

        if not full and page.tweets:
            # Deduplicate before comparing: a malformed page can repeat a tweet
            # and must not defeat the whole-page-known pruning signal.
            tweet_ids = {tweet.id_str for tweet in page.tweets}
            known = twitter_projection.known_bookmark_ids(
                connection,
                list(tweet_ids),
            )
            if len(known) == len(tweet_ids):
                mark_run_partial()
                print('Twitter 书签整页已存在，停止增量抓取')
                break

        next_cursor = page.cursor_bottom.value if page.cursor_bottom is not None else ''
        if not next_cursor:
            break
        if next_cursor == cursor or next_cursor in seen_cursors:
            mark_run_partial()
            print('Twitter 书签游标未推进，停止抓取')
            break
        if pages >= max_pages:
            mark_run_partial()
            print(f'Twitter 书签分页已达上限 {max_pages}，停止抓取')
            break
        if fetch.rate_limit_remaining is not None and fetch.rate_limit_remaining <= 0:
            mark_run_partial()
            _print_rate_limit(fetch)
            break
        # A few cursor-bearing empty pages can happen when upstream returns
        # only modules; three in a row is treated as an unproductive loop.
        if empty_pages >= 3:
            mark_run_partial()
            print('Twitter 书签连续 3 页为空，停止抓取')
            break
        seen_cursors.add(next_cursor)
        cursor = next_cursor


def _print_bookmark_fetch_error(
    fetch: BookmarksFetch,
    cursor: str | None,
) -> None:
    """Print an actionable message for a failed bookmark page."""
    status = fetch.status_code
    if status == 429:
        _print_rate_limit(fetch)
        return
    if status == 400 and cursor:
        print('Twitter 书签请求失败: HTTP 400，游标可能失效，请加 --force 从顶部重来')
        return
    if status in {400, 404}:
        print(f'Twitter 书签请求失败: {query_id_maintenance_hint(status)}')
        return
    if status in {401, 403}:
        print(f'Twitter 书签 Cookie 已过期或无效: HTTP {status}')
        return
    print(f'Twitter 书签请求失败: {fetch.error}')


def _print_rate_limit(fetch: BookmarksFetch) -> None:
    """Report the reset timestamp so cron users know when to retry."""
    if fetch.rate_limit_reset is None:
        print('Twitter 书签触发限流，本次抓取停止，稍后重试')
        return
    print(
        f'Twitter 书签触发限流，x-rate-limit-reset={fetch.rate_limit_reset}，'
        '本次抓取停止，稍后重试'
    )
