"""导出流程的轻量共用辅助函数。"""

import os
from typing import Any, Mapping

from app.context import get_output_prefix
from export_runtime.index_writer import IndexWriter
from utils.file_utils import output_content_to_file_path
from utils.md_utils import dump_markdown_with_frontmatter


def resolve_output_prefix(prefix: str | None = None) -> str:
    """解析导出文件前缀，优先使用显式参数，其次使用全局上下文。"""
    if prefix is not None:
        return prefix
    return get_output_prefix()


def build_output_path(
    output_dir: str,
    filename: str,
    prefix: str | None = None,
) -> str:
    """返回标准 Markdown 输出路径。"""
    resolved_prefix = resolve_output_prefix(prefix)
    return os.path.join(output_dir, f"{resolved_prefix}{filename}.md")


def build_link_target(
    filename: str,
    *,
    prefix: str | None = None,
    include_extension: bool = False,
) -> str:
    """返回索引使用的链接目标。"""
    resolved_prefix = resolve_output_prefix(prefix)
    suffix = ".md" if include_extension else ""
    return f"{resolved_prefix}{filename}{suffix}"


def stop_if_output_exists(
    output_dir: str,
    filename: str,
    *,
    index_writer: IndexWriter,
    section_name: str,
    flush_title: str | None = "导出index",
    force: bool = False,
    message: str = "已存在: {filename}.md，同步结束",
    prefix: str | None = None,
) -> bool:
    """检测增量剪枝条件并在命中时刷新索引。"""
    if force:
        return False

    file_path = build_output_path(output_dir, filename, prefix)
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
    prefix: str | None = None,
) -> None:
    """生成 front matter 并写入 Markdown 文件。"""
    markdown = dump_markdown_with_frontmatter(dict(metadata), content)
    output_content_to_file_path(
        output_dir,
        filename,
        markdown,
        "md",
        resolve_output_prefix(prefix),
    )


def write_raw_markdown_output(
    output_dir: str,
    filename: str,
    content: str,
    prefix: str | None = None,
) -> None:
    """直接写入 Markdown 文本，不额外生成 front matter。"""
    output_content_to_file_path(
        output_dir,
        filename,
        content,
        "md",
        resolve_output_prefix(prefix),
    )


def add_index_entry(
    index_writer: IndexWriter,
    *,
    link_target: str,
    title: str,
) -> None:
    """追加一条标准索引项。"""
    index_writer.add(f"- [[{link_target}|{title}]]")