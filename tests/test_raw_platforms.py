from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
import requests


class FakeResponse:
    def __init__(self, json_data=None, text='', status_code=200):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.reason = 'Error'
        self.headers = {'Content-Type': 'application/json'}
        if json_data is not None:
            self.content = json.dumps(json_data).encode()
        else:
            self.content = text.encode()

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'HTTP {self.status_code}')


class FakeSession:
    def __init__(self, response):
        self.headers = {}
        self.response = response

    def request(self, method, url, **kwargs):
        return self.response


class FakeClient:
    def __init__(self, response, api_endpoints=None):
        self.session = FakeSession(response)
        self.api_endpoints = api_endpoints
        self.user_id = '42'


def _patch_get(monkeypatch, module_name, response, endpoints):
    def fake_get(session, url, *, endpoint, **kwargs):
        endpoints.append(endpoint)
        return response

    monkeypatch.setattr(f'{module_name}.http.get', fake_get)


def test_zhihu_collection_endpoint(monkeypatch):
    from zhihu.collection import get_collection_page

    endpoints = []
    client = FakeClient(FakeResponse({'paging': {}, 'data': []}))
    monkeypatch.setattr('zhihu.collection.ZhihuClient', lambda: client)
    _patch_get(monkeypatch, 'zhihu.collection', client.session.response, endpoints)

    assert get_collection_page('1', 0, 20) is not None
    assert endpoints == ['zhihu.collection.page']


def test_bilibili_favlist_endpoint(monkeypatch):
    from bilibili.favlist import get_bilibili_favlistd

    endpoints = []
    client = FakeClient(
        FakeResponse(
            {
                'code': 0,
                'message': '',
                'ttl': 1,
                'data': {'info': None, 'medias': [], 'has_more': False, 'ttl': 1},
            }
        )
    )
    monkeypatch.setattr('bilibili.favlist.BilibiliClient', lambda: client)
    _patch_get(monkeypatch, 'bilibili.favlist', client.session.response, endpoints)

    assert get_bilibili_favlistd(1, 1, 20).code == 0
    assert endpoints == ['bilibili.favlist.page']


def test_weibo_like_endpoint(monkeypatch):
    from weibo.like import get_weibo_like_list

    endpoints = []
    client = FakeClient(FakeResponse({'ok': 1, 'data': {'list': []}}))
    monkeypatch.setattr('weibo.like.WeiboClient', lambda: client)
    _patch_get(monkeypatch, 'weibo.like', client.session.response, endpoints)

    assert get_weibo_like_list(1, 1).ok == 1
    assert endpoints == ['weibo.likes.page']


def test_weibo_longtext_endpoint(monkeypatch):
    from weibo.post import get_weibo_longtext_by_id

    endpoints = []
    client = FakeClient(FakeResponse({'data': {'longTextContent': 'long'}}))
    monkeypatch.setattr('weibo.post.WeiboClient', lambda: client)
    _patch_get(monkeypatch, 'weibo.post', client.session.response, endpoints)

    assert get_weibo_longtext_by_id('1') == 'long'
    assert endpoints == ['weibo.longtext']


def test_v2ex_fav_endpoint(monkeypatch):
    from v2ex.mytopic import get_fav_html_with_page

    endpoints = []
    client = FakeClient(FakeResponse(text='<html></html>'))
    monkeypatch.setattr('v2ex.mytopic.V2exClient', lambda: client)
    _patch_get(monkeypatch, 'v2ex.mytopic', client.session.response, endpoints)

    assert get_fav_html_with_page(1) == '<html></html>'
    assert endpoints == ['v2ex.fav.page']


def test_v2ex_non_200_raises(monkeypatch):
    from v2ex.mytopic import get_fav_html_with_page

    client = FakeClient(FakeResponse(text='error', status_code=503))
    monkeypatch.setattr('v2ex.mytopic.V2exClient', lambda: client)
    monkeypatch.setattr(
        'v2ex.mytopic.http.get',
        lambda session, url, *, endpoint, **kwargs: client.session.response,
    )

    with pytest.raises(requests.HTTPError):
        get_fav_html_with_page(1)


