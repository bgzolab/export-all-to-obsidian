"""
@Author : bGZo
@Date : 2025-08-07
@Links : https://github.com/bGZo
"""

from types import SimpleNamespace

import pytest
from urllib3.util.retry import Retry

from v2ex.cilent import V2exClient
from v2ex.mytopic import get_fav_html_with_page, get_fav_list_topic_id_page
from v2ex.replies import fetch_all_replies, get_replies_page_info
from v2ex.tipped import get_balance_page, parse_balance_page
from v2ex.topic import get_v2ex_topic_info


def _write_cookies_file(tmp_path, line):
    p = tmp_path / 'cookies.txt'
    p.write_text(line, encoding='utf-8')
    return str(p)


def _make_client(monkeypatch, tmp_path):
    monkeypatch.setenv('V2EX_ACCESS_TOKEN', 'fake-token')
    p = _write_cookies_file(
        tmp_path, '.v2ex.com\tTRUE\t/\tTRUE\t0\tfake-cookie-name\tfake-cookie\n'
    )
    monkeypatch.setenv('COOKIES', p)
    return V2exClient()


def test_v2ex_client_session_has_retry_adapter(monkeypatch, tmp_path):
    """V2exClient 的 session 应挂载带重试配置的 HTTPAdapter。"""
    client = _make_client(monkeypatch, tmp_path)
    adapter = client.session.get_adapter('https://www.v2ex.com/')
    retry = adapter.max_retries
    assert isinstance(retry, Retry)
    assert retry.total == 5
    assert retry.connect == 5
    assert retry.read == 5
    assert retry.other == 5
    assert retry.backoff_factor == 1


def test_v2ex_client_retry_covers_ssl_errors(monkeypatch, tmp_path):
    """SSL 错误走 other 分支，other 必须大于 0 才会重试。"""
    client = _make_client(monkeypatch, tmp_path)
    adapter = client.session.get_adapter('https://www.v2ex.com/')
    retry = adapter.max_retries
    # other 默认为 None（不重试），显式设置后应能重试 SSL 错误
    assert retry.other == 5


def test_v2ex_client_headers_configured(monkeypatch, tmp_path):
    """session 应携带 Authorization、Cookie、User-Agent 头。"""
    client = _make_client(monkeypatch, tmp_path)
    headers = client.session.headers
    assert headers['Authorization'] == 'Bearer fake-token'
    assert headers['Cookie'] == 'fake-cookie-name=fake-cookie'
    assert 'User-Agent' in headers
    assert headers['Referer'] == 'https://www.v2ex.com'


def test_v2ex_client_includes_www_host_only_cookie(monkeypatch, tmp_path):
    """www.v2ex.com 的 host-only Cookie 也要发送。"""
    monkeypatch.setenv('V2EX_ACCESS_TOKEN', 'fake-token')
    p = _write_cookies_file(
        tmp_path,
        'www.v2ex.com\tFALSE\t/\tTRUE\t0\tPB3_SESSION\tfake-session\n',
    )
    monkeypatch.setenv('COOKIES', p)
    client = V2exClient()
    assert client.session.headers['Cookie'] == 'PB3_SESSION=fake-session'


def test_v2ex_client_dedupes_same_name_across_domains(monkeypatch, tmp_path):
    """同名 Cookie 同时命中 www 与域时，只发送 www 的值。"""
    monkeypatch.setenv('V2EX_ACCESS_TOKEN', 'fake-token')
    p = _write_cookies_file(
        tmp_path,
        '.v2ex.com\tTRUE\t/\tTRUE\t0\tA2\tdomain-value\n'
        'www.v2ex.com\tFALSE\t/\tTRUE\t0\tA2\twww-value\n',
    )
    monkeypatch.setenv('COOKIES', p)
    client = V2exClient()
    assert client.session.headers['Cookie'] == 'A2=www-value'


def test_v2ex_client_missing_token_raises(monkeypatch, tmp_path):
    """缺少 V2EX_ACCESS_TOKEN 应抛出 ValueError。"""
    monkeypatch.delenv('V2EX_ACCESS_TOKEN', raising=False)
    p = _write_cookies_file(
        tmp_path, '.v2ex.com\tTRUE\t/\tTRUE\t0\tfake-cookie-name\tfake-cookie\n'
    )
    monkeypatch.setenv('COOKIES', p)
    with pytest.raises(ValueError, match='V2EX_ACCESS_TOKEN'):
        V2exClient()


