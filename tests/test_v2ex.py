#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author : bGZo
@Date : 2025-08-07
@Links : https://github.com/bGZo
"""
from urllib3.util.retry import Retry

from v2ex.cilent import V2exClient


def _make_client(monkeypatch):
    monkeypatch.setenv("V2EX_ACCESS_TOKEN", "fake-token")
    monkeypatch.setenv("V2EX_COOKIE", "fake-cookie")
    return V2exClient()


def test_v2ex_client_session_has_retry_adapter(monkeypatch):
    """V2exClient 的 session 应挂载带重试配置的 HTTPAdapter。"""
    client = _make_client(monkeypatch)
    adapter = client.session.get_adapter("https://www.v2ex.com/")
    retry = adapter.max_retries
    assert isinstance(retry, Retry)
    assert retry.total == 5
    assert retry.connect == 5
    assert retry.read == 5
    assert retry.other == 5
    assert retry.backoff_factor == 1


def test_v2ex_client_retry_covers_ssl_errors(monkeypatch):
    """SSL 错误走 other 分支，other 必须大于 0 才会重试。"""
    client = _make_client(monkeypatch)
    adapter = client.session.get_adapter("https://www.v2ex.com/")
    retry = adapter.max_retries
    # other 默认为 None（不重试），显式设置后应能重试 SSL 错误
    assert retry.other == 5


def test_v2ex_client_headers_configured(monkeypatch):
    """session 应携带 Authorization、Cookie、User-Agent 头。"""
    client = _make_client(monkeypatch)
    headers = client.session.headers
    assert headers["Authorization"] == "Bearer fake-token"
    assert headers["Cookie"] == "fake-cookie"
    assert "User-Agent" in headers
    assert headers["Referer"] == "https://www.v2ex.com"


def test_v2ex_client_missing_token_raises(monkeypatch):
    """缺少 V2EX_ACCESS_TOKEN 应抛出 ValueError。"""
    monkeypatch.delenv("V2EX_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv("V2EX_COOKIE", "fake-cookie")
    try:
        V2exClient()
        assert False, "应抛出 ValueError"
    except ValueError as exc:
        assert "V2EX_ACCESS_TOKEN" in str(exc)


def test_v2ex_client_missing_cookie_raises(monkeypatch):
    """缺少 V2EX_COOKIE 应抛出 ValueError。"""
    monkeypatch.setenv("V2EX_ACCESS_TOKEN", "fake-token")
    monkeypatch.delenv("V2EX_COOKIE", raising=False)
    try:
        V2exClient()
        assert False, "应抛出 ValueError"
    except ValueError as exc:
        assert "V2EX_COOKIE" in str(exc)