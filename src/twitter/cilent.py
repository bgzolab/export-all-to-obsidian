#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Twitter 网页接口客户端。

@Author : bGZo
@Date : 2026-08-19
@Links : https://github.com/bGZo
"""
import os
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from twitter.api_endpoints import TWITTER_BEARER_TOKEN
from twitter.api_endpoints import TWITTER_COOKIE_ENV
from twitter.api_endpoints import TWITTER_CSRF_ENV
from twitter.api_endpoints import TWITTER_USER_ID_ENV

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:144.0) "
    "Gecko/20100101 Firefox/144.0"
)


def _derive_user_id_from_cookie(cookie: str) -> str | None:
    """从 Cookie 的 twid=u%3D<id> 推导用户 ID。"""
    match = re.search(r"twid=u%3D(\d+)", cookie, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return None


class TwitterClient:
    """封装 X 网页端 GraphQL 请求所需的 Cookie 与请求头。"""

    def __init__(self) -> None:
        cookie = os.getenv(TWITTER_COOKIE_ENV)
        if not cookie:
            raise ValueError(f"{TWITTER_COOKIE_ENV} environment variable is not set.")

        csrf_token = os.getenv(TWITTER_CSRF_ENV)
        if not csrf_token:
            match = re.search(r"ct0=([^;]+)", cookie, flags=re.IGNORECASE)
            if match:
                csrf_token = match.group(1)
        if not csrf_token:
            raise ValueError(
                f"{TWITTER_CSRF_ENV} environment variable is not set "
                "or Cookie missing ct0."
            )

        user_id = os.getenv(TWITTER_USER_ID_ENV) or _derive_user_id_from_cookie(cookie)
        if not user_id:
            raise ValueError(
                f"{TWITTER_USER_ID_ENV} environment variable is not set "
                "or Cookie missing twid."
            )
        self.user_id: str = user_id

        self.session = requests.Session()
        # 配置重试：X GraphQL 偶发 429/503 / 连接中断，自动重试并退避
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
        self.session.headers.update(
            {
                "Authorization": f"Bearer {TWITTER_BEARER_TOKEN}",
                "Cookie": cookie,
                "User-Agent": USER_AGENT,
                "x-csrf-token": csrf_token,
                "x-twitter-active-user": "yes",
                "x-twitter-auth-type": "OAuth2Session",
                "x-twitter-client-language": "en",
                "content-type": "application/json",
                "Accept": "*/*",
            }
        )
