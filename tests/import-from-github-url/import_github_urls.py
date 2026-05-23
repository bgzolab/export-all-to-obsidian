#!/usr/bin/env python3
"""Best-effort GitHub repository importer for a URL list."""

from __future__ import annotations

import argparse
import base64
import json
import os
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from export_runtime.exporter_support import add_index_entry
from export_runtime.exporter_support import build_link_target
from export_runtime.exporter_support import write_raw_markdown_output
from export_runtime.index_writer import IndexWriter
from github.entity import GitHubStarredResponseItem
from github.exporter import build_template_context
from github.exporter import render_github_template
from utils.file_utils import get_clean_filename


GITHUB_API_BASE_URL = "https://api.github.com"
DEFAULT_TIMEOUT = 30
RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)


@dataclass
class ImportSuccess:
    original_url: str
    requested_full_name: str
    exported_full_name: str
    output_file: str
    redirected_from: str | None = None


@dataclass
class ImportFailure:
    original_url: str
    requested_full_name: str | None
    reason: str
    redirected_to: str | None = None


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent.parent

    parser = argparse.ArgumentParser(
        description=(
            "Read GitHub repository URLs from a file and export them as Markdown "
            "with the same template used by the github command."
        ),
    )
    parser.add_argument(
        "--urls-file",
        type=Path,
        default=script_dir / "import.url",
        help="Path to the input URL list.",
    )
    parser.add_argument(
        "--template-path",
        type=Path,
        default=repo_root / "config" / "template" / "github.md",
        help="Markdown template used for each repository.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "output" / "github-import-from-urls",
        help="Directory for exported Markdown files.",
    )
    parser.add_argument(
        "--index-file",
        type=Path,
        default=script_dir / "import-index.md",
        help="Path to the generated index Markdown file.",
    )
    parser.add_argument(
        "--report-file",
        type=Path,
        default=script_dir / "import-report.json",
        help="Path to the JSON import report.",
    )
    parser.add_argument(
        "--prefix",
        default="",
        help="Output filename prefix, aligned with eto --prefix.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N distinct repository URLs.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help="Per-request timeout in seconds.",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")


def build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=RETRYABLE_STATUS_CODES,
        allowed_methods=frozenset({"GET"}),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "export-to-obsidian-import-script",
        },
    )

    token = os.environ.get("GITHUB_TOKEN")
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
    else:
        print("Warning: GITHUB_TOKEN not set, continuing with anonymous GitHub API access")

    return session


def load_url_lines(urls_file: Path) -> list[str]:
    lines = []
    for raw_line in urls_file.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def normalize_repo_reference(raw_value: str) -> tuple[str | None, str | None]:
    candidate = raw_value.strip()
    if not candidate:
        return None, "empty"

    if "://" not in candidate and candidate.count("/") >= 1:
        parts = [segment for segment in candidate.split("/") if segment]
        if len(parts) >= 2:
            owner = parts[0]
            repo = parts[1].removesuffix(".git")
            if owner and repo:
                return f"{owner}/{repo}", None

    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    if host not in {"github.com", "www.github.com"}:
        return None, f"unsupported-host:{host or 'missing'}"

    segments = [segment for segment in parsed.path.split("/") if segment]
    if len(segments) < 2:
        return None, "not-a-repository-url"

    owner = segments[0]
    repo = segments[1].removesuffix(".git")
    if not owner or not repo:
        return None, "invalid-repository-path"

    return f"{owner}/{repo}", None


def get_with_timeout(session: requests.Session, url: str, timeout: int) -> requests.Response:
    return session.get(url, timeout=timeout, allow_redirects=True)


def fetch_repository(
    session: requests.Session,
    full_name: str,
    timeout: int,
) -> tuple[dict[str, Any] | None, str | None]:
    owner, repo = full_name.split("/", 1)
    response = get_with_timeout(
        session,
        f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}",
        timeout,
    )
    if response.status_code == 200:
        return response.json(), None
    if response.status_code == 404:
        return None, "repository-not-found"
    if response.status_code == 403:
        return None, f"forbidden:{extract_github_message(response)}"
    return None, f"api-status-{response.status_code}:{extract_github_message(response)}"


def extract_github_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:200]
    message = payload.get("message")
    if not message:
        return "unknown"
    return str(message)


def resolve_redirected_repository(
    session: requests.Session,
    original_url: str,
    timeout: int,
) -> tuple[str | None, str | None]:
    response = get_with_timeout(session, original_url, timeout)
    if response.status_code >= 400:
        return None, f"html-status-{response.status_code}"

    final_full_name, reason = normalize_repo_reference(response.url)
    if not final_full_name:
        return None, reason
    return final_full_name, None


def fetch_repository_readme(
    session: requests.Session,
    owner: str,
    repo: str,
    timeout: int,
) -> str:
    response = get_with_timeout(
        session,
        f"{GITHUB_API_BASE_URL}/repos/{owner}/{repo}/readme",
        timeout,
    )
    if response.status_code == 404:
        return ""
    if response.status_code != 200:
        print(
            f"README skipped for {owner}/{repo}: "
            f"status={response.status_code} message={extract_github_message(response)}",
        )
        return ""

    content_type = response.headers.get("Content-Type", "")
    if "application/json" in content_type:
        payload = response.json()
        encoded = payload.get("content") or ""
        if not encoded:
            return ""
        normalized = encoded.replace("\n", "")
        return base64.b64decode(normalized).decode("utf-8", errors="ignore")

    return response.text


