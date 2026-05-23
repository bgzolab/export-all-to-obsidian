# Import GitHub URLs and export to Markdown files for Obsidian

This is a temporary test script to import GitHub URLs and export them as Markdown files for use in Obsidian. 

The script reads a list of GitHub URLs from a text file(default with import.url), fetches the content of each URL, and saves it as a Markdown file in a specified output directory.

Additionally, it generates an index Markdown file that lists all the imported URLs with links to their corresponding Markdown files.

## Get Started

```shell
python3 ./tests/import-from-github-url/import_github_urls.py --prefix "_" --index-file ./tests/import-from-github-url/index.md
```

## Usage

```shell
usage: import_github_urls.py [-h] [--urls-file URLS_FILE] [--template-path TEMPLATE_PATH] [--output-dir OUTPUT_DIR]
                             [--index-file INDEX_FILE] [--report-file REPORT_FILE] [--prefix PREFIX] [--force]
                             [--limit LIMIT] [--timeout TIMEOUT]

Read GitHub repository URLs from a file and export them as Markdown with the same template used by the github
command.

options:
  -h, --help            show this help message and exit
  --urls-file URLS_FILE
                        Path to the input URL list.
  --template-path TEMPLATE_PATH
                        Markdown template used for each repository.
  --output-dir OUTPUT_DIR
                        Directory for exported Markdown files.
  --index-file INDEX_FILE
                        Path to the generated index Markdown file.
  --report-file REPORT_FILE
                        Path to the JSON import report.
  --prefix PREFIX       Output filename prefix, aligned with eto --prefix.
  --force               Overwrite existing output files.
  --limit LIMIT         Only process the first N distinct repository URLs.
  --timeout TIMEOUT     Per-request timeout in seconds.
```
