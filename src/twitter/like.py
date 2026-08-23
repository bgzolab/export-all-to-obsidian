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
from twitter.cilent import TwitterClient
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
    user_id = client.user_id
    if not user_id:
        return None

    response = client.session.get(
        TWITTER_LIKES_PATH,
        params=build_likes_params(user_id, count, cursor),
    )
    if response.status_code != 200:
        return None

    payload = response.json()
    data = payload.get("data")
    if not data:
        return None
    return LikesPage.from_dict(data)


if __name__ == "__main__":
    print(get_twitter_like_list(TwitterClient(), 5))
