#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author : bGZo
@Date : 2025-12-06
@Links : https://github.com/bGZo
"""
import pytest

from qireader.cilent import QiReaderClient


def _write_cookies(tmp_path, content):
    p = tmp_path / "cookies.txt"
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_qireader_client_headers_configured(monkeypatch, tmp_path):
    path = _write_cookies(tmp_path, ".qireader.com\tTRUE\t/\tTRUE\t0\tcookie\tvalue\n")
    monkeypatch.setenv("COOKIES", path)
    client = QiReaderClient()
    headers = client.session.headers
    assert headers["Cookie"] == "cookie=value"
    assert "User-Agent" in headers
    assert headers["Referer"] == "https://www.qireader.com/tags/!readlater"


def test_qireader_client_missing_cookie_raises(monkeypatch, tmp_path):
    path = _write_cookies(tmp_path, ".weibo.com\tTRUE\t/\tTRUE\t0\tname\tvalue\n")
    monkeypatch.setenv("COOKIES", path)
    with pytest.raises(ValueError, match="No cookies found"):
        QiReaderClient()