def build_item(repository: dict[str, Any], export_time: str) -> GitHubStarredResponseItem:
    repo_payload = dict(repository)
    repo_payload["starred_at"] = export_time
    return GitHubStarredResponseItem.from_api(repo_payload)


def export_repository(
    *,
    item: GitHubStarredResponseItem,
    readme: str,
    export_time: str,
    template_content: str,
    output_dir: Path,
    index_writer: IndexWriter,
    prefix: str,
) -> str:
    repo_slug = get_clean_filename(f"{item.owner_login}-{item.repo_name}")
    context = build_template_context(item, readme, export_time, prefix)
    content = render_github_template(template_content, context)
    write_raw_markdown_output(str(output_dir), repo_slug, content, prefix)
    add_index_entry(
        index_writer,
        link_target=build_link_target(repo_slug, prefix=prefix, include_extension=True),
        title=item.full_name,
    )
    return f"{prefix}{repo_slug}.md"


def write_report(
    report_file: Path,
    *,
    urls_file: Path,
    output_dir: Path,
    index_file: Path,
    successes: list[ImportSuccess],
    failures: list[ImportFailure],
) -> None:
    report = {
        "generated_at": now_iso(),
        "source_file": str(urls_file),
        "output_dir": str(output_dir),
        "index_file": str(index_file),
        "stats": {
            "success": len(successes),
            "failure": len(failures),
        },
        "successes": [asdict(item) for item in successes],
        "failures": [asdict(item) for item in failures],
    }
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    if not args.urls_file.exists():
        raise FileNotFoundError(f"URL list not found: {args.urls_file}")
    if not args.template_path.exists():
        raise FileNotFoundError(f"Template not found: {args.template_path}")

    session = build_session()
    template_content = args.template_path.read_text(encoding="utf-8")
    requested_urls = load_url_lines(args.urls_file)

    unique_urls: list[str] = []
    seen_full_names: set[str] = set()
    failures: list[ImportFailure] = []
    for raw_url in requested_urls:
        full_name, reason = normalize_repo_reference(raw_url)
        if not full_name:
            failures.append(
                ImportFailure(
                    original_url=raw_url,
                    requested_full_name=None,
                    reason=reason or "invalid-url",
                ),
            )
            continue
        if full_name in seen_full_names:
            continue
        seen_full_names.add(full_name)
        unique_urls.append(raw_url)

    if args.limit is not None:
        unique_urls = unique_urls[: args.limit]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    index_writer = IndexWriter(file_path=str(args.index_file))

    successes: list[ImportSuccess] = []
    export_time = now_iso()

    for original_url in unique_urls:
        requested_full_name, _ = normalize_repo_reference(original_url)
        if not requested_full_name:
            continue

        print(f"Processing: {original_url}")
        repository, reason = fetch_repository(session, requested_full_name, args.timeout)
        redirected_to = None

        if repository is None and reason == "repository-not-found":
            redirected_to, redirect_reason = resolve_redirected_repository(
                session,
                original_url,
                args.timeout,
            )
            if redirected_to and redirected_to != requested_full_name:
                repository, reason = fetch_repository(session, redirected_to, args.timeout)
            elif redirected_to == requested_full_name:
                redirected_to = None
                reason = reason or redirect_reason
            else:
                reason = redirect_reason or reason

        if repository is None:
            failures.append(
                ImportFailure(
                    original_url=original_url,
                    requested_full_name=requested_full_name,
                    reason=reason or "unknown-error",
                    redirected_to=redirected_to,
                ),
            )
            print(f"Skipped: {original_url} ({reason})")
            continue

        item = build_item(repository, export_time)
        repo_slug = get_clean_filename(f"{item.owner_login}-{item.repo_name}")
        target_path = args.output_dir / f"{args.prefix}{repo_slug}.md"
        if target_path.exists() and not args.force:
            failures.append(
                ImportFailure(
                    original_url=original_url,
                    requested_full_name=requested_full_name,
                    reason="output-already-exists",
                    redirected_to=item.full_name if item.full_name != requested_full_name else None,
                ),
            )
            print(f"Skipped existing: {target_path}")
            continue

        readme = fetch_repository_readme(
            session,
            item.owner_login,
            item.repo_name,
            args.timeout,
        )
        output_file = export_repository(
            item=item,
            readme=readme,
            export_time=export_time,
            template_content=template_content,
            output_dir=args.output_dir,
            index_writer=index_writer,
            prefix=args.prefix,
        )
        successes.append(
            ImportSuccess(
                original_url=original_url,
                requested_full_name=requested_full_name,
                exported_full_name=item.full_name,
                output_file=output_file,
                redirected_from=requested_full_name if item.full_name != requested_full_name else None,
            ),
        )
        print(f"Imported: {item.full_name}")

    if successes:
        index_writer.flush("github")

    write_report(
        args.report_file,
        urls_file=args.urls_file,
        output_dir=args.output_dir,
        index_file=args.index_file,
        successes=successes,
        failures=failures,
    )

    print(
        "Finished: "
        f"success={len(successes)} failure={len(failures)} "
        f"report={args.report_file}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())