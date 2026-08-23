#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Twitter Likes 接口拉取逻辑。

@Author : bGZo
@Date : 2026-08-19
@Links : https://github.com/bGZo
"""
from __future__ import annotations

import json

from twitter.api_endpoints import TWITTER_LIKES_FEATURES
from twitter.api_endpoints import TWITTER_LIKES_FIELD_TOGGLES
from twitter.api_endpoints import TWITTER_LIKES_PATH
from twitter.client import TwitterClient
from twitter.entity import LikesPage


def build_likes_params(
    user_id: str,
    count: int,
    cursor: str | None = None,
) -> dict[str, str]:
    """构造 Likes GraphQL 查询参数。"""
    variables = {
        "userId": user_id,
        "count": count,
        "includePromotedContent": False,
        "withClientEventToken": False,
        "withBirdwatchNotes": False,
        "withVoice": True,
    }
    if cursor:
        variables["cursor"] = cursor
    return {
        "features": json.dumps(TWITTER_LIKES_FEATURES),
        "fieldToggles": json.dumps(TWITTER_LIKES_FIELD_TOGGLES),
        "variables": json.dumps(variables),
    }


def get_twitter_like_list(
    client: TwitterClient,
    count: int = 20,
    cursor: str | None = None,
) -> LikesPage | None:
    """拉取指定用户的一页点赞 Tweet。"""
    response = client.session.get(
        TWITTER_LIKES_PATH,
        params=build_likes_params(client.user_id, count, cursor),
        timeout=30,
    )
    if response.status_code != 200:
        print(f"Twitter Likes 请求失败: HTTP {response.status_code}")
        return None

    payload = response.json()
    if not isinstance(payload, dict):
        print("Twitter Likes 响应解析失败: 非 JSON 对象")
        return None
    data = payload.get("data")
    if not data:
        return None
    return LikesPage.from_dict(data)
