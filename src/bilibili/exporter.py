"""Bilibili 导出流程。"""

from datetime import datetime

from bilibili.favlist import get_bilibili_favlistd
from export_runtime.exporter_support import add_index_entry
from export_runtime.exporter_support import build_link_target
from export_runtime.exporter_support import stop_if_output_exists
from export_runtime.exporter_support import write_markdown_output
from export_runtime.index_writer import IndexWriter
from utils.file_utils import get_clean_filename
from utils.template import Video


def export(fid: int, output_dir: str, index_writer: IndexWriter,
           force: bool = False) -> None:
    """导出 Bilibili 收藏夹。"""
    page = 1
    size = 20
    while True:
        favlist_response = get_bilibili_favlistd(fid, page, size)
        if (
            not favlist_response
            or not favlist_response.data
            or len(favlist_response.data.medias) == 0
        ):
            break

        for item in favlist_response.data.medias:
            try:
                filename = f"{item.bvid}-{get_clean_filename(item.title)}"
                if stop_if_output_exists(
                    output_dir,
                    filename,
                    index_writer=index_writer,
                    section_name="bilibili",
                    force=force,
                ):
                    return

                pubtime_date = datetime.fromtimestamp(item.pubtime).strftime(
                    "%Y-%m-%dT%H:%M:%S%z",
                )
                fav_date = datetime.fromtimestamp(item.fav_time).strftime(
                    "%Y-%m-%dT%H:%M:%S%z",
                )
                intro = item.intro.replace("\n", " ").replace("\r", " ")

                webpage = Video(
                    comments=True,
                    draft=True,
                    title=item.title,
                    cover=item.cover,
                    author=item.upper.name,
                    created=fav_date,
                    modified=fav_date,
                    published=pubtime_date,
                    description=intro,
                    source=f"https://www.bilibili.com/video/{item.bvid}",
                    tags=["video/bilibili"],
                    type="video",
                )

                content = f"""
# {item.title}

## Source

<iframe src='https://player.bilibili.com/player.html?isOutside=true&bvid={item.bvid}&p=1&autoplay=false' style='height:40vh;width:100%' class='iframe-radius' allow='fullscreen'></iframe>
<center>via: <a href='https://www.bilibili.com/video/{item.bvid}' target='_blank' class='external-link'>https://www.bilibili.com/video/{item.bvid}</a></center>

## Notes

"""
                if item.title == "已失效视频":
                    content = (
                        f"\n\n> 监测到视频已失效，请尝试去 "
                        f"https://www.jijidown.com/video/{item.bvid}/ 或 "
                        f"https://www.biliplus.com/video/{item.bvid} "
                        "查看是否有缓存存在，如果没有请节哀.\n\n"
                        + content
                    )

                write_markdown_output(
                    output_dir,
                    filename,
                    webpage.__dict__,
                    content,
                )

                print(f"Done: {item.title}")
                add_index_entry(
                    index_writer,
                    link_target=build_link_target(filename),
                    title=item.title,
                )

            except Exception as error:
                print(f"处理报文发生错误: {error}，跳过处理")
        page += 1

    index_writer.flush("bilibili")