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


def _write_twitter_cookies(monkeypatch, tmp_path, cookie_header=TWITTER_COOKIE):
    """将 Cookie 头字符串写入 Netscape cookies.txt 并设置 COOKIES 指向它。"""
    lines = []
    for pair in cookie_header.split("; "):
        name, value = pair.split("=", 1)
        lines.append(f".x.com\tTRUE\t/\tTRUE\t0\t{name}\t{value}\n")
    p = tmp_path / "cookies.txt"
    p.write_text("".join(lines), encoding="utf-8")
    monkeypatch.setenv("COOKIES", str(p))
    return str(p)


def _make_client(monkeypatch, tmp_path):
    from twitter.client import TwitterClient

    _write_twitter_cookies(monkeypatch, tmp_path)
    monkeypatch.delenv("TWITTER_USER_ID", raising=False)
    monkeypatch.delenv("TWITTER_CSRF_TOKEN", raising=False)
    return TwitterClient()


def test_twitter_client_headers_configured(monkeypatch, tmp_path):
    from twitter.client import TwitterClient

    client = _make_client(monkeypatch, tmp_path)
    headers = client.session.headers
    assert headers["Authorization"].startswith("Bearer ")
    assert headers["Cookie"] == TWITTER_COOKIE
    assert headers["x-csrf-token"] == (
        "0f1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f80"
    )
    assert headers["x-twitter-active-user"] == "yes"
    assert "User-Agent" in headers


def test_twitter_client_derives_user_id_from_twid(monkeypatch, tmp_path):
    from twitter.client import TwitterClient

    client = _make_client(monkeypatch, tmp_path)
    assert client.user_id == "123456789012345678"


def test_twitter_client_derives_user_id_from_decoded_twid(monkeypatch, tmp_path):
    from twitter.client import TwitterClient

    _write_twitter_cookies(monkeypatch, tmp_path, "guest_id=1; twid=u=987654321098765432; ct0=abc")
    monkeypatch.delenv("TWITTER_USER_ID", raising=False)
    client = TwitterClient()
    assert client.user_id == "987654321098765432"


def test_twitter_client_strips_ct0_trailing_whitespace(monkeypatch, tmp_path):
    from twitter.client import TwitterClient

    _write_twitter_cookies(monkeypatch, tmp_path, "guest_id=1; twid=u%3D123456789012345678; ct0=csrfabc \n")
    monkeypatch.delenv("TWITTER_CSRF_TOKEN", raising=False)
    client = TwitterClient()
    assert client.session.headers["x-csrf-token"] == "csrfabc"


def test_twitter_client_missing_ct0_raises(monkeypatch, tmp_path):
    from twitter.client import TwitterClient

    _write_twitter_cookies(monkeypatch, tmp_path, "guest_id=1; twid=u%3D123456789012345678")
    monkeypatch.delenv("TWITTER_CSRF_TOKEN", raising=False)
    with pytest.raises(ValueError, match="ct0"):
        TwitterClient()


def test_twitter_client_uses_user_id_env(monkeypatch, tmp_path):
    from twitter.client import TwitterClient

    _write_twitter_cookies(monkeypatch, tmp_path)
    monkeypatch.setenv("TWITTER_USER_ID", "999")
    client = TwitterClient()
    assert client.user_id == "999"


def test_twitter_client_csrf_from_env(monkeypatch, tmp_path):
    from twitter.client import TwitterClient

    _write_twitter_cookies(monkeypatch, tmp_path)
    monkeypatch.setenv("TWITTER_CSRF_TOKEN", "csrf-from-env")
    client = TwitterClient()
    assert client.session.headers["x-csrf-token"] == "csrf-from-env"


def test_twitter_client_missing_cookie_raises(monkeypatch, tmp_path):
    from twitter.client import TwitterClient

    # 无 twitter/x.com 域的 cookies.txt
    p = tmp_path / "cookies.txt"
    p.write_text(".zhihu.com\tTRUE\t/\tTRUE\t0\tname\tvalue\n", encoding="utf-8")
    monkeypatch.setenv("COOKIES", str(p))
    with pytest.raises(ValueError, match="No cookies found"):
        TwitterClient()


def test_twitter_client_missing_user_id_raises(monkeypatch, tmp_path):
    from twitter.client import TwitterClient

    _write_twitter_cookies(monkeypatch, tmp_path, "guest_id=1; ct0=abc")
    monkeypatch.delenv("TWITTER_USER_ID", raising=False)
    with pytest.raises(ValueError, match="TWITTER_USER_ID"):
        TwitterClient()


