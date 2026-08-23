#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Twitter Likes 接口返回的数据模型。

@Author : bGZo
@Date : 2026-08-19
@Links : https://github.com/bGZo
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TwitterUser:
    """Tweet 作者信息。"""

    screen_name: str
    name: str
    id: str = ""

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "TwitterUser":
        legacy = data.get("legacy") or {}
        core = data.get("core") or {}
        return TwitterUser(
            screen_name=legacy.get("screen_name") or core.get("screen_name") or "",
            name=legacy.get("name") or core.get("name") or "",
            id=legacy.get("id_str") or data.get("id") or data.get("rest_id") or "",
        )


@dataclass
class Tweet:
    """单条点赞 Tweet。"""

    id_str: str
    created_at: str
    full_text: str
    author: TwitterUser
    favorite_count: int = 0
    retweet_count: int = 0
    reply_count: int = 0
    view_count: int = 0

    @property
    def url(self) -> str:
        """构造 Tweet 链接。"""
        screen_name = self.author.screen_name or "i"
        return f"https://x.com/{screen_name}/status/{self.id_str}"

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Tweet | None:
        if data.get("__typename") == "TweetWithVisibilityResults":
            data = data.get("tweet") or {}

        legacy = data.get("legacy") or {}
        if not legacy.get("id_str"):
            return None

        user_result = ((data.get("core") or {}).get("user_results") or {}).get(
            "result"
        ) or {}
        author = TwitterUser.from_dict(user_result)

        views = data.get("views") or {}
        try:
            view_count = int(views.get("count") or 0)
        except (TypeError, ValueError):
            view_count = 0

        return Tweet(
            id_str=legacy["id_str"],
            created_at=legacy.get("created_at", ""),
            full_text=legacy.get("full_text", ""),
            author=author,
            favorite_count=legacy.get("favorite_count", 0),
            retweet_count=legacy.get("retweet_count", 0),
            reply_count=legacy.get("reply_count", 0),
            view_count=view_count,
        )


@dataclass
class TimelineCursor:
    """时间线游标，用于分页。"""

    value: str
    cursor_type: str

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "TimelineCursor":
        return TimelineCursor(
            value=data.get("value", ""),
            cursor_type=data.get("cursorType", ""),
        )


@dataclass
class LikesPage:
    """单页 Likes 结果。"""

    tweets: list[Tweet] = field(default_factory=list)
    cursor_bottom: TimelineCursor | None = None

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "LikesPage":
        tweets: list[Tweet] = []
        cursor_bottom: TimelineCursor | None = None

        user_result = (data.get("user") or {}).get("result") or {}
        nested = user_result.get("timeline_v2") or user_result.get("timeline") or {}
        timeline = nested.get("timeline") or {}
        instructions = timeline.get("instructions") or []

        for instruction in instructions:
            if instruction.get("type") != "TimelineAddEntries":
                continue
            for entry in instruction.get("entries") or []:
                entry_id = entry.get("entryId", "")
                content = entry.get("content") or {}

                if content.get("entryType") == "TimelineTimelineCursor":
                    cursor = TimelineCursor.from_dict(content)
                    if cursor.cursor_type == "Bottom":
                        cursor_bottom = cursor
                    continue

                if not entry_id.startswith("tweet-"):
                    continue

                item_content = content.get("itemContent") or (
                    content.get("content") or {}
                ).get("itemContent") or {}
                if item_content.get("itemType") != "TimelineTweet":
                    continue

                tweet_results = item_content.get("tweet_results") or {}
                tweet = Tweet.from_dict(tweet_results.get("result") or {})
                if tweet is not None:
                    tweets.append(tweet)

        return LikesPage(tweets=tweets, cursor_bottom=cursor_bottom)
