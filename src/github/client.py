"""GitHub API 客户端。"""

import base64
import os

import requests

from github.api_endpoints import build_readme_url
from github.api_endpoints import build_starred_repos_url
from github.entity import GitHubStarredResponseItem


def get_github_token() -> str:
    """读取 GitHub 访问令牌。"""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")
    return token


def get_starred_repositories(
    page: int,
    per_page: int = 100,
) -> list[GitHubStarredResponseItem]:
    """拉取当前认证用户的 starred repositories。"""
    response = requests.get(
        build_starred_repos_url(page, per_page),
        headers={
            "Authorization": f"Bearer {get_github_token()}",
            "Accept": "application/vnd.github.star+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub starred request failed with status {response.status_code}",
        )

    payload = response.json()
    return [GitHubStarredResponseItem.from_api(item) for item in payload]


def get_repository_readme(owner: str, repo: str) -> str:
    """获取仓库 README 内容，缺失时返回空字符串。"""
    response = requests.get(
        build_readme_url(owner, repo),
        headers={
            "Authorization": f"Bearer {get_github_token()}",
            "Accept": "application/vnd.github.raw+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )
    if response.status_code == 404:
        return ""
    if response.status_code != 200:
        print(
            f"GitHub README request failed for {owner}/{repo}: "
            f"status={response.status_code}",
        )
        return ""

    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        payload = response.json()
        encoded_content = payload.get("content") or ""
        if not encoded_content:
            return ""
        normalized = encoded_content.replace("\n", "")
        return base64.b64decode(normalized).decode("utf-8", errors="ignore")

    return response.text