# Export your data into Obsidian

> Your data is your asset, you own it forever. 

This tool exports your social media data to Obsidian with markdown files.

- Export data from many sites into local Markdown files.
- Keep one simple CLI for all modules.
- Provide an optional index file in Markdown.

Now this tool had supported following modules:

1. bangumi
2. bilibili
3. cnblog
4. github
5. qireader
6. v2ex
7. twitter
8. weibo
9. zhihu

## Quick start

You can install from PyPI:

```shell
pipx install export_to_obsidian
```

Or install from this repo:

```shell
pipx install -e .
```

Put your token or cookie values in .env, then load them. Cookies come from a single Netscape-format `cookies.txt` file; point the `COOKIES` env var at its path (or pass `--cookies-file` to the CLI).

```shell
chmod +x ./export-env.sh
source ./export-env.sh
```

Main env vars used by the current modules:

- CNBLOG_ACCESS_TOKEN
- BGM_ACCESS_TOKEN
- V2EX_ACCESS_TOKEN
- TWITTER_CSRF_TOKEN (optional, derived from the `ct0` cookie)
- TWITTER_USER_ID (optional, derived from the `twid` cookie)
- COOKIES (path to a Netscape-format cookies.txt used by qireader, v2ex, zhihu, weibo, bilibili and twitter)

Optional reminder env vars:

- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

## Basic usage

```shell
eto <command> [options]
eto --prefix <prefix> <command> [options]
eto --index-file <path> <command> [options]
eto --cookies-file <path> <command> [options]
```

`--index-file`, `--prefix` and `--cookies-file` are top-level options. Put them before the subcommand.

`--cookies-file` points to a Netscape-format `cookies.txt` shared by qireader, v2ex, zhihu, weibo, bilibili and twitter. When omitted, the `COOKIES` environment variable is used.

If you do not use `--index-file`, the index is printed to the terminal.

If you use `--index-file`, the index is written to one Markdown file.

Each module is stored under one second-level heading, and repeated exports for the same module are appended in order under that same heading.

## Command examples

### cnblog

```shell
eto cnblog -o output/cnblog
```

### bangumi

Use `config/bangumi_template.md` as the template file.

```shell
eto bangumi -t config/bangumi_template.md -s 1 -o output/bangumi
eto bangumi -t config/bangumi_template.md -s 2 -o output/bangumi
eto bangumi -t config/bangumi_template.md -s 3 -o output/bangumi
eto bangumi -t config/bangumi_template.md -s 4 -o output/bangumi
```

You can also set one collection type:

```shell
eto bangumi -t config/bangumi_template.md -s 2 -c 3 -o output/bangumi
```

`-c` means the status of the subject:

- 1: 想看
- 2: 看过
- 3: 在看
- 4: 搁置
- 5: 抛弃

### qireader

```shell
eto qireader -t your-tag -o output/qireader
```

### github

Use `config/template/github.md` as the default template file.

```shell
eto github -t config/template/github.md -o output/github
eto --prefix "" github -t config/template/github.md -o output/github
```

### v2ex

```shell
eto v2ex -o output/v2ex
```

### zhihu

```shell
eto zhihu -c your-collection-id -o output/zhihu
```

### weibo

```shell
eto weibo -u your-user-id -o output/weibo
```

### bilibili

```shell
eto bilibili -f your-fav-id -o output/bilibili
```

### twitter

Exports your Twitter likes.

```shell
eto twitter -o output/twitter
```

By default it exports up to the built-in max pages (roughly 100 liked tweets). Use `--max-pages` to adjust:

```shell
eto twitter --max-pages 5 -o output/twitter
```

Use `--force` to overwrite existing local files:

```shell
eto twitter --force -o output/twitter
```

`TWITTER_CSRF_TOKEN` and `TWITTER_USER_ID` are optional; if not set, they are derived from your cookies.txt Cookie (`ct0` / `twid`).

## Credential health check

Before each module export, the CLI runs a lightweight credential probe.

- If the cookie or token is confirmed expired, the export is skipped.
- If `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are both configured, the tool sends a Telegram bot reminder with the affected module name.
- If the probe cannot confirm whether the credential is invalid because of a transient network or service problem, the export still continues.

## Index file

Example:

```shell
eto --index-file output/index/export-index.md zhihu -c your-collection-id -o output/zhihu
eto --index-file output/index/export-index.md bilibili -f your-fav-id -o output/bilibili
eto --index-file output/index/export-index.md github -t config/template/github.md -o output/github
```

The file is grouped by module name.
One module keeps one `##` section.
Each export run adds one `###` block under that module.

Example output:

```markdown
## zhihu

- [[~zhihu-entry-1|First saved item]]
- [[~zhihu-entry-2|Second saved item]]

## bilibili

- [[~BV1xxxxxx|One saved video]]
```

## Output

Files are written as Markdown files in your output folder.
The project also writes front matter, so the files work well in Obsidian.


## Testing

Run all tests:

```shell
PYTHONPATH=src pytest tests -q
```

Run one test file:

```shell
PYTHONPATH=src pytest tests/test_utils.py -q
```

In VS Code, you can also use the debug and test settings in .vscode/launch.json.

## Contributing


Any contributions made are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".
Don't forget to give the project a star! Thanks again!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'feat(module):add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

Top contributors:

<a href="https://github.com/bGZo/playground/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=bGZo/playground" alt="contrib.rocks image" />
</a>

## License

All code is licensed under the AGPL-3.0 license. See `LICENSE` for more information.
