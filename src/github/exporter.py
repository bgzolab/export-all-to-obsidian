"""GitHub star 导出流程。"""

from datetime import datetime
import re

from export_runtime.exporter_support import add_index_entry
from export_runtime.exporter_support import build_link_target
from export_runtime.exporter_support import resolve_output_prefix
from export_runtime.exporter_support import stop_if_output_exists
from export_runtime.exporter_support import write_raw_markdown_output
from export_runtime.index_writer import IndexWriter
from github.client import get_repository_readme
from github.client import get_starred_repositories
from github.entity import GitHubStarredResponseItem
from utils.file_utils import get_clean_filename


def build_template_context(
    item: GitHubStarredResponseItem,
    readme: str,
    export_time: str,
    prefix: str,
) -> dict[str, str]:
    """构造 GitHub 模板渲染上下文。"""
    repo_slug = get_clean_filename(f"{item.owner_login}-{item.repo_name}")
    topics = ", ".join(item.topics)

    return {
        "authors": item.owner_login,
        "name": item.repo_name,
        "created_time": item.created_at,
        "export_time": export_time,
        "description": item.description,
        "url": item.html_url,
        "readme": readme,
        "full_name": item.full_name,
        "owner_login": item.owner_login,
        "language": item.language,
        "topics": topics,
        "stargazers_count": str(item.stargazers_count),
        "forks_count": str(item.forks_count),
        "open_issues_count": str(item.open_issues_count),
        "fork": str(item.fork),
        "archived": str(item.archived),
        "private": str(item.private),
        "homepage": item.homepage,
        "license": item.license,
        "updated_at": item.updated_at,
        "pushed_at": item.pushed_at,
        "starred_at": item.starred_at,
        "repo_filename": f"{prefix}{repo_slug}.md",
        "prefix": prefix,
    }


def render_github_template(
    template_content: str,
    context: dict[str, str],
) -> str:
    """将 `{{variable}}` 占位符替换为具体字符串。"""

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return context.get(key, "")

    return re.sub(r"\{\{\s*([^{}]+?)\s*\}\}", _replace, template_content)


def export(
    output_dir: str,
    template_path: str,
    index_writer: IndexWriter,
    force: bool = False,
    prefix: str | None = None,
) -> None:
    """导出当前认证用户的 GitHub star 仓库。"""
    resolved_prefix = resolve_output_prefix(prefix)
    with open(template_path, "r", encoding="utf-8") as file:
        template_content = file.read()

    page = 1
    per_page = 100
    while True:
        items = get_starred_repositories(page, per_page)
        if not items:
            break

        export_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
        for item in items:
            repo_slug = get_clean_filename(f"{item.owner_login}-{item.repo_name}")
            if stop_if_output_exists(
                output_dir,
                repo_slug,
                index_writer=index_writer,
                section_name="github",
                force=force,
                prefix=resolved_prefix,
            ):
                return

            readme = get_repository_readme(item.owner_login, item.repo_name)
            context = build_template_context(
                item,
                readme,
                export_time,
                resolved_prefix,
            )
            content = render_github_template(template_content, context)
            write_raw_markdown_output(output_dir, repo_slug, content, resolved_prefix)
            add_index_entry(
                index_writer,
                link_target=build_link_target(
                    repo_slug,
                    prefix=resolved_prefix,
                    include_extension=True,
                ),
                title=item.full_name,
            )
            print(f"Done: {item.full_name}")

        page += 1

    index_writer.flush("github")