"""导出流程的轻量共用辅助函数。"""

import os
from typing import Any, Mapping

from export_runtime.index_writer import IndexWriter
from utils.file_utils import output_content_to_file_path
from utils.md_utils import dump_markdown_with_frontmatter


def build_output_path(output_dir: str, filename: str) -> str:
    """返回标准 Markdown 输出路径。"""
    return os.path.join(output_dir, f"~{filename}.md")


def stop_if_output_exists(
    output_dir: str,
    filename: str,
    *,
    index_writer: IndexWriter,
    section_name: str,
    flush_title: str | None = "导出index",
    force: bool = False,
    message: str = "已存在: {filename}.md，同步结束",
) -> bool:
    """检测增量剪枝条件并在命中时刷新索引。"""
    if force:
        return False

    file_path = build_output_path(output_dir, filename)
    if not os.path.exists(file_path):
        return False

    print(message.format(filename=filename))
    index_writer.flush(section_name, flush_title)
    return True


def write_markdown_output(
    output_dir: str,
    filename: str,
    metadata: Mapping[str, Any],
    content: str,
) -> None:
    """生成 front matter 并写入 Markdown 文件。"""
    markdown = dump_markdown_with_frontmatter(dict(metadata), content)
    output_content_to_file_path(output_dir, filename, markdown, "md")


def add_index_entry(
    index_writer: IndexWriter,
    *,
    link_target: str,
    title: str,
) -> None:
    """追加一条标准索引项。"""
    index_writer.add(f"- [[{link_target}|{title}]]")