def test_twitter_client_dedupes_x_com_and_twitter_com(monkeypatch, tmp_path):
    """端到端：cookies.txt 同时含 .x.com 与 .twitter.com 的同名 Cookie 时，
    TwitterClient 输出的 Cookie 头应去重且 csrf 取 x.com 的值。"""
    from twitter.client import TwitterClient

    lines = [
        # 旧域 twitter.com 的 ct0 写在前面，验证最终仍取 x.com 的值
        ".twitter.com\tTRUE\t/\tTRUE\t0\tct0\tOLD_CSRF\n"
        ".twitter.com\tTRUE\t/\tTRUE\t0\ttwid\tu%3D123456789012345678\n"
        ".x.com\tTRUE\t/\tTRUE\t0\tct0\tNEW_CSRF\n"
        ".x.com\tTRUE\t/\tTRUE\t0\ttwid\tu%3D123456789012345678\n"
    ]
    p = tmp_path / "cookies.txt"
    p.write_text("".join(lines), encoding="utf-8")
    monkeypatch.setenv("COOKIES", str(p))
    monkeypatch.delenv("TWITTER_USER_ID", raising=False)
    monkeypatch.delenv("TWITTER_CSRF_TOKEN", raising=False)
    client = TwitterClient()
    cookie_header = client.session.headers["Cookie"]
    assert cookie_header == (
        "ct0=NEW_CSRF; twid=u%3D123456789012345678"
    )
    assert client.session.headers["x-csrf-token"] == "NEW_CSRF"
    assert client.user_id == "123456789012345678"


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


def test_tweet_parsing_realistic_legacy_author():
    """贴近 X 真实响应：作者字段位于 legacy、rest_id 位于顶层。"""
    from twitter.entity import Tweet

    result = {
        "__typename": "Tweet",
        "rest_id": "444",
        "legacy": {
            "id_str": "444",
            "created_at": "Thu Aug 15 12:00:00 +0000 2024",
            "full_text": "Realistic tweet",
            "favorite_count": 7,
            "retweet_count": 3,
            "reply_count": 1,
        },
        "core": {
            "user_results": {
                "result": {
                    "rest_id": "42",
                    "legacy": {"screen_name": "alice", "name": "Alice"},
                }
            }
        },
    }
    tweet = Tweet.from_dict(result)
    assert tweet is not None
    assert tweet.id_str == "444"
    assert tweet.author.screen_name == "alice"
    assert tweet.author.name == "Alice"
    assert tweet.author.id == "42"
    assert tweet.url == "https://x.com/alice/status/444"


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


def test_likes_page_ignores_non_bottom_cursor():
    from twitter.entity import LikesPage

    tweet = _sample_tweet()
    top_cursor = {
        "entryId": "cursor-top-abc",
        "content": {
            "entryType": "TimelineTimelineCursor",
            "value": "TOP_CURSOR",
            "cursorType": "Top",
        },
    }
    payload = _sample_response([tweet], cursor=top_cursor)
    page = LikesPage.from_dict(payload["data"])
    assert len(page.tweets) == 1
    assert page.cursor_bottom is None


def test_parse_created_at_preserves_timezone():
    from twitter.exporter import _parse_created_at

    assert (
        _parse_created_at("Thu Aug 15 12:00:00 +0000 2024")
        == "2024-08-15T12:00:00+0000"
    )
    assert (
        _parse_created_at("Fri Aug 16 09:30:00 +0800 2024")
        == "2024-08-16T09:30:00+0800"
    )


def test_parse_created_at_returns_raw_on_invalid():
    from twitter.exporter import _parse_created_at

    assert _parse_created_at("") == ""
    assert _parse_created_at("not a date") == "not a date"
    assert _parse_created_at("Foo Bar 99 99:99:99 +0000 2024") == (
        "Foo Bar 99 99:99:99 +0000 2024"
    )


def test_get_twitter_like_list_builds_params(monkeypatch, tmp_path):
    from twitter.entity import LikesPage
    from twitter.like import get_twitter_like_list

    client = _make_client(monkeypatch, tmp_path)

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


def test_get_twitter_like_list_returns_none_on_non_dict_payload(monkeypatch, tmp_path):
    from twitter.like import get_twitter_like_list

    client = _make_client(monkeypatch, tmp_path)

    class FakeSession:
        def get(self, url, params, **kwargs):
            return FakeResponse()

    class FakeResponse:
        @property
        def status_code(self):
            return 200

        def json(self):
            return ["not", "a", "dict"]

    client.session = FakeSession()
    assert get_twitter_like_list(client) is None


