"""博客园导出流程。"""

from cnblog.blog_post import get_cnblog_post_body_by_url
from cnblog.bookmark import get_bookmark_list
from export_runtime.exporter_support import add_index_entry
from export_runtime.exporter_support import build_link_target
from export_runtime.exporter_support import stop_if_output_exists
from export_runtime.exporter_support import write_markdown_output
from export_runtime.index_writer import IndexWriter
from utils.file_utils import get_clean_filename
from utils.md_utils import html_to_markdown_with_bs
from utils.template import WebPage


def export(output_dir: str, index_writer: IndexWriter) -> None:
    """导出博客园收藏。"""
    page_index = 1
    page_size = 100
    while True:
        bookmarks = get_bookmark_list(page_index, page_size)
        if not bookmarks:
            break
        for bookmark in bookmarks:
            filename = get_clean_filename(bookmark.Title)
            if stop_if_output_exists(
                output_dir,
                filename,
                index_writer=index_writer,
                section_name="cnblog",
                flush_title=None,
                message="已存在，提前结束: {filename}.md",
            ):
                return
            if bookmark.FromCNBlogs:
                webpage = WebPage(
                    comments=True,
                    draft=True,
                    title=bookmark.Title,
                    source=bookmark.LinkUrl,
                    created=bookmark.DateAdded,
                    modified=bookmark.DateAdded,
                    type="archive-web",
                )

                write_markdown_output(
                    output_dir,
                    filename,
                    webpage.__dict__,
                    html_to_markdown_with_bs(
                        get_cnblog_post_body_by_url(bookmark.LinkUrl),
                    ),
                )

                print(f"Done: {bookmark.Title}")
            else:
                print(f"Skip: {bookmark.Title}")
            add_index_entry(
                index_writer,
                link_target=build_link_target(filename),
                title=bookmark.Title,
            )
        page_index += 1
    index_writer.flush("cnblog")