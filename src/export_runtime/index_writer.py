"""索引输出器。"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class IndexWriter:
    """管理导出索引的累计与输出位置。"""

    file_path: Optional[str] = None
    title: str = "输出index"
    _entries: list[str] | None = None

    def __post_init__(self) -> None:
        """初始化索引条目列表。"""
        if self._entries is None:
            self._entries = []

    def add(self, entry: str) -> None:
        """追加一条索引内容。"""
        if entry:
            self._entries.append(entry)

    def render(self) -> str:
        """渲染最终索引文本。"""
        return "\n".join(self._entries)

    def flush(self, section_name: str, title: Optional[str] = None) -> None:
        """将索引输出到控制台或指定 Markdown 文件。"""
        output_title = title or self.title
        content = self.render()
        if self.file_path:
            directory = os.path.dirname(self.file_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            self._write_markdown_index(section_name, output_title, content)
        else:
            print(f"{output_title}:\n{content}")

        self._entries.clear()

    def _write_markdown_index(
        self,
        section_name: str,
        output_title: str,
        content: str,
    ) -> None:
        """将一次导出结果写入对应模块的 Markdown 分节。"""
        heading = self._format_section_heading(section_name)
        run_block = self._format_run_block(output_title, content)
        existing_content = ""

        if os.path.exists(self.file_path):
            with open(self.file_path, "r", encoding="utf-8") as file:
                existing_content = file.read().strip()

        updated_content = self._merge_section(existing_content, heading, run_block)

        with open(self.file_path, "w", encoding="utf-8") as file:
            file.write(updated_content)
            if updated_content:
                file.write("\n")

        print(f"{output_title}已写入: {self.file_path}")

    @staticmethod
    def _format_section_heading(section_name: str) -> str:
        """格式化模块级二级标题。"""
        return f"## {section_name}"

    @staticmethod
    def _format_run_block(output_title: str, content: str) -> str:
        """格式化单次导出块。"""
        normalized_content = content.strip()
        return normalized_content

    @classmethod
    def _merge_section(
        cls,
        existing_content: str,
        heading: str,
        run_block: str,
    ) -> str:
        """将本次导出块并入目标模块分节，保留已有顺序。"""
        if not existing_content:
            return f"{heading}\n\n{run_block}"

        sections = existing_content.split("\n## ")
        normalized_sections = []
        for index, section in enumerate(sections):
            if index == 0:
                normalized_sections.append(section)
            else:
                normalized_sections.append(f"## {section}")

        merged_sections = []
        found = False
        for section in normalized_sections:
            if section.startswith(f"{heading}\n") or section == heading:
                found = True
                if run_block:
                    merged_sections.append(f"{section.rstrip()}\n\n{run_block}")
                else:
                    merged_sections.append(section.rstrip())
            else:
                merged_sections.append(section.rstrip())

        if not found and run_block:
            merged_sections.append(f"{heading}\n\n{run_block}")

        return "\n\n".join(part for part in merged_sections if part).strip()