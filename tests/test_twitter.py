#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author : bGZo
@Date : 2026-08-19
@Links : https://github.com/bGZo
"""
import json

import pytest

from export_runtime.index_writer import IndexWriter

TWITTER_COOKIE = (
    "guest_id=1; twid=u%3D123456789012345678; "
    "ct0=0f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f80"
)


def _sample_tweet() -> dict:
    result = {
        "__typename": "TweetWithVisibilityResults",
        "tweet": {
            "rest_id": "111",
            "core": {
                "user_results": {
                    "result": {
                        "rest_id": "42",
                        "core": {"screen_name": "alice", "name": "Alice"},
                    }
                }
            },
            "legacy": {
                "id_str": "111",
                "created_at": "Thu Aug 15 12:00:00 +0000 2024",
                "full_text": "Hello Twitter",
                "favorite_count": 5,
                "retweet_count": 2,
                "reply_count": 1,
            },
            "views": {"count": "100"},
        },
    }
    return {
        "entryId": "tweet-111",
        "content": {
            "entryType": "TimelineTimelineItem",
            "itemContent": {
                "itemType": "TimelineTweet",
                "tweet_results": {"result": result},
            },
        },
    }


def _sample_cursor() -> dict:
    return {
        "entryId": "cursor-bottom-abc",
        "content": {
            "entryType": "TimelineTimelineCursor",
            "value": "NEXT_CURSOR",
            "cursorType": "Bottom",
        },
    }


def _sample_response(tweets: list, cursor: dict | None = None) -> dict:
    entries = list(tweets)
    if cursor is not None:
        entries.append(cursor)
    return {
        "data": {
            "user": {
                "result": {
                    "timeline": {
                        "timeline": {
                            "instructions": [
                                {
                                    "type": "TimelineAddEntries",
                                    "entries": entries,
                                },
                                {"type": "TimelineTerminateTimeline", "direction": "Top"},
                            ]
                        }
                    }
                }
            }
        }
    }


def _make_client(monkeypatch):
    from twitter.cilent import TwitterClient

    monkeypatch.setenv("TWITTER_COOKIE", TWITTER_COOKIE)
    return TwitterClient()


def test_twitter_client_headers_configured(monkeypatch):
    from twitter.cilent import TwitterClient

    client = _make_client(monkeypatch)
    headers = client.session.headers
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["Cookie"] == TWITTER_COOKIE
    assert headers["x-csrf-token"] == (
        "0f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f80"
    )
    assert headers["x-twitter-active-user"] == "yes"
    assert "User-Agent" in headers


def test_twitter_client_derives_user_id_from_twid(monkeypatch):
    from twitter.cilent import TwitterClient

    client = _make_client(monkeypatch)
    assert client.user_id == "123456789012345678"


def test_twitter_client_uses_user_id_env(monkeypatch):
    from twitter.cilent import TwitterClient

    monkeypatch.setenv("TWITTER_COOKIE", TWITTER_COOKIE)
    monkeypatch.setenv("TWITTER_USER_ID", "999")
    client = TwitterClient()
    assert client.user_id == "999"


def test_twitter_client_csrf_from_env(monkeypatch):
    from twitter.cilent import TwitterClient

    monkeypatch.setenv("TWITTER_COOKIE", TWITTER_COOKIE)
    monkeypatch.setenv("TWITTER_CSRF_TOKEN", "csrf-from-env")
    client = TwitterClient()
    assert client.session.headers["x-csrf-token"] == "csrf-from-env"


def test_twitter_client_missing_cookie_raises(monkeypatch):
    from twitter.cilent import TwitterClient

    monkeypatch.delenv("TWITTER_COOKIE", raising=False)
    try:
        TwitterClient()
        assert False, "应抛出 ValueError"
    except ValueError as exc:
        assert "TWITTER_COOKIE" in str(exc)


def test_twitter_client_missing_user_id_raises(monkeypatch):
    from twitter.cilent import TwitterClient

    monkeypatch.setenv("TWITTER_COOKIE", "guest_id=1; ct0=abc")
    monkeypatch.delenv("TWITTER_USER_ID", raising=False)
    try:
        TwitterClient()
        assert False, "应抛出 ValueError"
    except ValueError as exc:
        assert "TWITTER_USER_ID" in str(exc)


def test_tweet_parsing():
    from twitter.entity import Tweet

    result = _sample_tweet()["content"]["itemContent"]["tweet_results"]["result"]
    tweet = Tweet.from_dict(result)
    assert tweet.id_str == "111"
    assert tweet.full_text == "Hello Twitter"
    assert tweet.author.screen_name == "alice"
    assert tweet.view_count == 100
    assert tweet.url == "https://x.com/alice/status/111"


def test_tweet_url_falls_back_to_i_status_when_no_screen_name():
    from twitter.entity import Tweet
    from twitter.entity import TwitterUser

    tweet = Tweet(
        id_str="111",
        created_at="",
        full_text="x",
        author=TwitterUser(screen_name="", name=""),
    )
    assert tweet.url == "https://x.com/i/status/111"


def test_tweet_parsing_legacy_nested_structure():
    """兼容旧版 timeline_v2 深层嵌套结构。"""
    from twitter.entity import Tweet

    result = {
        "__typename": "Tweet",
        "legacy": {"id_str": "222", "created_at": "", "full_text": "legacy"},
        "core": {
            "user_results": {
                "result": {"legacy": {"screen_name": "bob", "name": "Bob"}}
            }
        },
    }
    tweet = Tweet.from_dict(result)
    assert tweet is not None
    assert tweet.id_str == "222"
    assert tweet.author.screen_name == "bob"


def test_likes_page_parsing_legacy_timeline_v2():
    from twitter.entity import LikesPage

    tweet = {
        "entryId": "tweet-333",
        "content": {
            "entryType": "TimelineTimelineItem",
            "content": {
                "itemContent": {
                    "itemType": "TimelineTweet",
                    "tweet_results": {
                        "result": {
                            "__typename": "Tweet",
                            "legacy": {
                                "id_str": "333",
                                "created_at": "",
                                "full_text": "deep",
                            },
                            "core": {
                                "user_results": {
                                    "result": {
                                        "legacy": {
                                            "screen_name": "carol",
                                            "name": "Carol",
                                        }
                                    }
                                }
                            },
                        }
                    },
                }
            },
        },
    }
    payload = {
        "data": {
            "user": {
                "result": {
                    "timeline_v2": {
                        "timeline": {
                            "instructions": [
                                {
                                    "type": "TimelineAddEntries",
                                    "entries": [tweet],
                                }
                            ]
                        }
                    }
                }
            }
        }
    }
    page = LikesPage.from_dict(payload["data"])
    assert len(page.tweets) == 1
    assert page.tweets[0].id_str == "333"
    assert page.tweets[0].author.screen_name == "carol"


def test_likes_page_parsing_tweets_and_cursor():
    from twitter.entity import LikesPage

    payload = _sample_response([_sample_tweet()], cursor=_sample_cursor())
    page = LikesPage.from_dict(payload["data"])
    assert len(page.tweets) == 1
    assert page.tweets[0].id_str == "111"
    assert page.cursor_bottom is not None
    assert page.cursor_bottom.value == "NEXT_CURSOR"
    assert page.cursor_bottom.cursor_type == "Bottom"


def test_get_twitter_like_list_builds_params(monkeypatch):
    from twitter.entity import LikesPage
    from twitter.like import get_twitter_like_list

    client = _make_client(monkeypatch)

    captured = {}

    class FakeSession:
        def get(self, url, params, **kwargs):
            captured["url"] = url
            captured["params"] = params
            captured["timeout"] = kwargs.get("timeout")
            return FakeResponse(json.loads(json.dumps(_sample_response([]))))

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        @property
        def status_code(self):
            return 200

        def json(self):
            return self._payload

    client.session = FakeSession()
    page = get_twitter_like_list(client, count=5, cursor="CURSOR")
    assert isinstance(page, LikesPage)
    assert captured["url"].endswith("/Likes")
    variables = json.loads(captured["params"]["variables"])
    assert variables["userId"] == "123456789012345678"
    assert variables["count"] == 5
    assert variables["cursor"] == "CURSOR"
    assert "features" in captured["params"]
    assert captured["timeout"] == 30


def test_build_likes_params_no_cursor():
    from twitter.like import build_likes_params

    params = build_likes_params("123", 3)
    variables = json.loads(params["variables"])
    assert variables["userId"] == "123"
    assert variables["count"] == 3
    assert "cursor" not in variables
    assert "features" in params
    assert "fieldToggles" in params


def test_build_likes_params_with_cursor():
    from twitter.like import build_likes_params

    params = build_likes_params("123", 3, cursor="NEXT")
    assert json.loads(params["variables"])["cursor"] == "NEXT"


def test_exporter_writes_files_and_index(monkeypatch, tmp_path):
    from twitter import exporter as exporter_module
    from twitter.entity import LikesPage
    from twitter.entity import TimelineCursor
    from twitter.entity import Tweet
    from twitter.entity import TwitterUser

    monkeypatch.setenv("TWITTER_COOKIE", TWITTER_COOKIE)

    page = LikesPage(
        tweets=[
            Tweet(
                id_str="111",
                created_at="Thu Aug 15 12:00:00 +0000 2024",
                full_text="Hello Twitter",
                author=TwitterUser(screen_name="alice", name="Alice"),
            )
        ],
        cursor_bottom=TimelineCursor(value="NEXT", cursor_type="Bottom"),
    )

    calls = []

    def fake_get_like_list(client, count=20, cursor=None):
        calls.append(cursor)
        if cursor == "NEXT":
            return LikesPage(tweets=[])
        return page

    exporter_module.get_twitter_like_list = fake_get_like_list
    exporter_module.TwitterClient = lambda: type("C", (), {"user_id": "123456789012345678"})()

    writer = IndexWriter(file_path=str(tmp_path / "index.md"))
    exporter_module.export(str(tmp_path), writer)

    target = tmp_path / "~alice-111.md"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "Hello Twitter" in content
    assert "Alice" in content
    assert "https://x.com/alice/status/111" in content

    index = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert "## twitter" in index
    assert "~alice-111" in index
    assert calls == [None, "NEXT"]


def test_exporter_stops_on_existing_file(monkeypatch, tmp_path):
    from twitter import exporter as exporter_module
    from twitter.entity import LikesPage
    from twitter.entity import Tweet
    from twitter.entity import TwitterUser

    monkeypatch.setenv("TWITTER_COOKIE", TWITTER_COOKIE)

    (tmp_path / "~alice-111.md").write_text("existing", encoding="utf-8")

    page = LikesPage(
        tweets=[
            Tweet(
                id_str="111",
                created_at="Thu Aug 15 12:00:00 +0000 2024",
                full_text="Hello Twitter",
                author=TwitterUser(screen_name="alice", name="Alice"),
            )
        ]
    )
    exporter_module.get_twitter_like_list = lambda client, count=20, cursor=None: page
    exporter_module.TwitterClient = lambda: type("C", (), {"user_id": "123456789012345678"})()

    writer = IndexWriter(file_path=str(tmp_path / "index.md"))
    exporter_module.export(str(tmp_path), writer)

    assert (tmp_path / "~alice-111.md").read_text(encoding="utf-8") == "existing"


def test_exporter_stops_on_fetch_exception_and_flushes(monkeypatch, tmp_path):
    from twitter import exporter as exporter_module

    monkeypatch.setenv("TWITTER_COOKIE", TWITTER_COOKIE)

    def boom(client, count=20, cursor=None):
        raise RuntimeError("network down")

    exporter_module.get_twitter_like_list = boom
    exporter_module.TwitterClient = lambda: type("C", (), {"user_id": "123456789012345678"})()
    exporter_module.add_index_entry = lambda *a, **k: None

    writer = IndexWriter(file_path=str(tmp_path / "index.md"))
    exporter_module.export(str(tmp_path), writer)

    index = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert "## twitter" in index


def test_exporter_filename_falls_back_to_author_id(monkeypatch, tmp_path):
    from twitter import exporter as exporter_module
    from twitter.entity import LikesPage
    from twitter.entity import TimelineCursor
    from twitter.entity import Tweet
    from twitter.entity import TwitterUser

    monkeypatch.setenv("TWITTER_COOKIE", TWITTER_COOKIE)

    page = LikesPage(
        tweets=[
            Tweet(
                id_str="111",
                created_at="Thu Aug 15 12:00:00 +0000 2024",
                full_text="Hello Twitter",
                author=TwitterUser(screen_name="", name="", id="42"),
            )
        ],
        cursor_bottom=TimelineCursor(value="NEXT", cursor_type="Bottom"),
    )

    exporter_module.get_twitter_like_list = lambda client, count=20, cursor=None: page
    exporter_module.TwitterClient = lambda: type("C", (), {"user_id": "123456789012345678"})()

    writer = IndexWriter(file_path=str(tmp_path / "index.md"))
    exporter_module.export(str(tmp_path), writer)

    assert (tmp_path / "~42-111.md").exists()
