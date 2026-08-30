#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author : bGZo
@Date : 2025-12-06
@Links : https://github.com/bGZo
"""
import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.cookies import get_cookie_header
from v2ex import api_endpoints

class V2exClient:
    def __init__(self):
        # 先校验 token 再取 cookie：缺 V2EX_ACCESS_TOKEN 属于凭证缺失（抛 ValueError，
        # 由 credential_guard 判为 invalid 走「跳过+提醒」），不应复用 CookiesConfigError
        # 的「硬退出」语义，也避免 COOKIES 未设时先报 cookies 错误而掩盖令牌缺失。
        self.token = os.getenv("V2EX_ACCESS_TOKEN")
        if not self.token:
            raise ValueError(
                "V2EX_ACCESS_TOKEN environment variable is not set."
            )
        self.cookie = get_cookie_header(("v2ex.com",))

        self.session = requests.Session()
        # 配置重试：v2ex 偶发 SSL 握手中断 / 限流，需自动重试并退避
        # 注意 SSLError 走 urllib3 Retry 的 "other" 分支，需显式设置 other 才会重试
        retry = Retry(
            total=5,
            connect=5,
            read=5,
            other=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Cookie": f"{self.cookie}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:144.0) Gecko/20100101 Firefox/144.0",
            "Referer": "https://www.v2ex.com"
        })
        self.api_endpoints = api_endpoints
