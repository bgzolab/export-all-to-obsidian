#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
获取 Cookie https://weibo.com/u/page/like/8221250887

@Author : bGZo
@Date : 2025-12-06
@Links : https://github.com/bGZo
"""
import requests

from app.cookies import get_cookie_header
from demo import (api_endpoints)

class WeiboClient:
    def __init__(self):
        # weibo.com/weibo.cn 是「主站 + 旧域」，浏览器导出的 cookies.txt 常同时
        # 含两域的同名 Cookie（如 SUB），按域名优先级去重，weibo.com 优先。
        self.cookie = get_cookie_header(
            ("weibo.com", "weibo.cn"), dedupe_by_name=True
        )

        self.session = requests.Session()
        self.session.headers.update({
            "Cookie": f"{self.cookie}",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:144.0) Gecko/20100101 Firefox/144.0",
            "Referer": "https://weibo.com/u/page/like/"
        })
        self.api_endpoints = api_endpoints

