#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author : bGZo
@Date : 2026-08-29
@Links : https://github.com/bGZo
"""
import pytest

from app.cookies import CookiesConfigError
from zhihu.cilent import ZhihuClient


def _write_cookies(tmp_path, content):
    p = tmp_path / "cookies.txt"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_zhihu_client_headers_configured(monkeypatch, tmp_path):
    path = _write_cookies(tmp_path, ".zhihu.com\tTRUE\t/\tTRUE\t0\td_c0\tzv\n")
    monkeypatch.setenv("COOKIES", path)
    client = ZhihuClient()
    headers = client.session.headers
    assert headers["Cookie"] == "d_c0=zv"
    assert "User-Agent" in headers
    assert headers["Referer"] == "https://www.zhihu.com"


def test_zhihu_client_missing_cookie_raises(monkeypatch, tmp_path):
    path = _write_cookies(tmp_path, ".weibo.com\tTRUE\t/\tTRUE\t0\tname\tvalue\n")
    monkeypatch.setenv("COOKIES", path)
    with pytest.raises(CookiesConfigError, match="No cookies found"):
        ZhihuClient()
