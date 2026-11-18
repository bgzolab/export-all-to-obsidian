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
) -> TopicResult | None:
    """Fetch a topic's missing detail/replies, returning None when nothing to render.

    Returns None in two cases: the topic is already projected under
    ``--db-only`` (after repairing any reply gap), or fetching failed. Both
    mean the caller can skip Markdown; failures are per-topic and marked
    partial instead of aborting the batch.
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
                return None
        result = get_v2ex_topic_info(topic_id)
        if not (result and result.result):
            mark_run_partial()
            return None
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
        return topic
    except Exception as exc:
        mark_run_partial()
        print(f'Skip v2ex topic {topic_id}: {exc}')
        return None


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
                topic = _ensure_topic_data(topic_id, client, force)
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
        if max_page is None:
            max_page = balance_page.max_page
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
    for topic_id in topic_ids:
        _ensure_topic_data(topic_id, client, force)
