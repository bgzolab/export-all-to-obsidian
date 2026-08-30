#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author : bGZo
@Date : 2026-08-29
@Links : https://github.com/bGZo
"""
import pytest

from app.cookies import CookiesConfigError
from weibo.cilent import WeiboClient


def _write_cookies(tmp_path, content):
    p = tmp_path / "cookies.txt"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_weibo_client_headers_configured_cn_domain(monkeypatch, tmp_path):
    """weibo.cn 域的 Cookie 也应命中 weibo 的双域名匹配。"""
    path = _write_cookies(tmp_path, ".weibo.cn\tTRUE\t/\tTRUE\t0\tSUB\tv1\n")
    monkeypatch.setenv("COOKIES", path)
    client = WeiboClient()
    headers = client.session.headers
    assert headers["Cookie"] == "SUB=v1"
    assert "User-Agent" in headers
    assert headers["Referer"] == "https://weibo.com/u/page/like/"


def test_weibo_client_dedupes_cross_domain_same_name(monkeypatch, tmp_path):
    """weibo.com 与 weibo.cn 同名 Cookie 应去重，weibo.com 优先。"""
    path = _write_cookies(
        tmp_path,
        (
            ".weibo.com\tTRUE\t/\tTRUE\t0\tSUB\tv1\n"
            ".weibo.cn\tTRUE\t/\tTRUE\t0\tSUB\tv2\n"
        ),
    )
    monkeypatch.setenv("COOKIES", path)
    client = WeiboClient()
    assert client.session.headers["Cookie"] == "SUB=v1"


def test_weibo_client_missing_cookie_raises(monkeypatch, tmp_path):
    path = _write_cookies(tmp_path, ".zhihu.com\tTRUE\t/\tTRUE\t0\tname\tvalue\n")
    monkeypatch.setenv("COOKIES", path)
    with pytest.raises(CookiesConfigError, match="No cookies found"):
        WeiboClient()
