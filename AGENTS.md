# AGENTS.md

Instructions for OpenCode. This file is the source of truth for internals; `README.md` is the
user-facing usage doc. Both are kept in sync manually — do not add other long-term docs.

## Project overview

`export_to_obsidian` is a Python CLI tool that exports saved content from multiple platforms
into Obsidian-friendly Markdown files. The CLI entry point is `eto`.

- Thin entry: `src/export_to_obsidian.py` -> `src/app/cli.py`
- Platform modules (all registered in the CLI): `bangumi`, `bilibili`, `cnblog`,
  `github`, `qireader`, `twitter`, `v2ex`, `weibo`, `zhihu`, each orchestrated in `src/<platform>/exporter.py`
- Shared runtime: `src/export_runtime/` (index_writer, exporter_support)
- Common utilities: `src/utils/`, `src/entity/`

## Runtime flow

1. `eto` -> `src/app/cli.py` parses top-level options and the subcommand.
2. `app.context` builds the root context and injects IndexWriter into the chosen exporter.
3. `app.cookies` extracts per-domain Cookie headers from the Netscape `cookies.txt`.
4. Each exporter converts entries to front matter + Markdown via `utils.template` /
   `utils.md_utils`.
5. `export_runtime.exporter_support` handles output paths, incremental pruning, file writes
   and index appends; `index_writer` prints the index or appends it to the index file.

## Constraints

- Only lightweight exporter helpers exist; there is no `BaseExporter`-style abstraction.
- `bangumi.bangumi` is a historical compatibility import layer.

## Tech stack

- Python >= 3.12, click (CLI), requests (HTTP)
- beautifulsoup4 / html2text / markdownify (HTML to Markdown), python-frontmatter
- Poetry packaging (pyproject.toml, poetry-core backend), `[tool.poetry.scripts] eto`
- Ruff for lint + format (`ruff 0.17.4`), enforced by the PR workflow

## Development commands

```shell
pip install -e .                 # dev install
source ./export-env.sh           # load env vars from .env (export + source .env)
PYTHONPATH=src pytest tests -q                 # run all tests
PYTHONPATH=src pytest tests/test_utils.py -q   # run a single test file
ruff check src tests                           # lint
ruff format --check src tests                  # verify formatting
ruff format src tests                          # apply formatting
```

- You must explicitly set `PYTHONPATH=src` to run pytest.
- After changes, only run the smallest affected test slice.

## Code conventions

- **No emoji**; large code blocks (> a few hundred lines) need doc comments in
  **Simplified Chinese**.
- Modular: keep single files < 1000 lines, avoid monoliths.
- Every change must include unit tests; aim for high coverage.
- Prefer minimal changes; no unrelated refactoring. Source in `src/`, tests in `tests/`.
- Adding a platform still requires manually registering a click subcommand in
  `src/app/cli.py` and explicitly injecting IndexWriter into the exporter
  (see `get_index_writer` in `src/app/context.py`).

## CLI contract (gotchas)

- `--index-file`、`--prefix` and `--cookies-file` are **top-level options and must come
  before the subcommand**; when `--index-file` is omitted, the index is printed to the
  terminal. `--cookies-file` points to a Netscape-format `cookies.txt`; when omitted, the
  environment variable `COOKIES` (the file path) is used.
- Subcommands: `cnblog(-o)`, `bangumi(-t -s -o [-c] [--force])`, `qireader(-t -o)`,
  `v2ex(-o)`, `twitter(-o [--force] [--max-pages])`, `zhihu(-c -o)`, `weibo(-u -o [--force])`,
  `bilibili(-f -o [--force])`, `github(-t -o [--force])`.
- `--force` currently only affects bangumi, weibo, bilibili, and twitter.

## Environment variables (required by module exports)

`CNBLOG_ACCESS_TOKEN`, `BGM_ACCESS_TOKEN`, `V2EX_ACCESS_TOKEN`,
`TWITTER_CSRF_TOKEN`, `TWITTER_USER_ID`. `TWITTER_CSRF_TOKEN` / `TWITTER_USER_ID`
fall back to deriving from the cookies.txt Cookie (`ct0` / `twid`). `COOKIES` holds the
path to a Netscape-format `cookies.txt` shared by qireader, v2ex, zhihu, weibo,
bilibili and twitter. `GITHUB_TOKEN` is used by the github module. Optional
notifications: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## Incremental / output behavior

- Most modules treat "target file already exists" as the local pruning signal and end the
  current sync run immediately — not a remote cursor.
- Each entry is one Markdown file with YAML front matter; the top-level `--prefix` controls
  the filename prefix (default `~`).
- Index file is grouped by module: module is `##`, each export run is `###`.
- Special cases: bangumi and github render from template files, bilibili emits iframe embeds,
  github injects the repo README.

## Workflow: planning & execution

- Before planning a new feature, read this file (and `README.md` for the user-facing contract).
- Write plans into `docs/implementation-plans/`; tasks must be atomic (with file paths and
  verification steps), status one of `Completed / In progress / Planned / Deprecated / On Hold`.
- Execute plans TASK by TASK, only advancing after verification passes; update the plan's
  execution records when done; update this file if architecture/tech-stack changes.

## Test status

Each platform has `tests/test_<platform>.py`; shared pieces are covered by
`test_cookies.py`, `test_credential_guard.py` and `test_utils.py`.

## Non-goals

- No database, no message queue / async task system, no web service, no plugin framework.
