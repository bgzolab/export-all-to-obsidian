"""Bangumi 导出流程。"""

import os
from datetime import datetime

from bangumi.client import BangumiClient
from bangumi.collection import get_all_collections_by_pages
from bangumi.enum import CollectionType, SubjectType
from bangumi.subject import get_subject_character, get_subject_info
from export_runtime.exporter_support import build_link_target
from export_runtime.exporter_support import build_output_path
from export_runtime.exporter_support import resolve_output_prefix
from export_runtime.index_writer import IndexWriter
from utils.file_utils import get_clean_filename


def export(
    subject_type: int,
    collection_type: int,
    output_dir: str,
    template_path: str,
    index_writer: IndexWriter,
    force: bool = False,
) -> None:
    """导出指定 Bangumi 收藏类型。"""
    client = BangumiClient()
    username = client.get_user()["username"]
    limit = 30
    offset = 0

    while True:
        results = get_all_collections_by_pages(
            username,
            subject_type,
            collection_type,
            limit=limit,
            offset=offset,
        )
        if not results:
            break
        offset += limit
        for result in results:
            try:
                success, filename, title = write_subject_markdown(
                    subject_id=result.subject_id,
                    collection_type=collection_type,
                    output_dir=output_dir,
                    template_path=template_path,
                    force=force,
                )
                if success and filename and title:
                    index_writer.add(f"- [[{filename}|{title}]]")
                elif not force:
                    print(f"写入失败: {filename}")
                    index_writer.flush("bangumi")
                    return
            except Exception as error:
                print(
                    f"跳过:{result.subject.name}, "
                    f"subject_id={result.subject_id}, error={error}",
                )
            print(f"处理完成={result.subject_id}")
    index_writer.flush("bangumi")


def sync_all_collections(
    subject_type: int,
    output_dir: str,
    template_path: str,
    index_writer: IndexWriter,
    force: bool = False,
) -> None:
    """导出某个主题类型下的全部收藏分类。"""
    for collection_type in CollectionType.all():
        print("正在处理: ", collection_type)
        export(
            subject_type=subject_type,
            collection_type=collection_type.value,
            output_dir=output_dir,
            template_path=template_path,
            index_writer=index_writer,
            force=force,
        )
        print("处理完成: ", collection_type)


def write_subject_markdown(
    subject_id: int,
    collection_type: int,
    output_dir: str,
    template_path: str,
    force: bool = False,
) -> tuple[bool, str, str]:
    """根据 subject id 渲染并写入 Bangumi Markdown。"""
    subject = get_subject_info(subject_id)
    if not subject:
        print(f"未获取到条目详情: {subject_id}")
        return True, "", ""

    subject_type = subject.type_id
    subject_type_en = SubjectType.get_name_en(subject_type)
    collection_type_en = CollectionType.get_name_en(collection_type)
    tags = [f"bangumi/{collection_type_en}", f"bangumi/{subject_type_en}"]
    aliases_set = {subject.name}
    website_set: set[str] = set()
    if subject.name_cn:
        aliases_set.add(subject.name_cn)

    if subject.infobox:
        for item in subject.infobox:
            if item.get("key") in {"官方网站", "website"}:
                website_set.update(parse_infobox_value(item))
            if item.get("key") == "别名":
                aliases_set.update(parse_infobox_value(item))

    created_date = (
        (subject.date or datetime.now().strftime("%Y-%m-%d"))
        + datetime.now().strftime("T%H:%M:%S%z")
    )
    title = subject.name_cn or subject.name or ""
    prefix = resolve_output_prefix()
    filename_without_extension = (
        str(subject_id)
        + "-"
        + get_clean_filename(title or str(subject.id))
    )
    filename = build_link_target(
        filename_without_extension,
        prefix=prefix,
        include_extension=True,
    )
    output_path = build_output_path(
        os.path.join(output_dir, subject_type_en),
        filename_without_extension,
        prefix,
    )
    if os.path.exists(output_path) and not force:
        print(f"已存在，提前结束: {filename}")
        return False, "", ""

    with open(template_path, "r", encoding="utf-8") as file:
        template = file.read()

    content = template
    content = content.replace("{{tags}}", str(tags))
    content = content.replace("{{aliases}}", str(list(aliases_set)))
    content = content.replace("{{website}}", str(list(website_set)))
    content = content.replace("{{title}}", title)
    content = content.replace("{{bangumi}}", str(subject.id))
    content = content.replace(
        "{{cover}}",
        subject.images.medium if subject.images else "",
    )
    content = content.replace("{{created}}", created_date)
    content = content.replace(
        "{{modified}}",
        datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
    )
    content = content.replace(
        "{{rating}}",
        str(subject.rating.score)
        if subject.rating and subject.rating.score
        else "",
    )
    content = content.replace("{{type}}", "bangumi/" + subject_type_en)
    content = content.replace(
        "{{characters}}",
        get_output_character_string(subject_id),
    )
    content = content.replace("{{summary}}", subject.summary or "")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        file.write(content)
    print(f"写入完成: {output_path}")
    return True, filename, title


def parse_infobox_value(item: dict) -> list[str]:
    """提取 infobox value 为字符串列表。"""
    value = item.get("value")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [entry.get("v") for entry in value if isinstance(entry, dict)]
    return []


def get_output_character_string(subject_id: int) -> str:
    """按横向 Markdown 表格输出条目角色信息。"""

    def _escape_cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ").strip()

    character_list = get_subject_character(subject_id)
    if not character_list:
        return ""

    relation_cells = []
    name_cells = []
    image_cells = []

    for character in character_list:
        relation_cells.append(_escape_cell(character.relation or ""))
        name_cells.append(_escape_cell(character.name or ""))
        image_url = character.images.medium if character.images else ""
        image_cells.append(f"![]({image_url})" if image_url else "")

    separator_row = [" --- " for _ in character_list]

    return "\n".join(
        [
            "|" + "|".join(relation_cells) + "|",
            "|" + "|".join(separator_row) + "|",
            "|" + "|".join(name_cells) + "|",
            "|" + "|".join(image_cells) + "|",
        ],
    )