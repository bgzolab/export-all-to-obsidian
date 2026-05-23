"""知乎导出流程。"""

from datetime import datetime

from export_runtime.exporter_support import add_index_entry
from export_runtime.exporter_support import build_link_target
from export_runtime.exporter_support import stop_if_output_exists
from export_runtime.exporter_support import write_markdown_output
from export_runtime.index_writer import IndexWriter
from utils.file_utils import get_clean_filename
from utils.md_utils import html_to_markdown_with_html2text
from utils.template import WebPage
from zhihu.collection import get_collection_page


def export(collection: str, output_dir: str, index_writer: IndexWriter) -> None:
    """导出知乎收藏夹。"""
    offset = 0
    limit = 20

    while True:
        page = get_collection_page(collection, offset, limit)
        for item in page.data:
            content = item.content
            article = ""
            if isinstance(content.content, list):
                title = item.content.content[0]["title"]
                article = content.content[0]["content"]
            else:
                title = content.title or content.question.title
                article = content.content

            content_id = content.id
            filename = get_clean_filename(f"{content_id}-{title}")
            if stop_if_output_exists(
                output_dir,
                filename,
                index_writer=index_writer,
                section_name="zhihu",
            ):
                return

            created_time = datetime.fromtimestamp(content.created_time).strftime(
                "%Y-%m-%dT%H:%M:%S%z",
            )
            modified_time = datetime.fromtimestamp(content.updated_time).strftime(
                "%Y-%m-%dT%H:%M:%S%z",
            )
            webpage = WebPage(
                comments=True,
                draft=True,
                title=title,
                source=content.url,
                created=created_time,
                modified=modified_time,
                type="archive-web",
            )
            write_markdown_output(
                output_dir,
                filename,
                webpage.__dict__,
                html_to_markdown_with_html2text(article),
            )

            print(f"Done: {title}")
            add_index_entry(
                index_writer,
                link_target=build_link_target(filename),
                title=title,
            )

        if not page.data:
            break
        offset += limit

    index_writer.flush("zhihu")