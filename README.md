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

## Usage

Full command reference lives in [docs/usages](./docs/usages/README.md). It covers:

- global options (`--index-file`, `--prefix`, `--cookies-file`, `--db`)
- required environment variables and cookie domains
- one page per subcommand with parameters, output layout and examples
- shared behavior for credential checks, incremental exports, index files and the raw database

A typical call looks like:

```shell
eto --index-file output/index/export-index.md zhihu -c your-collection-id -o output/zhihu
```

Run `eto --help` or `eto <command> --help` for the built-in help.

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

Internals and repo conventions live in `AGENTS.md`.

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
