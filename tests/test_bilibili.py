#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author : bGZo
@Date : 2026-08-29
@Links : https://github.com/bGZo
"""
import pytest

from bilibili.cilent import BilibiliClient


def _write_cookies(tmp_path, content):
    p = tmp_path / "cookies.txt"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_bilibili_client_headers_configured(monkeypatch, tmp_path):
    path = _write_cookies(
        tmp_path, ".bilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\tabc\n"
    )
    monkeypatch.setenv("COOKIES", path)
    client = BilibiliClient()
    headers = client.session.headers
    assert headers["Cookie"] == "SESSDATA=abc"
    assert "User-Agent" in headers
    assert headers["Referer"] == "https://www.bilibili.com/"


def test_bilibili_client_missing_cookie_raises(monkeypatch, tmp_path):
    path = _write_cookies(tmp_path, ".zhihu.com\tTRUE\t/\tTRUE\t0\tname\tvalue\n")
    monkeypatch.setenv("COOKIES", path)
    with pytest.raises(ValueError, match="No cookies found"):
        BilibiliClient()
