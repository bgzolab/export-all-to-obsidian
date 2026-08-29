#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author : bGZo
@Date : 2026-08-29
@Links : https://github.com/bGZo
"""
import pytest

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


def test_weibo_client_missing_cookie_raises(monkeypatch, tmp_path):
    path = _write_cookies(tmp_path, ".zhihu.com\tTRUE\t/\tTRUE\t0\tname\tvalue\n")
    monkeypatch.setenv("COOKIES", path)
    with pytest.raises(ValueError, match="No cookies found"):
        WeiboClient()
