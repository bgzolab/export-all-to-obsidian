"""博客园导出流程。"""

from app.context import get_database, is_db_only, mark_run_partial
from cnblog.blog_post import get_cnblog_post_body_by_url
from cnblog.bookmark import get_bookmark_list
from db.projections import cnblog as cnblog_projection
from export_runtime.exporter_support import (
    add_index_entry,
    build_link_target,
    stop_if_output_exists,
    stop_if_page_known,
    write_markdown_output,
)
from export_runtime.index_writer import IndexWriter
from utils.file_utils import get_clean_filename
from utils.md_utils import html_to_markdown_with_bs
from utils.template import WebPage


def export(
    output_dir: str,
    index_writer: IndexWriter,
    force: bool = False,
) -> None:
    """导出博客园收藏。"""
    page_index = 1
    page_size = 100
    while True:
        bookmarks = get_bookmark_list(page_index, page_size)
        if not bookmarks:
            break
        for bookmark in bookmarks:
            try:
                filename = get_clean_filename(bookmark.Title)
                if stop_if_output_exists(
                    output_dir,
                    filename,
                    index_writer=index_writer,
                    section_name='cnblog',
                    flush_title=None,
                    force=force,
                    message='已存在，提前结束: {filename}.md',
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
                        type='archive-web',
                    )

                    skip_body = (
                        is_db_only()
                        and not force
                        and cnblog_projection.post_exists(
                            get_database(),
                            bookmark.LinkUrl,
                        )
                    )
                    body = ''
                    if not skip_body:
                        body = get_cnblog_post_body_by_url(bookmark.LinkUrl)
                        if not body:
                            mark_run_partial()

                    write_markdown_output(
                        output_dir,
                        filename,
                        webpage.__dict__,
                        html_to_markdown_with_bs(body),
                    )

                    print(f'Done: {bookmark.Title}')
                else:
                    print(f'Skip: {bookmark.Title}')
                add_index_entry(
                    index_writer,
                    link_target=build_link_target(filename),
                    title=bookmark.Title,
                )
            except Exception as error:
                mark_run_partial()
                print(f'Skip cnblog bookmark: {error}')
                continue

        bookmark_ids = [getattr(bookmark, 'WzLinkId', None) for bookmark in bookmarks]
        if is_db_only() and not force and bookmark_ids and all(bookmark_ids):
            known = cnblog_projection.known_bookmark_ids(
                get_database(),
                bookmark_ids,
            )
            if stop_if_page_known(bookmark_ids, known):
                break

        page_index += 1
    index_writer.flush('cnblog')
