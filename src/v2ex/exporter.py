"""V2EX 导出流程。"""

from datetime import datetime

from app.context import get_database, is_db_only, mark_run_partial
from db.projections import v2ex as v2ex_projection
from export_runtime.exporter_support import (
    add_index_entry,
    build_link_target,
    stop_if_output_exists,
    write_markdown_output,
)
from export_runtime.index_writer import IndexWriter
from utils.file_utils import get_clean_filename
from utils.template import WebPage
from v2ex.cilent import V2exClient
from v2ex.entity import TopicResult
from v2ex.mytopic import get_fav_list_topic_id_page
from v2ex.replies import V2EX_MAX_REPLIES, fetch_all_replies
from v2ex.tipped import ThanksEntry, get_balance_page
from v2ex.topic import get_v2ex_topic_info

# 连续这么多次主题抓取失败，基本可判定为配额耗尽或上游故障：每次失败已走满
# 客户端重试退避，继续扫描只会对限流端点重复打请求，剩余主题留给下一轮收敛。
V2EX_MAX_CONSECUTIVE_FAILURES = 10


def _warn_reply_gap(topic_id: int, total: int, expected: int) -> None:
    """Report a short reply fetch, usually caused by deleted replies."""
    if total < expected:
        print(
            f'警告: v2ex topic {topic_id} 抓到 {total} 条回复，'
            f'少于 expected={expected}，可能含已删除回复',
        )


def _ensure_topic_data(
    topic_id: int,
    client: V2exClient,
    force: bool,
) -> tuple[TopicResult | None, bool]:
    """Fetch a topic's missing detail/replies.

    Returns ``(topic, failed)``. A ``None`` topic with ``failed=False`` means
    the topic is already projected under ``--db-only`` (after repairing any
    reply gap), so the caller can skip Markdown; ``failed=True`` means the
    fetch itself failed, which the caller may count to abort a doomed batch.
    """
    try:
        if is_db_only() and not force:
            connection = get_database()
            reply_count = v2ex_projection.topic_reply_count(connection, topic_id)
            if reply_count is not None:
                expected = min(reply_count, V2EX_MAX_REPLIES)
                if expected > 0 and not v2ex_projection.replies_complete(
                    connection,
                    topic_id,
                    expected,
                ):
                    _warn_reply_gap(
                        topic_id,
                        fetch_all_replies(topic_id, client),
                        expected,
                    )
                return None, False
        result = get_v2ex_topic_info(topic_id, client)
        if not (result and result.result):
            mark_run_partial()
            return None, True
        topic = result.result
        expected = min(topic.replies, V2EX_MAX_REPLIES)
        if (
            is_db_only()
            and expected > 0
            and (
                force
                or not v2ex_projection.replies_complete(
                    get_database(),
                    topic_id,
                    expected,
                )
            )
        ):
            _warn_reply_gap(
                topic_id,
                fetch_all_replies(topic_id, client),
                expected,
            )
        return topic, False
    except Exception as exc:
        mark_run_partial()
        print(f'Skip v2ex topic {topic_id}: {exc}')
        return None, True


def export(
    output_dir: str,
    index_writer: IndexWriter,
    force: bool = False,
) -> None:
    """导出 V2EX 收藏主题。"""
    client = V2exClient()
    page = 1
    previous_ids: list[int] | None = None
    while True:
        id_list = get_fav_list_topic_id_page(page, client)
        if not id_list:
            break
        if id_list == previous_ids:
            print('分页返回重复数据，停止')
            break
        previous_ids = id_list
        page += 1
        for topic_id in id_list:
            try:
                topic, _failed = _ensure_topic_data(topic_id, client, force)
                if topic is None:
                    continue
                filename = get_clean_filename(f'{topic_id}-{topic.title}')
                if stop_if_output_exists(
                    output_dir,
                    filename,
                    index_writer=index_writer,
                    section_name='v2ex',
                    force=force,
                ):
                    return
                created_time = datetime.fromtimestamp(topic.created).strftime(
                    '%Y-%m-%dT%H:%M:%S%z',
                )
                modified_time = datetime.fromtimestamp(topic.last_modified).strftime(
                    '%Y-%m-%dT%H:%M:%S%z',
                )
                webpage = WebPage(
                    comments=True,
                    draft=True,
                    title=topic.title,
                    source=topic.url,
                    created=created_time,
                    modified=modified_time,
                    type='archive-web',
                )
                write_markdown_output(
                    output_dir,
                    filename,
                    webpage.__dict__,
                    topic.content,
                )

                print(f'Done: {topic.title}')
                add_index_entry(
                    index_writer,
                    link_target=build_link_target(filename),
                    title=topic.title,
                )
            except Exception as exc:
                # 单条主题失败只跳过该条，抓取、写文件和索引异常都不中断整批同步
                mark_run_partial()
                print(f'Skip v2ex topic {topic_id}: {exc}')
                continue
    index_writer.flush('v2ex', '导出完成index')


def export_tipped(force: bool = False) -> None:
    """Ingest topics discovered from sent-thanks transactions, DB only.

    Paging stops early when a whole balance page is already projected, but the
    topic scan below always includes previously tipped topics: earlier runs may
    have been cut short by the API quota, and only a full scan repairs them.
    """
    client = V2exClient()
    connection = get_database()
    new_entries: list[ThanksEntry] = []
    previous_keys: list[str] | None = None
    max_page: int | None = None
    page = 1

    while True:
        balance_page = get_balance_page(page, client)
        if not balance_page.has_table:
            # 维护页/风控页没有流水表：继续翻页只会拿到更多空页，且不能把
            # “没抓到流水”当成“已完整观察”，所以按 partial 结束本轮。
            mark_run_partial()
            print(f'警告: 余额页第 {page} 页缺少流水表，HTML 结构可能变化')
            break
        if max_page is None:
            max_page = balance_page.max_page
        if page == 1 and not balance_page.transaction_keys:
            # 表在但一行流水都解析不出来：新账号为空历史，老账号则多半是行
            # 结构变了。两种情况都只告警，不改变 success 的判定基础。
            print(
                '警告: 余额页第 1 页解析不到任何流水，可能为空历史或 HTML 行结构变化',
            )
        new_entries.extend(balance_page.thanks)

        if (
            not force
            and balance_page.thanks
            and v2ex_projection.thanks_page_known(
                connection,
                balance_page.thanks,
            )
        ):
            mark_run_partial()
            print('余额页已全部入库，停止翻页')
            break
        if max_page is not None and page >= max_page:
            break
        if balance_page.transaction_keys == previous_keys:
            print('余额分页返回重复数据，停止')
            break
        previous_keys = balance_page.transaction_keys
        page += 1

    topic_ids: list[int] = []
    seen: set[int] = set()
    for entry in new_entries:
        if entry.topic_id not in seen:
            seen.add(entry.topic_id)
            topic_ids.append(entry.topic_id)
    # Existing tipped topics keep their recency order and are appended after
    # this run's discoveries, so their pending detail/reply gaps still retry.
    for topic_id in v2ex_projection.tipped_topic_ids(connection):
        if topic_id not in seen:
            seen.add(topic_id)
            topic_ids.append(topic_id)

    print(f'投币主题待检查: {len(topic_ids)} 个')
    failures = 0
    for topic_id in topic_ids:
        _topic, failed = _ensure_topic_data(topic_id, client, force)
        failures = failures + 1 if failed else 0
        if failures >= V2EX_MAX_CONSECUTIVE_FAILURES:
            print(
                f'连续 {failures} 个主题抓取失败，停止本轮扫描，剩余主题留给下一轮',
            )
            break
