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

from app.cookies import CookiesConfigError
from app.cookies import get_cookie_header
from twitter.api_endpoints import TWITTER_BEARER_TOKEN
from twitter.api_endpoints import TWITTER_CSRF_ENV
from twitter.api_endpoints import TWITTER_USER_ID_ENV

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:144.0) "
    "Gecko/20100101 Firefox/144.0"
)


def _derive_user_id_from_cookie(cookie: str) -> str | None:
    """从 Cookie 的 twid=u%3D<id>（或已解码的 twid=u=<id>）推导用户 ID。"""
    match = re.search(r"twid=u(?:%3D|=)(\d+)", cookie, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return None


class TwitterClient:
    """封装 X 网页端 GraphQL 请求所需的 Cookie 与请求头。"""

    def __init__(self) -> None:
        cookie = get_cookie_header(("x.com", "twitter.com"))

        csrf_token = os.getenv(TWITTER_CSRF_ENV)
        if not csrf_token:
            match = re.search(r"ct0=([^;]+)", cookie, flags=re.IGNORECASE)
            if match:
                csrf_token = match.group(1).strip()
        if not csrf_token:
            raise CookiesConfigError(
                f"{TWITTER_CSRF_ENV} environment variable is not set "
                "or Cookie missing ct0."
            )

        user_id = os.getenv(TWITTER_USER_ID_ENV) or _derive_user_id_from_cookie(cookie)
        if not user_id:
            raise CookiesConfigError(
                f"{TWITTER_USER_ID_ENV} environment variable is not set "
                "or Cookie missing twid."
            )
        self.user_id: str = user_id

        self.session = requests.Session()
        # 配置重试：X GraphQL 偶发 503 / 连接中断自动重试并退避。
        # 注意：429（限流）窗口长达约 15 分钟，短退避重试只会徒增耗时，
        # 因此不列入 status_forcelist，交由上层直接结束本轮导出。
        # 重试次数刻意压低，避免持续性 5xx 时单页阻塞过久（2 次退避 1+2=3s）。
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            other=2,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
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