def test_get_twitter_like_list_returns_none_on_json_decode_error(monkeypatch, tmp_path):
    from twitter.like import get_twitter_like_list

    client = _make_client(monkeypatch, tmp_path)

    class FakeSession:
        def get(self, url, params, **kwargs):
            return FakeResponse()

    class FakeResponse:
        @property
        def status_code(self):
            return 200

        def json(self):
            raise json.JSONDecodeError("Expecting value", "doc", 0)

    client.session = FakeSession()
    assert get_twitter_like_list(client) is None


def test_get_twitter_like_list_returns_none_on_non_dict_data(monkeypatch, tmp_path):
    from twitter.like import get_twitter_like_list

    client = _make_client(monkeypatch, tmp_path)

    class FakeSession:
        def get(self, url, params, **kwargs):
            return FakeResponse()

    class FakeResponse:
        @property
        def status_code(self):
            return 200

        def json(self):
            return {"data": ["not", "a", "dict"]}

    client.session = FakeSession()
    assert get_twitter_like_list(client) is None


def test_exporter_writes_files_and_index(monkeypatch, tmp_path):
    from twitter import exporter as exporter_module
    from twitter.entity import LikesPage
    from twitter.entity import TimelineCursor
    from twitter.entity import Tweet
    from twitter.entity import TwitterUser

    _write_twitter_cookies(monkeypatch, tmp_path)

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

    monkeypatch.setattr(exporter_module, "get_twitter_like_list", fake_get_like_list)
    monkeypatch.setattr(exporter_module, "TwitterClient", lambda: type("C", (), {"user_id": "123456789012345678"})())

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

    _write_twitter_cookies(monkeypatch, tmp_path)

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
    monkeypatch.setattr(exporter_module, "get_twitter_like_list", lambda client, count=20, cursor=None: page)
    monkeypatch.setattr(exporter_module, "TwitterClient", lambda: type("C", (), {"user_id": "123456789012345678"})())

    writer = IndexWriter(file_path=str(tmp_path / "index.md"))
    exporter_module.export(str(tmp_path), writer)

    assert (tmp_path / "~alice-111.md").read_text(encoding="utf-8") == "existing"