def test_v2ex_client_missing_cookie_raises(monkeypatch, tmp_path):
    """缺少 Cookie（无 v2ex.com 域 cookies.txt）应抛出 ValueError。"""
    monkeypatch.setenv('V2EX_ACCESS_TOKEN', 'fake-token')
    p = _write_cookies_file(tmp_path, '.zhihu.com\tTRUE\t/\tTRUE\t0\tname\tvalue\n')
    monkeypatch.setenv('COOKIES', p)
    with pytest.raises(ValueError, match='No cookies found'):
        V2exClient()


def test_fav_list_reuses_provided_client(monkeypatch):
    class FakeResponse:
        status_code = 200
        url = 'https://www.v2ex.com/my/topics'
        text = '<a href="/t/1">topic</a>'

    def fail_client():
        raise AssertionError('V2exClient should not be created')

    monkeypatch.setattr('v2ex.mytopic.V2exClient', fail_client)
    monkeypatch.setattr(
        'v2ex.mytopic.http.get',
        lambda session, url, *, endpoint, **kwargs: FakeResponse(),
    )

    client = SimpleNamespace(session=object())
    assert get_fav_list_topic_id_page(1, client) == [1]


def test_fav_page_limit_stops_pagination(monkeypatch):
    monkeypatch.setattr('v2ex.mytopic.V2EX_MAX_FAV_PAGES', 2)

    with pytest.raises(RuntimeError, match='favorite page limit 2'):
        get_fav_list_topic_id_page(3)


def test_fav_page_detects_signin_redirect(monkeypatch):
    class FakeResponse:
        status_code = 200
        url = 'https://www.v2ex.com/signin?next=/my/topics'
        text = '<html></html>'

    monkeypatch.setattr(
        'v2ex.mytopic.V2exClient',
        lambda: SimpleNamespace(session=object()),
    )
    monkeypatch.setattr(
        'v2ex.mytopic.http.get',
        lambda session, url, *, endpoint, **kwargs: FakeResponse(),
    )

    with pytest.raises(RuntimeError, match='login required'):
        get_fav_html_with_page(1)


def test_fetch_all_replies_reads_pages_until_empty(monkeypatch):
    pages = {1: [{'id': 1}], 2: [{'id': 2}], 3: []}
    calls = []
    clients = []

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    def fake_get(session, url, *, endpoint, **kwargs):
        calls.append((endpoint, kwargs['params']['p']))
        return FakeResponse({'result': pages[kwargs['params']['p']]})

    def fake_client():
        clients.append(1)
        return SimpleNamespace(session=object())

    monkeypatch.setattr('v2ex.replies.V2exClient', fake_client)
    monkeypatch.setattr('v2ex.replies.http.get', fake_get)

    assert fetch_all_replies(1) == 2
    assert len(clients) == 1
    assert calls == [
        ('v2ex.topic.replies.page', 1),
        ('v2ex.topic.replies.page', 2),
        ('v2ex.topic.replies.page', 3),
    ]


