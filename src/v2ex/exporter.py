"""V2EX 导出流程。"""

from datetime import datetime

from export_runtime.exporter_support import add_index_entry
from export_runtime.exporter_support import build_link_target
from export_runtime.exporter_support import stop_if_output_exists
from export_runtime.exporter_support import write_markdown_output
from export_runtime.index_writer import IndexWriter
from utils.file_utils import get_clean_filename
from utils.template import WebPage
from v2ex.mytopic import get_fav_list_topic_id_page
from v2ex.topic import get_v2ex_topic_info


def export(output_dir: str, index_writer: IndexWriter) -> None:
    """导出 V2EX 收藏主题。"""
    page = 1
    while True:
        id_list = get_fav_list_topic_id_page(page)
        if not id_list:
            break
        page += 1
        for topic_id in id_list:
            result = get_v2ex_topic_info(topic_id)
            if not result:
                continue
            topic = result.result
            filename = get_clean_filename(f"{topic_id}-{topic.title}")
            if stop_if_output_exists(
                output_dir,
                filename,
                index_writer=index_writer,
                section_name="v2ex",
            ):
                return
            created_time = datetime.fromtimestamp(topic.created).strftime(
                "%Y-%m-%dT%H:%M:%S%z",
            )
            modified_time = datetime.fromtimestamp(topic.last_modified).strftime(
                "%Y-%m-%dT%H:%M:%S%z",
            )
            webpage = WebPage(
                comments=True,
                draft=True,
                title=topic.title,
                source=topic.url,
                created=created_time,
                modified=modified_time,
                type="archive-web",
            )
            write_markdown_output(
                output_dir,
                filename,
                webpage.__dict__,
                topic.content,
            )

            print(f"Done: {topic.title}")
            add_index_entry(
                index_writer,
                link_target=build_link_target(filename),
                title=topic.title,
            )
    index_writer.flush("v2ex", "导出完成index")