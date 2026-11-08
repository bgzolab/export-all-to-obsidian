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
from v2ex.mytopic import get_fav_list_topic_id_page
from v2ex.replies import fetch_all_replies
from v2ex.topic import get_v2ex_topic_info


def export(
    output_dir: str,
    index_writer: IndexWriter,
    force: bool = False,
) -> None:
    """导出 V2EX 收藏主题。"""
    client = V2exClient()
    page = 1
    while True:
        id_list = get_fav_list_topic_id_page(page, client)
        if not id_list:
            break
        page += 1
        for topic_id in id_list:
            try:
                if is_db_only() and not force:
                    connection = get_database()
                    reply_count = v2ex_projection.topic_reply_count(
                        connection,
                        topic_id,
                    )
                    if reply_count is not None:
                        if reply_count > 0 and not v2ex_projection.replies_exist(
                            connection,
                            topic_id,
                        ):
                            fetch_all_replies(topic_id, client)
                        continue
                result = get_v2ex_topic_info(topic_id)
                if not (result and result.result):
                    mark_run_partial()
                    continue
                topic = result.result
                if (
                    is_db_only()
                    and topic.replies
                    and (
                        force
                        or not v2ex_projection.replies_exist(
                            get_database(),
                            topic_id,
                        )
                    )
                ):
                    fetch_all_replies(topic_id, client)
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
