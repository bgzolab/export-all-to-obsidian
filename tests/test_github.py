from pathlib import Path

import pytest
from click.testing import CliRunner


def test_github_starred_response_item_from_api_handles_fallbacks():
    from github.entity import GitHubStarredResponseItem

    item = GitHubStarredResponseItem.from_api(
        {
            "starred_at": "2026-05-23T00:00:00Z",
            "repo": {
                "full_name": "octocat/Hello-World",
                "html_url": "https://github.com/octocat/Hello-World",
                "description": None,
                "name": "Hello-World",
                "owner": {"login": "octocat"},
                "language": None,
                "topics": ["demo", None, "python"],
                "stargazers_count": 10,
                "forks_count": 2,
                "open_issues_count": 3,
                "fork": False,
                "archived": False,
                "private": False,
                "homepage": None,
                "license": {"name": "MIT License"},
                "created_at": "2020-01-01T00:00:00Z",
                "updated_at": "2020-01-02T00:00:00Z",
                "pushed_at": "2020-01-03T00:00:00Z",
            },
        },
    )

    assert item.full_name == "octocat/Hello-World"
    assert item.description == ""
    assert item.language == ""
    assert item.topics == ["demo", "python"]
    assert item.license == "MIT License"
    assert item.starred_at == "2026-05-23T00:00:00Z"


def test_get_github_token_requires_env(monkeypatch):
    from github.client import get_github_token

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="GITHUB_TOKEN is required"):
        get_github_token()


def test_get_starred_repositories_maps_payload(monkeypatch):
    from github.client import get_starred_repositories

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return [
                {
                    "starred_at": "2026-05-23T00:00:00Z",
                    "repo": {
                        "full_name": "octocat/Hello-World",
                        "html_url": "https://github.com/octocat/Hello-World",
                        "description": "Demo",
                        "name": "Hello-World",
                        "owner": {"login": "octocat"},
                        "language": "Python",
                        "topics": ["demo"],
                        "stargazers_count": 1,
                        "forks_count": 2,
                        "open_issues_count": 3,
                        "fork": False,
                        "archived": False,
                        "private": False,
                        "homepage": "",
                        "license": {"spdx_id": "MIT"},
                        "created_at": "2020-01-01T00:00:00Z",
                        "updated_at": "2020-01-02T00:00:00Z",
                        "pushed_at": "2020-01-03T00:00:00Z",
                    },
                },
            ]

    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    monkeypatch.setattr("github.client.requests.get", lambda *args, **kwargs: FakeResponse())

    result = get_starred_repositories(1)

    assert len(result) == 1
    assert result[0].full_name == "octocat/Hello-World"


def test_get_starred_repositories_raises_without_leaking_token(monkeypatch):
    from github.client import get_starred_repositories

    class FakeResponse:
        status_code = 401

        @staticmethod
        def json():
            return {"message": "Bad credentials"}

    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    monkeypatch.setattr("github.client.requests.get", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(RuntimeError) as exc_info:
        get_starred_repositories(1)

    assert "secret-token" not in str(exc_info.value)
    assert "status 401" in str(exc_info.value)


def test_get_repository_readme_handles_404_and_base64(monkeypatch):
    from github.client import get_repository_readme

    class FakeResponse:
        def __init__(self, status_code, text="", json_data=None, headers=None):
            self.status_code = status_code
            self.text = text
            self._json_data = json_data or {}
            self.headers = headers or {}

        def json(self):
            return self._json_data

    responses = [
        FakeResponse(404),
        FakeResponse(
            200,
            json_data={"content": "IyBSRUFETUU="},
            headers={"Content-Type": "application/json"},
        ),
        FakeResponse(200, text="# RAW README", headers={"Content-Type": "text/plain"}),
    ]

    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    monkeypatch.setattr("github.client.requests.get", lambda *args, **kwargs: responses.pop(0))

    assert get_repository_readme("octocat", "missing") == ""
    assert get_repository_readme("octocat", "json") == "# README"
    assert get_repository_readme("octocat", "raw") == "# RAW README"


def test_render_github_template_replaces_default_template_variables():
    from github.entity import GitHubStarredResponseItem
    from github.exporter import build_template_context
    from github.exporter import render_github_template

    template = Path("config/template/github.md").read_text(encoding="utf-8")
    item = GitHubStarredResponseItem(
        full_name="octocat/Hello-World",
        html_url="https://github.com/octocat/Hello-World",
        description="Demo repo",
        owner_login="octocat",
        repo_name="Hello-World",
        language="Python",
        topics=["demo"],
        stargazers_count=1,
        forks_count=2,
        open_issues_count=3,
        fork=False,
        archived=False,
        private=False,
        homepage="",
        license="MIT",
        created_at="2020-01-01T00:00:00Z",
        updated_at="2020-01-02T00:00:00Z",
        pushed_at="2020-01-03T00:00:00Z",
        starred_at="2026-05-23T00:00:00Z",
    )

    rendered = render_github_template(
        template,
        build_template_context(item, "# README", "2026-05-23T12:00:00Z", "~"),
    )

    assert "{{" not in rendered
    assert "octocat/Hello-World" in rendered
    assert "# README" in rendered


def test_github_export_writes_files_and_index(monkeypatch, tmp_path):
    from export_runtime.index_writer import IndexWriter
    from github.entity import GitHubStarredResponseItem
    from github.exporter import export

    item = GitHubStarredResponseItem(
        full_name="octocat/Hello-World",
        html_url="https://github.com/octocat/Hello-World",
        description="Demo repo",
        owner_login="octocat",
        repo_name="Hello-World",
        language="Python",
        topics=["demo"],
        stargazers_count=1,
        forks_count=2,
        open_issues_count=3,
        fork=False,
        archived=False,
        private=False,
        homepage="",
        license="MIT",
        created_at="2020-01-01T00:00:00Z",
        updated_at="2020-01-02T00:00:00Z",
        pushed_at="2020-01-03T00:00:00Z",
        starred_at="2026-05-23T00:00:00Z",
    )

    monkeypatch.setattr("github.exporter.get_starred_repositories", lambda page, per_page=100: [item] if page == 1 else [])
    monkeypatch.setattr("github.exporter.get_repository_readme", lambda owner, repo: "# README\n")

    index_file = tmp_path / "index.md"
    writer = IndexWriter(file_path=str(index_file))
    export(str(tmp_path), "config/template/github.md", writer, prefix="")

    output = tmp_path / "octocat-Hello-World.md"
    assert output.exists()
    assert "# README" in output.read_text(encoding="utf-8")
    assert "[[octocat-Hello-World.md|octocat/Hello-World]]" in index_file.read_text(encoding="utf-8")

    second_dir = tmp_path / "prefixed"
    second_dir.mkdir()
    writer = IndexWriter(file_path=str(second_dir / "index.md"))
    export(str(second_dir), "config/template/github.md", writer, prefix="~")
    assert (second_dir / "~octocat-Hello-World.md").exists()


def test_cli_registers_github_command():
    from export_to_obsidian import eto

    runner = CliRunner()

    root_help_result = runner.invoke(eto, ["--help"])
    help_result = runner.invoke(eto, ["github", "--help"])
    missing_template_result = runner.invoke(eto, ["github", "-o", "output/github"])

    assert root_help_result.exit_code == 0
    assert "--prefix" in root_help_result.output
    assert help_result.exit_code == 0
    assert "--template" in help_result.output
    assert "--prefix" not in help_result.output
    assert missing_template_result.exit_code != 0