def test_v2ex_topic_endpoint(monkeypatch):
    from v2ex.topic import get_v2ex_topic_info

    endpoints = []
    client = FakeClient(
        FakeResponse({'success': True, 'message': '', 'result': {'id': 1}})
    )
    monkeypatch.setattr('v2ex.topic.V2exClient', lambda: client)
    _patch_get(monkeypatch, 'v2ex.topic', client.session.response, endpoints)

    assert get_v2ex_topic_info(1).result.id == 1
    assert endpoints == ['v2ex.topic.detail']


def test_bangumi_collection_endpoint(monkeypatch):
    from bangumi.collection import get_all_collections_by_pages

    endpoints = []
    client = FakeClient(FakeResponse({'data': []}))
    monkeypatch.setattr('bangumi.collection.BangumiClient', lambda: client)
    _patch_get(monkeypatch, 'bangumi.collection', client.session.response, endpoints)

    assert get_all_collections_by_pages('user', 1, 1) == []
    assert endpoints == ['bangumi.collections.page']


def test_bangumi_subject_endpoint(monkeypatch):
    from bangumi.subject import get_subject_info

    endpoints = []
    client = FakeClient(
        FakeResponse(
            {
                'id': 1,
                'name': 'subject',
                'images': None,
                'tags': [],
                'rating': None,
                'collection': None,
            }
        )
    )
    monkeypatch.setattr('bangumi.subject.BangumiClient', lambda: client)
    _patch_get(monkeypatch, 'bangumi.subject', client.session.response, endpoints)

    assert get_subject_info(1).name == 'subject'
    assert endpoints == ['bangumi.subject.detail']


def test_bangumi_character_endpoint(monkeypatch):
    from bangumi.subject import get_subject_character

    endpoints = []
    client = FakeClient(FakeResponse([]))
    monkeypatch.setattr('bangumi.subject.BangumiClient', lambda: client)
    _patch_get(monkeypatch, 'bangumi.subject', client.session.response, endpoints)

    assert get_subject_character(1) == []
    assert endpoints == ['bangumi.subject.characters']


def test_qireader_readlater_endpoint(monkeypatch):
    from qireader.readlatter import get_list_from_read_latter

    endpoints = []
    client = FakeClient(
        FakeResponse({'result': {'id': 'tag', 'entries': [], 'hasMore': False}}),
        SimpleNamespace(READ_LATER='https://qireader.example/'),
    )
    monkeypatch.setattr('qireader.readlatter.QiReaderClient', lambda: client)
    _patch_get(monkeypatch, 'qireader.readlatter', client.session.response, endpoints)

    assert get_list_from_read_latter('tag', None) == []
    assert endpoints == ['qireader.readlater.page']


def test_qireader_article_endpoint(monkeypatch):
    from qireader.getext import get_html_text_from_url

    endpoints = []
    client = FakeClient(
        FakeResponse({'content': '<p>text</p>'}),
        SimpleNamespace(FULL_TEXT='https://qireader.example/fulltext'),
    )
    monkeypatch.setattr('qireader.getext.QiReaderClient', lambda: client)
    _patch_get(monkeypatch, 'qireader.getext', client.session.response, endpoints)

    assert get_html_text_from_url('https://example.com') == '<p>text</p>'
    assert endpoints == ['qireader.article']


def test_cnblog_bookmarks_endpoint(monkeypatch):
    from cnblog.bookmark import get_bookmark_list

    endpoints = []
    client = FakeClient(
        FakeResponse([]),
        SimpleNamespace(BOOKMARK='https://cnblog.example/bookmarks'),
    )
    monkeypatch.setattr('cnblog.bookmark.CnblogClient', lambda: client)
    _patch_get(monkeypatch, 'cnblog.bookmark', client.session.response, endpoints)

    assert get_bookmark_list(1, 100) == []
    assert endpoints == ['cnblog.bookmarks.page']


