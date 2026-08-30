#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author : bGZo
@Date : 2025-08-07
@Links : https://github.com/bGZo
"""
from urllib3.util.retry import Retry

import pytest

from app.cookies import CookiesConfigError
from v2ex.cilent import V2exClient


def _write_cookies_file(tmp_path, line):
    p = tmp_path / "cookies.txt"
    p.write_text(line, encoding="utf-8")
    return str(p)


def _make_client(monkeypatch, tmp_path):
    monkeypatch.setenv("V2EX_ACCESS_TOKEN", "fake-token")
    p = _write_cookies_file(
        tmp_path, ".v2ex.com\tTRUE\t/\tTRUE\t0\tfake-cookie-name\tfake-cookie\n"
    )
    monkeypatch.setenv("COOKIES", p)
    return V2exClient()


def test_v2ex_client_session_has_retry_adapter(monkeypatch, tmp_path):
    """V2exClient 的 session 应挂载带重试配置的 HTTPAdapter。"""
    client = _make_client(monkeypatch, tmp_path)
    adapter = client.session.get_adapter("https://www.v2ex.com/")
    retry = adapter.max_retries
    assert isinstance(retry, Retry)
    assert retry.total == 5
    assert retry.connect == 5
    assert retry.read == 5
    assert retry.other == 5
    assert retry.backoff_factor == 1


def test_v2ex_client_retry_covers_ssl_errors(monkeypatch, tmp_path):
    """SSL 错误走 other 分支，other 必须大于 0 才会重试。"""
    client = _make_client(monkeypatch, tmp_path)
    adapter = client.session.get_adapter("https://www.v2ex.com/")
    retry = adapter.max_retries
    # other 默认为 None（不重试），显式设置后应能重试 SSL 错误
    assert retry.other == 5


def test_v2ex_client_headers_configured(monkeypatch, tmp_path):
    """session 应携带 Authorization、Cookie、User-Agent 头。"""
    client = _make_client(monkeypatch, tmp_path)
    headers = client.session.headers
    assert headers["Authorization"] == "Bearer fake-token"
    assert headers["Cookie"] == "fake-cookie-name=fake-cookie"
    assert "User-Agent" in headers
    assert headers["Referer"] == "https://www.v2ex.com"


def test_v2ex_client_missing_token_raises(monkeypatch, tmp_path):
    """缺少 V2EX_ACCESS_TOKEN 应抛出 ValueError。"""
    monkeypatch.delenv("V2EX_ACCESS_TOKEN", raising=False)
    p = _write_cookies_file(
        tmp_path, ".v2ex.com\tTRUE\t/\tTRUE\t0\tfake-cookie-name\tfake-cookie\n"
    )
    monkeypatch.setenv("COOKIES", p)
    with pytest.raises(ValueError, match="V2EX_ACCESS_TOKEN"):
        V2exClient()


def test_v2ex_client_missing_cookie_raises(monkeypatch, tmp_path):
    """缺少 Cookie（无 v2ex.com 域 cookies.txt）应抛出 CookiesConfigError。"""
    monkeypatch.setenv("V2EX_ACCESS_TOKEN", "fake-token")
    p = _write_cookies_file(
        tmp_path, ".zhihu.com\tTRUE\t/\tTRUE\t0\tname\tvalue\n"
    )
    monkeypatch.setenv("COOKIES", p)
    with pytest.raises(CookiesConfigError, match="No cookies found"):
        V2exClient()
