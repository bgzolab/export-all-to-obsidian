#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author : bGZo
@Date : 2026-08-29
@Links : https://github.com/bGZo
"""
import pytest

from app.cookies import get_cookie_header
from app.cookies import load_cookie_header
from app.cookies import resolve_cookies_file
from app.cookies import set_explicit_cookies_file


@pytest.fixture(autouse=True)
def _reset_explicit_path():
    yield
    set_explicit_cookies_file(None)


def _write(tmp_path, content):
    p = tmp_path / "cookies.txt"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_parses_in_file_order(tmp_path):
    content = (
        ".zhihu.com\tTRUE\t/\tTRUE\t0\ta\t1\n"
        ".zhihu.com\tTRUE\t/\tTRUE\t0\tb\t2\n"
        ".zhihu.com\tTRUE\t/\tTRUE\t0\tc\t3\n"
    )
    path = _write(tmp_path, content)
    header = load_cookie_header(path, ("zhihu.com",))
    assert header == "a=1; b=2; c=3"


def test_domain_suffix_matching(tmp_path):
    content = (
        ".zhihu.com\tTRUE\t/\tTRUE\t0\tdot\tv1\n"
        "www.zhihu.com\tTRUE\t/\tTRUE\t0\tsub\tv2\n"
    )
    path = _write(tmp_path, content)
    header = load_cookie_header(path, ("zhihu.com",))
    assert header == "dot=v1; sub=v2"


def test_filters_other_domains(tmp_path):
    content = (
        ".weibo.com\tTRUE\t/\tTRUE\t0\twb\tv\n"
        ".zhihu.com\tTRUE\t/\tTRUE\t0\tzh\tv\n"
    )
    path = _write(tmp_path, content)
    header = load_cookie_header(path, ("zhihu.com",))
    assert header == "zh=v"


def test_httponly_prefix_parsed_and_comments_skipped(tmp_path):
    content = (
        "# comment line\n"
        "\n"
        "#HttpOnly_.zhihu.com\tTRUE\t/\tTRUE\t0\tht\tonly\n"
        "#HttpOnly_.zhihu.com\tTRUE\t/\tTRUE\t0\tnormal\tplain\n"
    )
    path = _write(tmp_path, content)
    header = load_cookie_header(path, ("zhihu.com",))
    assert header == "ht=only; normal=plain"


def test_short_lines_skipped(tmp_path):
    content = (
        ".zhihu.com\tTRUE\t/\tTRUE\t0\tgood\tv\n"
        ".zhihu.com\tTRUE\t/\tTRUE\t0\n"
        "not-a-cookie-line\n"
    )
    path = _write(tmp_path, content)
    header = load_cookie_header(path, ("zhihu.com",))
    assert header == "good=v"


def test_missing_env_and_explicit_raises(monkeypatch):
    monkeypatch.delenv("COOKIES", raising=False)
    set_explicit_cookies_file(None)
    with pytest.raises(ValueError, match="COOKIES environment variable"):
        resolve_cookies_file()


def test_missing_file_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("COOKIES", str(tmp_path / "no-such-file.txt"))
    with pytest.raises(ValueError, match="Cookies file not found"):
        get_cookie_header(("zhihu.com",))


def test_no_matching_domain_raises(monkeypatch, tmp_path):
    path = _write(tmp_path, ".weibo.com\tTRUE\t/\tTRUE\t0\twb\tv\n")
    monkeypatch.setenv("COOKIES", path)
    with pytest.raises(ValueError, match="No cookies found"):
        get_cookie_header(("zhihu.com",))


def test_explicit_path_overrides_env(monkeypatch, tmp_path):
    env_path = _write(tmp_path, ".weibo.com\tTRUE\t/\tTRUE\t0\twb\tv\n")
    explicit = tmp_path / "explicit.txt"
    explicit.write_text(".zhihu.com\tTRUE\t/\tTRUE\t0\tzh\tv\n", encoding="utf-8")
    monkeypatch.setenv("COOKIES", env_path)
    set_explicit_cookies_file(str(explicit))
    assert get_cookie_header(("zhihu.com",)) == "zh=v"
