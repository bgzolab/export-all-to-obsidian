#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author : bGZo
@Date : 2026-08-29
@Links : https://github.com/bGZo
"""
import click
import pytest

from app.cookies import get_cookie_header
from app.cookies import load_cookie_header
from app.cookies import resolve_cookies_file


def _write(tmp_path, content):
    p = tmp_path / "cookies.txt"
    p.write_text(content, encoding="utf-8")
    return str(p)


def _root_ctx(cookies_file):
    """构造带 cookies_file 的 click 根上下文，模拟顶层 --cookies-file 注入。"""
    ctx = click.Context(click.Command("eto"))
    ctx.obj = {"cookies_file": cookies_file}
    return ctx


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


def test_flag_false_host_only_exact_match(tmp_path):
    """flag=FALSE 的 host-only Cookie 不做后缀匹配，不发送到子域。"""
    content = (
        "api.zhihu.com\tFALSE\t/\tTRUE\t0\thost\tv1\n"
        ".zhihu.com\tTRUE\t/\tTRUE\t0\tdot\tv2\n"
    )
    path = _write(tmp_path, content)
    assert load_cookie_header(path, ("zhihu.com",)) == "dot=v2"
    assert load_cookie_header(path, ("api.zhihu.com",)) == "host=v1"


def test_duplicate_names_keep_last_value(tmp_path):
    """同名 Cookie 去重，保留文件中最后一条的值，位置保持首次出现顺序。"""
    content = (
        ".zhihu.com\tTRUE\t/\tTRUE\t0\ta\t1\n"
        ".zhihu.com\tTRUE\t/\tTRUE\t0\tb\t2\n"
        ".zhihu.com\tTRUE\t/\tTRUE\t0\ta\t9\n"
    )
    path = _write(tmp_path, content)
    header = load_cookie_header(path, ("zhihu.com",))
    assert header == "a=9; b=2"


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


def test_leading_whitespace_tolerated(tmp_path):
    """行首空白不应导致该行被静默丢弃。"""
    content = "  .zhihu.com\tTRUE\t/\tTRUE\t0\tlead\tv\n"
    path = _write(tmp_path, content)
    header = load_cookie_header(path, ("zhihu.com",))
    assert header == "lead=v"


def test_crlf_line_endings_supported(tmp_path):
    content = ".zhihu.com\tTRUE\t/\tTRUE\t0\tcrlf\tv\r\n"
    path = _write(tmp_path, content)
    header = load_cookie_header(path, ("zhihu.com",))
    assert header == "crlf=v"


def test_missing_env_and_ctx_raises(monkeypatch):
    monkeypatch.delenv("COOKIES", raising=False)
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


def test_ctx_cookies_file_overrides_env(monkeypatch, tmp_path):
    env_path = _write(tmp_path, ".weibo.com\tTRUE\t/\tTRUE\t0\twb\tv\n")
    explicit = tmp_path / "explicit.txt"
    explicit.write_text(".zhihu.com\tTRUE\t/\tTRUE\t0\tzh\tv\n", encoding="utf-8")
    monkeypatch.setenv("COOKIES", env_path)
    with _root_ctx(str(explicit)):
        assert get_cookie_header(("zhihu.com",)) == "zh=v"


def test_get_cookie_header_explicit_param_highest_priority(tmp_path):
    p1 = _write(tmp_path, ".zhihu.com\tTRUE\t/\tTRUE\t0\ta\t1\n")
    p2 = tmp_path / "b.txt"
    p2.write_text(".zhihu.com\tTRUE\t/\tTRUE\t0\tb\t2\n", encoding="utf-8")
    with _root_ctx(p1):
        assert get_cookie_header(("zhihu.com",), str(p2)) == "b=2"
