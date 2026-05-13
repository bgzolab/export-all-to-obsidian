"""微博导出流程。"""

from datetime import datetime

from export_runtime.exporter_support import add_index_entry
from export_runtime.exporter_support import stop_if_output_exists
from export_runtime.exporter_support import write_markdown_output
from export_runtime.index_writer import IndexWriter
from utils.file_utils import get_clean_filename
from utils.template import WebPage
from weibo.like import get_weibo_like_list
from weibo.post import get_weibo_longtext_by_id


def handle_weibo_pic(item) -> str:
    """生成微博图片 Markdown。"""
    if (
        item.pic_num is None
        or item.pic_num == 0
        or item.pic_ids is None
        or len(item.pic_ids) == 0
    ):
        return ""
    result = ""
    pic_infos = item.pic_infos
    for pic_id in item.pic_ids:
        pic_info = pic_infos[pic_id]
        url = pic_info.largest["url"]
        result += f"![{pic_id}]({url})\n\n"
    return result


def export(uid: int, output_dir: str, index_writer: IndexWriter,
           force: bool = False) -> None:
    """导出微博点赞。"""
    page_index = 1
    while True:
        page = get_weibo_like_list(uid, page_index)
        if page is None:
            print("获取微博喜欢列表失败，请检查接口")
            break

        if page.ok != 1:
            print("获取微博喜欢列表失败，请检查接口")
            break

        item_list = page.data.list
        if len(item_list) == 0:
            break

        for item in item_list:
            try:
                post_id = item.mblogid
                post_user = item.user.id
                post_url = f"https://weibo.com/{post_user}/{post_id}"
                filename = f"{post_user}-{post_id}"

                if stop_if_output_exists(
                    output_dir,
                    filename,
                    index_writer=index_writer,
                    section_name="weibo",
                    force=force,
                ):
                    return

                author_name = item.user.screen_name
                context_digest = get_clean_filename(item.text_raw[:10])
                title = author_name + ":" + context_digest

                article = item.text_raw
                if item.isLongText:
                    longtext = get_weibo_longtext_by_id(post_id)
                    if longtext is not None:
                        article = longtext

                dt_obj = datetime.strptime(
                    item.created_at,
                    "%a %b %d %H:%M:%S %z %Y",
                )
                webpage = WebPage(
                    comments=True,
                    draft=True,
                    title=title,
                    source=post_url,
                    created=dt_obj.strftime("%Y-%m-%dT%H:%M:%S"),
                    modified=dt_obj.strftime("%Y-%m-%dT%H:%M:%S"),
                    type="archive-web",
                )
                write_markdown_output(
                    output_dir,
                    filename,
                    webpage.__dict__,
                    article + "\n\n" + handle_weibo_pic(item),
                )

                print(f"Done: {title}")
                add_index_entry(
                    index_writer,
                    link_target=f"~{filename}",
                    title=title,
                )

            except Exception as error:
                print(f"处理报文发生错误: {error}，微博可能已经被删除，跳过处理")

        page_index += 1

    index_writer.flush("weibo")