def test_cnblog_post_endpoint(monkeypatch):
    from cnblog.blog_post import get_cnblog_post_body_by_url

    requests = []
    client = FakeClient(FakeResponse(text='<p>post</p>'))
    monkeypatch.setattr('cnblog.blog_post.CnblogClient', lambda: client)

    def fake_get(session, url, *, endpoint, **kwargs):
        requests.append((endpoint, url))
        return client.session.response

    monkeypatch.setattr('cnblog.blog_post.http.get', fake_get)

    assert (
        get_cnblog_post_body_by_url('https://cnblogs.com/x/p/1.html') == '<p>post</p>'
    )
    assert (
        get_cnblog_post_body_by_url('https://cnblogs.com/x/p/2/how-to-fetch')
        == '<p>post</p>'
    )
    assert get_cnblog_post_body_by_url('https://cnblogs.com/x/p/slug-only.html') == ''
    assert requests == [
        ('cnblog.post.body', 'https://api.cnblogs.com/api/blogposts/1/body'),
        ('cnblog.post.body', 'https://api.cnblogs.com/api/blogposts/2/body'),
    ]


def test_cnblog_user_endpoint(monkeypatch):
    from cnblog.user import get_current_user_info

    endpoints = []
    client = FakeClient(FakeResponse({'name': 'user'}))
    monkeypatch.setattr('cnblog.user.CnblogClient', lambda: client)
    _patch_get(monkeypatch, 'cnblog.user', client.session.response, endpoints)

    assert get_current_user_info()['name'] == 'user'
    assert endpoints == ['cnblog.user.current']


def test_twitter_likes_endpoint(monkeypatch):
    from twitter.like import get_twitter_like_list

    endpoints = []

    class FakeTwitterClient:
        user_id = '42'

        def __init__(self):
            self.session = FakeSession(FakeResponse({'data': {'user': {'result': {}}}}))

    client = FakeTwitterClient()

    def fake_get(session, url, *, endpoint, **kwargs):
        endpoints.append(endpoint)
        return client.session.response

    monkeypatch.setattr('twitter.like.http.get', fake_get)

    page = get_twitter_like_list(client)

    assert page is not None
    assert endpoints == ['twitter.likes.page']


def test_zhihu_non_200_raises(monkeypatch):
    from zhihu.collection import get_collection_page

    client = FakeClient(FakeResponse({}, status_code=500))
    monkeypatch.setattr('zhihu.collection.ZhihuClient', lambda: client)
    monkeypatch.setattr(
        'zhihu.collection.http.get',
        lambda session, url, *, endpoint, **kwargs: client.session.response,
    )

    with pytest.raises(requests.HTTPError):
        get_collection_page('1', 0, 1)


def test_qireader_non_200_raises(monkeypatch):
    from qireader.readlatter import get_list_from_read_latter

    client = FakeClient(
        FakeResponse({}, status_code=429),
        SimpleNamespace(READ_LATER='https://qireader.example/'),
    )
    monkeypatch.setattr('qireader.readlatter.QiReaderClient', lambda: client)
    monkeypatch.setattr(
        'qireader.readlatter.http.get',
        lambda session, url, *, endpoint, **kwargs: client.session.response,
    )

    with pytest.raises(requests.HTTPError):
        get_list_from_read_latter('tag', None)


def test_bangumi_non_200_raises(monkeypatch):
    from bangumi.collection import get_all_collections_by_pages

    client = FakeClient(FakeResponse({}, status_code=503))
    monkeypatch.setattr('bangumi.collection.BangumiClient', lambda: client)
    monkeypatch.setattr(
        'bangumi.collection.http.get',
        lambda session, url, *, endpoint, **kwargs: client.session.response,
    )

    with pytest.raises(requests.HTTPError):
        get_all_collections_by_pages('user', 1, 1)


def test_bilibili_error_code_raises(monkeypatch):
    from bilibili.favlist import get_bilibili_favlistd

    client = FakeClient(
        FakeResponse({'code': -101, 'message': 'not logged in', 'ttl': 1, 'data': None})
    )
    monkeypatch.setattr('bilibili.favlist.BilibiliClient', lambda: client)
    monkeypatch.setattr(
        'bilibili.favlist.http.get',
        lambda session, url, *, endpoint, **kwargs: client.session.response,
    )

    with pytest.raises(RuntimeError, match='code=-101'):
        get_bilibili_favlistd(1, 1, 20)