def test_fetch_all_replies_stops_at_reply_cap(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200

        def __init__(self, page):
            self.page = page

        def json(self):
            return {'result': [{'id': self.page}]}

    def fake_get(session, url, *, endpoint, **kwargs):
        page = kwargs['params']['p']
        calls.append(page)
        return FakeResponse(page)

    monkeypatch.setattr('v2ex.replies.V2EX_MAX_REPLIES', 2)
    monkeypatch.setattr(
        'v2ex.replies.V2exClient',
        lambda: SimpleNamespace(session=object()),
    )
    monkeypatch.setattr('v2ex.replies.http.get', fake_get)

    assert fetch_all_replies(1) == 2
    assert calls == [1, 2]


def test_fetch_all_replies_stops_at_pagination_pages(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    pages = {
        1: {'result': [{'id': 1}], 'pagination': {'pages': 3}},
        2: {'result': [{'id': 2}], 'pagination': {'pages': 3}},
        3: {'result': [{'id': 3}], 'pagination': {'pages': 3}},
    }

    def fake_get(session, url, *, endpoint, **kwargs):
        page = kwargs['params']['p']
        calls.append(page)
        return FakeResponse(pages[page])

    monkeypatch.setattr(
        'v2ex.replies.V2exClient',
        lambda: SimpleNamespace(session=object()),
    )
    monkeypatch.setattr('v2ex.replies.http.get', fake_get)

    assert fetch_all_replies(1) == 3
    assert calls == [1, 2, 3]


def test_fetch_all_replies_stops_on_repeated_last_page(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    pages = {
        1: {'result': [{'id': 1}]},
        2: {'result': [{'id': 2}]},
        3: {'result': [{'id': 2}]},
    }

    def fake_get(session, url, *, endpoint, **kwargs):
        page = kwargs['params']['p']
        calls.append(page)
        return FakeResponse(pages[page])

    monkeypatch.setattr(
        'v2ex.replies.V2exClient',
        lambda: SimpleNamespace(session=object()),
    )
    monkeypatch.setattr('v2ex.replies.http.get', fake_get)

    # Page 3 repeats page 2, so its rows are not counted a second time.
    assert fetch_all_replies(1) == 2
    assert calls == [1, 2, 3]


def test_replies_page_rejects_unexpected_result(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {'result': {'unexpected': True}}

    monkeypatch.setattr(
        'v2ex.replies.V2exClient',
        lambda: SimpleNamespace(session=object()),
    )
    monkeypatch.setattr(
        'v2ex.replies.http.get',
        lambda session, url, *, endpoint, **kwargs: FakeResponse(),
    )

    with pytest.raises(TypeError, match='unexpected replies result'):
        get_replies_page_info(1, 1)


BALANCE_HTML = """
<html>
<body>
<input class="page_input" type="number" max="156" value="1">
<table class="data">
    <tr>
        <th>时间</th>
        <th>类型</th>
        <th>金额</th>
        <th>余额</th>
        <th>描述</th>
    </tr>
    <tr>
        <td>2026-11-18 10:00:00 +08:00</td>
        <td>发送谢意</td>
        <td>-10.0</td>
        <td>1234.50</td>
        <td>感谢 <a href="/member/alice">alice</a> 的回复
            <span class="fade">›</span>
            <a href="/t/101">Reply topic</a></td>
    </tr>
    <tr>
        <td>2026-11-17 09:00:00 +08:00</td>
        <td>发送谢意</td>
        <td>-15.0</td>
        <td>1244.50</td>
        <td>感谢 <a href="/member/bob">bob</a> 的主题
            <span class="fade">›</span>
            <a href="/t/202#reply3">Topic title</a></td>
    </tr>
    <tr>
        <td>2026-11-16 08:00:00 +08:00</td>
        <td>每日登录奖励</td>
        <td>19.0</td>
        <td>1259.50</td>
        <td>20261116 的每日登录奖励 19 铜币</td>
    </tr>
</table>
</body>
</html>
"""


def test_parse_balance_page_extracts_reply_thanks():
    page = parse_balance_page(BALANCE_HTML)

    assert page.max_page == 156
    assert len(page.transaction_keys) == 3
    assert page.transaction_keys[0].startswith('2026-11-18 10:00:00 +08:00')
    assert len(page.thanks) == 2
    entry = page.thanks[0]
    assert entry.topic_id == 101
    assert entry.content_kind == 'reply'
    assert entry.member == 'alice'
    assert entry.amount == -10.0
    assert entry.balance == 1234.5
    assert entry.topic_title == 'Reply topic'
    assert entry.thanked_at == '2026-11-18 10:00:00 +08:00'


def test_parse_balance_page_extracts_topic_thanks():
    entry = parse_balance_page(BALANCE_HTML).thanks[1]

    assert entry.topic_id == 202
    assert entry.content_kind == 'topic'
    assert entry.member == 'bob'
    assert entry.amount == -15.0
    assert entry.topic_title == 'Topic title'


def test_parse_balance_page_keeps_non_thanks_rows_as_keys_only():
    page = parse_balance_page(
        """
        <table class="data">
            <tr><td>2026-01-01 00:00:00 +08:00</td><td>每日登录奖励</td>
                <td>19.0</td><td>100.0</td><td>login</td></tr>
        </table>
        """
    )

    assert page.thanks == []
    assert len(page.transaction_keys) == 1
    assert page.max_page is None


def test_parse_balance_page_without_table_is_empty():
    page = parse_balance_page('<html><body>maintenance</body></html>')

    assert page.thanks == []
    assert page.transaction_keys == []
    assert page.max_page is None
    assert page.has_table is False


def test_parse_balance_page_requires_the_member_prefix():
    """A description must start with the thanks prefix to be classified."""
    page = parse_balance_page(
        """
        <table class="data">
            <tr><td>2026-11-17 09:00:00 +08:00</td><td>发送谢意</td>
                <td>-15.0</td><td>1244.5</td>
                <td>备注 感谢 <a href="/member/bob">bob</a> 的回复
                    <a href="/t/202">Topic</a></td></tr>
        </table>
        """
    )

    assert page.thanks == []
    assert len(page.transaction_keys) == 1


def test_parse_balance_page_keeps_topic_thanks_when_title_mentions_reply():
    """A topic title containing "的回复" must not flip the kind to reply."""
    page = parse_balance_page(
        """
        <table class="data">
            <tr><td>2026-11-17 09:00:00 +08:00</td><td>发送谢意</td>
                <td>-15.0</td><td>1244.5</td>
                <td>感谢 <a href="/member/bob">bob</a> 的主题
                    <span class="fade">›</span>
                    <a href="/t/202">客服的回复太慢了</a></td></tr>
        </table>
        """
    )

    entry = page.thanks[0]
    assert entry.content_kind == 'topic'
    assert entry.member == 'bob'


def test_parse_balance_page_skips_thanks_without_topic_link():
    page = parse_balance_page(
        """
        <table class="data">
            <tr><td>2026-01-01 00:00:00 +08:00</td><td>发送谢意</td>
                <td>-10.0</td><td>90.0</td><td>感谢 alice 的回复</td></tr>
        </table>
        """
    )

    assert page.thanks == []
    assert len(page.transaction_keys) == 1


def test_balance_page_limit_stops_fetching(monkeypatch):
    monkeypatch.setattr('v2ex.tipped.V2EX_MAX_BALANCE_PAGES', 2)

    with pytest.raises(RuntimeError, match='balance page limit 2'):
        get_balance_page(3)


def test_balance_page_reuses_client_and_records_page(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200
        url = 'https://www.v2ex.com/balance?p=1'
        text = BALANCE_HTML

    def fake_get(session, url, *, endpoint, **kwargs):
        calls.append((endpoint, kwargs['params']['p']))
        return FakeResponse()

    monkeypatch.setattr('v2ex.tipped.http.get', fake_get)

    page = get_balance_page(1, SimpleNamespace(session=object()))

    assert len(page.thanks) == 2
    assert calls == [('v2ex.balance.page', 1)]


def test_topic_info_reuses_the_given_client(monkeypatch):
    """A backfill builds one client, so details must not rebuild it per topic."""
    session = object()
    seen = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {'success': True, 'result': {'id': 1, 'title': 'Topic'}}

    def fake_get(given_session, url, *, endpoint, **kwargs):
        seen.append((given_session, endpoint))
        return FakeResponse()

    monkeypatch.setattr('v2ex.topic.V2exClient', lambda: pytest.fail('rebuilt client'))
    monkeypatch.setattr('v2ex.topic.http.get', fake_get)

    response = get_v2ex_topic_info(1, SimpleNamespace(session=session))

    assert response.result.id == 1
    assert seen == [(session, 'v2ex.topic.detail')]


def test_balance_page_detects_signin_redirect(monkeypatch):
    class FakeResponse:
        status_code = 200
        url = 'https://www.v2ex.com/signin?next=/balance'
        text = '<html><form action="/signin" method="post"></form></html>'

    monkeypatch.setattr(
        'v2ex.tipped.V2exClient',
        lambda: SimpleNamespace(session=object()),
    )
    monkeypatch.setattr(
        'v2ex.tipped.http.get',
        lambda session, url, *, endpoint, **kwargs: FakeResponse(),
    )

    with pytest.raises(RuntimeError, match='login required'):
        get_balance_page(1)