def test_exporter_stops_on_fetch_exception_and_flushes(monkeypatch, tmp_path):
    from twitter import exporter as exporter_module

    _write_twitter_cookies(monkeypatch, tmp_path)

    def boom(client, count=20, cursor=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(exporter_module, "get_twitter_like_list", boom)
    monkeypatch.setattr(exporter_module, "TwitterClient", lambda: type("C", (), {"user_id": "123456789012345678"})())
    monkeypatch.setattr(exporter_module, "add_index_entry", lambda *a, **k: None)

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

    _write_twitter_cookies(monkeypatch, tmp_path)

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

    monkeypatch.setattr(exporter_module, "get_twitter_like_list", lambda client, count=20, cursor=None: page)
    monkeypatch.setattr(exporter_module, "TwitterClient", lambda: type("C", (), {"user_id": "123456789012345678"})())

    writer = IndexWriter(file_path=str(tmp_path / "index.md"))
    exporter_module.export(str(tmp_path), writer)

    assert (tmp_path / "~42-111.md").exists()


def test_exporter_breaks_on_empty_cursor_value(monkeypatch, tmp_path):
    from twitter import exporter as exporter_module
    from twitter.entity import LikesPage
    from twitter.entity import TimelineCursor
    from twitter.entity import Tweet
    from twitter.entity import TwitterUser

    _write_twitter_cookies(monkeypatch, tmp_path)

    page = LikesPage(
        tweets=[
            Tweet(
                id_str="111",
                created_at="Thu Aug 15 12:00:00 +0000 2024",
                full_text="Hello Twitter",
                author=TwitterUser(screen_name="alice", name="Alice"),
            )
        ],
        cursor_bottom=TimelineCursor(value="", cursor_type="Bottom"),
    )

    calls = []

    def fake_get_like_list(client, count=20, cursor=None):
        calls.append(cursor)
        return page

    monkeypatch.setattr(exporter_module, "get_twitter_like_list", fake_get_like_list)
    monkeypatch.setattr(exporter_module, "TwitterClient", lambda: type("C", (), {"user_id": "123456789012345678"})())
    monkeypatch.setattr(exporter_module, "stop_if_output_exists", lambda *a, **k: False)

    writer = IndexWriter(file_path=str(tmp_path / "index.md"))
    exporter_module.export(str(tmp_path), writer)

    assert (tmp_path / "~alice-111.md").exists()
    assert calls == [None]


def test_exporter_stops_when_cursor_repeats(monkeypatch, tmp_path):
    from twitter import exporter as exporter_module
    from twitter.entity import LikesPage
    from twitter.entity import TimelineCursor
    from twitter.entity import Tweet
    from twitter.entity import TwitterUser

    _write_twitter_cookies(monkeypatch, tmp_path)

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
        return page

    monkeypatch.setattr(exporter_module, "get_twitter_like_list", fake_get_like_list)
    monkeypatch.setattr(exporter_module, "TwitterClient", lambda: type("C", (), {"user_id": "123456789012345678"})())
    monkeypatch.setattr(exporter_module, "stop_if_output_exists", lambda *a, **k: False)

    writer = IndexWriter(file_path=str(tmp_path / "index.md"))
    exporter_module.export(str(tmp_path), writer)

    assert (tmp_path / "~alice-111.md").exists()
    assert calls == [None, "NEXT"]


def test_exporter_stops_at_max_pages(monkeypatch, tmp_path):
    from twitter import exporter as exporter_module
    from twitter.entity import LikesPage
    from twitter.entity import TimelineCursor
    from twitter.entity import Tweet
    from twitter.entity import TwitterUser

    _write_twitter_cookies(monkeypatch, tmp_path)

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
        return LikesPage(
            tweets=[
                Tweet(
                    id_str=f"{len(calls)}",
                    created_at="Thu Aug 15 12:00:00 +0000 2024",
                    full_text="Hello",
                    author=TwitterUser(screen_name=f"alice{len(calls)}", name="A"),
                )
            ],
            cursor_bottom=TimelineCursor(value=f"cursor-{len(calls)}", cursor_type="Bottom"),
        )

    monkeypatch.setattr(exporter_module, "get_twitter_like_list", fake_get_like_list)
    monkeypatch.setattr(exporter_module, "TwitterClient", lambda: type("C", (), {"user_id": "123456789012345678"})())
    monkeypatch.setattr(exporter_module, "stop_if_output_exists", lambda *a, **k: False)

    writer = IndexWriter(file_path=str(tmp_path / "index.md"))
    exporter_module.export(str(tmp_path), writer, max_pages=3)

    assert len(calls) == 3
    assert (tmp_path / "~alice1-1.md").exists()


def test_exporter_falls_back_to_default_when_max_pages_zero(monkeypatch, tmp_path):
    from twitter import exporter as exporter_module
    from twitter.entity import LikesPage
    from twitter.entity import TimelineCursor
    from twitter.entity import Tweet
    from twitter.entity import TwitterUser

    _write_twitter_cookies(monkeypatch, tmp_path)

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
        return page

    monkeypatch.setattr(
        exporter_module, "get_twitter_like_list", fake_get_like_list
    )
    monkeypatch.setattr(
        exporter_module,
        "TwitterClient",
        lambda: type("C", (), {"user_id": "123456789012345678"})(),
    )
    monkeypatch.setattr(exporter_module, "stop_if_output_exists", lambda *a, **k: False)

    writer = IndexWriter(file_path=str(tmp_path / "index.md"))
    exporter_module.export(str(tmp_path), writer, max_pages=0)

    # 若 max_pages 未回退到默认值，则会在 0 >= 0 时立即停止，calls 为空
    assert calls == [None, "NEXT"]


def test_exporter_title_falls_back_to_id_when_text_empty(monkeypatch, tmp_path):
    from twitter import exporter as exporter_module
    from twitter.entity import LikesPage
    from twitter.entity import Tweet
    from twitter.entity import TwitterUser

    _write_twitter_cookies(monkeypatch, tmp_path)

    page = LikesPage(
        tweets=[
            Tweet(
                id_str="111",
                created_at="",
                full_text="",
                author=TwitterUser(screen_name="alice", name="Alice"),
            )
        ]
    )
    monkeypatch.setattr(exporter_module, "get_twitter_like_list", lambda client, count=20, cursor=None: page)
    monkeypatch.setattr(exporter_module, "TwitterClient", lambda: type("C", (), {"user_id": "123456789012345678"})())

    writer = IndexWriter(file_path=str(tmp_path / "index.md"))
    exporter_module.export(str(tmp_path), writer)

    content = (tmp_path / "~alice-111.md").read_text(encoding="utf-8")
    assert "Alice:111" in content
    assert "Alice:" not in content.replace("Alice:111", "")
