"""Qireader 导出流程。"""

from datetime import datetime

from export_runtime.exporter_support import add_index_entry
from export_runtime.exporter_support import build_link_target
from export_runtime.exporter_support import stop_if_output_exists
from export_runtime.exporter_support import write_markdown_output
from export_runtime.index_writer import IndexWriter
from qireader.getext import get_html_text_from_url
from qireader.readlatter import get_list_from_read_latter
from utils.file_utils import get_clean_filename
from utils.md_utils import html_to_markdown_with_html2text
from utils.template import WebPage


def export(tag: str, output_dir: str, index_writer: IndexWriter) -> None:
    """导出稍后读内容。"""
    older_than = None

    while True:
        entries = get_list_from_read_latter(tag, older_than)
        if not entries:
            break

        for entry in entries:
            filename = get_clean_filename(entry.title)
            if stop_if_output_exists(
                output_dir,
                filename,
                index_writer=index_writer,
                section_name="qireader",
            ):
                return

            timestamp_seconds = int(entry.timestamp) / 1_000_000_000
            created_at = datetime.fromtimestamp(timestamp_seconds).strftime(
                "%Y-%m-%dT%H:%M:%S%z",
            )
            webpage = WebPage(
                comments=True,
                draft=True,
                title=entry.title,
                source=entry.url,
                created=created_at,
                modified=created_at,
                type="archive-web",
            )

            content = ""
            try:
                content = html_to_markdown_with_html2text(
                    get_html_text_from_url(entry.url),
                )
            except Exception:
                print(
                    f"处理{filename}时发生异常，源地址可以已经删除，"
                    "直接跳过，请考虑手动处理！",
                )

            write_markdown_output(
                output_dir,
                filename,
                webpage.__dict__,
                content,
            )

            print(f"Done: {entry.title}")
            add_index_entry(
                index_writer,
                link_target=build_link_target(filename),
                title=entry.title,
            )
        older_than = str(entries[-1].timestamp)

    index_writer.flush("qireader", "导出index")