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


def test_flag_numeric_zero_treated_as_false(tmp_path):
    """数字 flag 0 应与 FALSE 等价，host-only Cookie 不泄漏到父域。"""
    content = "api.zhihu.com\t0\t/\tTRUE\t0\thost\tv1\n"
    path = _write(tmp_path, content)
    assert load_cookie_header(path, ("zhihu.com",)) == ""


def test_expired_cookie_skipped_session_cookie_kept(tmp_path):
    """过期条目（非零过去时间戳）应跳过；会话 Cookie（0）保留。"""
    content = (
        ".zhihu.com\tTRUE\t/\tTRUE\t1000\told\tv\n"
        ".zhihu.com\tTRUE\t/\tTRUE\t0\tsess\ts\n"
    )
    path = _write(tmp_path, content)
    header = load_cookie_header(path, ("zhihu.com",))
    assert header == "sess=s"


def test_same_name_across_domains_both_kept(tmp_path):
    """多域同名 Cookie 应共存，不做跨域覆盖。"""
    content = (
        ".x.com\tTRUE\t/\tTRUE\t0\tct0\tAAA\n"
        ".twitter.com\tTRUE\t/\tTRUE\t0\tct0\tBBB\n"
    )
    path = _write(tmp_path, content)
    header = load_cookie_header(path, ("x.com", "twitter.com"))
    assert header == "ct0=AAA; ct0=BBB"


def test_dedupe_by_name_prefers_first_domain(tmp_path):
    """dedupe_by_name 按域名优先级去重：x.com 优先，twitter.com 回退。"""
    content = (
        ".x.com\tTRUE\t/\tTRUE\t0\tct0\tAAA\n"
        ".twitter.com\tTRUE\t/\tTRUE\t0\tct0\tBBB\n"
        ".x.com\tTRUE\t/\tTRUE\t0\tother\t1\n"
    )
    path = _write(tmp_path, content)
    header = load_cookie_header(
        path, ("x.com", "twitter.com"), dedupe_by_name=True
    )
    assert header == "ct0=AAA; other=1"


def test_dedupe_by_name_falls_back_to_second_domain(tmp_path):
    """主域无该 Cookie 时回退到次优先域名的值。"""
    content = (
        ".twitter.com\tTRUE\t/\tTRUE\t0\tct0\tBBB\n"
        ".x.com\tTRUE\t/\tTRUE\t0\tother\t1\n"
    )
    path = _write(tmp_path, content)
    header = load_cookie_header(
        path, ("x.com", "twitter.com"), dedupe_by_name=True
    )
    assert header == "ct0=BBB; other=1"


def test_utf8_bom_stripped(tmp_path):
    """UTF-8 BOM 应被剥除，host-only 首条 Cookie 不被静默丢弃。"""
    content = "zhihu.com\tFALSE\t/\tTRUE\t0\thost\tv1\n"
    path = _write(tmp_path, content)
    with open(path, "wb") as f:
        f.write(b"\xef\xbb\xbf" + content.encode("utf-8"))
    assert load_cookie_header(path, ("zhihu.com",)) == "host=v1"


def test_non_utf8_encoding_raises_config_error(monkeypatch, tmp_path):
    """非 UTF-8 字节应转抛 CookiesConfigError，而非 UnicodeDecodeError 泄漏。"""
    path = tmp_path / "cookies.txt"
    path.write_bytes(b".zhihu.com\tTRUE\t/\tTRUE\t0\tbad\t\xff\xfe\n")
    monkeypatch.setenv("COOKIES", str(path))
    from app.cookies import CookiesConfigError

    with pytest.raises(CookiesConfigError, match="encoding error"):
        get_cookie_header(("zhihu.com",))


def test_value_whitespace_stripped(tmp_path):
    """value 的尾随空白应被清理，不拼入请求头。"""
    content = ".zhihu.com\tTRUE\t/\tTRUE\t0\tct0\tabc \n"
    path = _write(tmp_path, content)
    assert load_cookie_header(path, ("zhihu.com",)) == "ct0=abc"


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


def test_leading_whitespace_on_httponly_line_deduped(tmp_path):
    """带前导空白的 #HttpOnly_ 行前缀检测不应失效，仍能与同名普通 Cookie 去重。"""
    content = (
        "  #HttpOnly_.zhihu.com\tTRUE\t/\tTRUE\t0\tct0\tLEAK\n"
        ".zhihu.com\tTRUE\t/\tTRUE\t0\tct0\tREAL\n"
    )
    path = _write(tmp_path, content)
    header = load_cookie_header(path, ("zhihu.com",))
    assert header == "ct0=REAL"


def test_empty_name_skipped(tmp_path):
    """空 cookie name 不应拼出 "=value" 这类非法请求头。"""
    content = (
        ".zhihu.com\tTRUE\t/\tTRUE\t0\t\tvalue\n"
        ".zhihu.com\tTRUE\t/\tTRUE\t0\tgood\tv\n"
    )
    path = _write(tmp_path, content)
    assert load_cookie_header(path, ("zhihu.com",)) == "good=v"


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


def test_unreadable_file_raises_config_error(monkeypatch, tmp_path):
    """cookies.txt 存在但不可读（如权限 000）时应转抛 CookiesConfigError，
    而非泄漏 PermissionError 原始 traceback。"""
    from app.cookies import CookiesConfigError

    path = _write(tmp_path, ".zhihu.com\tTRUE\t/\tTRUE\t0\ta\t1\n")
    import os
    import stat

    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)  # 确保先可读再锁定
    os.chmod(path, 0)
    monkeypatch.setenv("COOKIES", path)
    with pytest.raises(CookiesConfigError, match="not readable"):
        get_cookie_header(("zhihu.com",))
    os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


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
