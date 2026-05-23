"""GitHub API 地址构造。"""

GITHUB_API_BASE_URL = "https://api.github.com"


def build_starred_repos_url(page: int, per_page: int) -> str:
    """返回认证用户 star 仓库列表地址。"""
    return (
        f"{GITHUB_API_BASE_URL}/user/starred"
        f"?per_page={per_page}&page={page}"
    )


def build_readme_url(owner: str, repo: str) -> str:
    """返回仓库 README API 地址。"""
    return f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/readme"