"""GitHub star 仓库响应对象。"""

from dataclasses import dataclass
from typing import Any


@dataclass
class GitHubStarredResponseItem:
    """承载单个 starred repository 的核心字段。"""

    full_name: str
    html_url: str
    description: str
    owner_login: str
    repo_name: str
    language: str
    topics: list[str]
    stargazers_count: int
    forks_count: int
    open_issues_count: int
    fork: bool
    archived: bool
    private: bool
    homepage: str
    license: str
    created_at: str
    updated_at: str
    pushed_at: str
    starred_at: str
    readme: str = ""

    @staticmethod
    def from_api(data: dict[str, Any]) -> "GitHubStarredResponseItem":
        """将 GitHub starred API 响应映射为内部对象。"""
        repo = data.get("repo") or data
        owner = repo.get("owner") or {}
        license_data = repo.get("license") or {}
        topics = repo.get("topics") or []

        return GitHubStarredResponseItem(
            full_name=repo.get("full_name", ""),
            html_url=repo.get("html_url", ""),
            description=repo.get("description") or "",
            owner_login=owner.get("login", ""),
            repo_name=repo.get("name", ""),
            language=repo.get("language") or "",
            topics=[str(topic) for topic in topics if topic],
            stargazers_count=repo.get("stargazers_count", 0),
            forks_count=repo.get("forks_count", 0),
            open_issues_count=repo.get("open_issues_count", 0),
            fork=bool(repo.get("fork", False)),
            archived=bool(repo.get("archived", False)),
            private=bool(repo.get("private", False)),
            homepage=repo.get("homepage") or "",
            license=(
                license_data.get("spdx_id")
                or license_data.get("name")
                or ""
            ),
            created_at=repo.get("created_at", ""),
            updated_at=repo.get("updated_at", ""),
            pushed_at=repo.get("pushed_at", ""),
            starred_at=data.get("starred_at", ""),
            readme=data.get("readme") or "",
        )