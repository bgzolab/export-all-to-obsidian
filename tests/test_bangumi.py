"""
@Author : bGZo
@Date : 2025-08-19
@Links : https://github.com/bGZo
"""

import os
from types import SimpleNamespace

import pytest

from bangumi.bangumi import get_subject_character, get_subject_info
from bangumi.collection import _dict_to_slim_subject_v0, _dict_to_subject_tag_list
from bangumi.entity import SubjectTag

requires_bangumi_token = pytest.mark.skipif(
    not os.getenv('BGM_ACCESS_TOKEN'),
    reason='requires BGM_ACCESS_TOKEN',
)


@requires_bangumi_token
def test_subject_get():
    res = get_subject_info(1)
    print(res)


@requires_bangumi_token
def test_subject_character():
    res = get_subject_character(2)
    print(res)


def test_subject_tag_accepts_total_count():
    """API 实际返回 total_count 字段，SubjectTag 必须能接受该参数。"""
    tag = SubjectTag(name='科幻', count=10, total_count=100)
    assert tag.name == '科幻'
    assert tag.count == 10
    assert tag.total_count == 100


def test_dict_to_subject_tag_list_with_total_count():
    """从 API 返回的字典构造 tag 列表，字段名应为 total_count。"""
    lst = [
        {'name': '科幻', 'count': 10, 'total_count': 100},
        {'name': '动画', 'count': 5, 'total_count': 50},
    ]
    tags = _dict_to_subject_tag_list(lst)
    assert len(tags) == 2
    assert tags[0].name == '科幻'
    assert tags[0].total_count == 100
    assert tags[1].total_count == 50


def test_db_only_records_subject_characters(monkeypatch):
    from bangumi import exporter
    from db.connection import connect

    connection = connect(':memory:')
    calls = []
    monkeypatch.setattr('bangumi.exporter.is_db_only', lambda: True)
    monkeypatch.setattr('bangumi.exporter.get_database', lambda: connection)
    monkeypatch.setattr(
        'bangumi.exporter.get_subject_info',
        lambda subject_id: SimpleNamespace(),
    )
    monkeypatch.setattr(
        'bangumi.exporter.get_output_character_string',
        lambda subject_id: calls.append(subject_id) or '',
    )

    assert exporter.write_subject_markdown(1, 3, '', '', False) == (True, '', '')
    assert calls == [1]
    connection.close()


def test_export_stops_after_short_page(monkeypatch):
    """末页不足 limit 时停止翻页，避免请求超过 API 的 offset 上限。"""
    from bangumi import exporter

    offsets = []

    def fake_pages(username, subject_type, collection_type, limit=30, offset=0):
        offsets.append(offset)
        if offset == 0:
            return [SimpleNamespace(subject_id=1)]
        raise AssertionError(f'unexpected page request: offset={offset}')

    class FakeIndex:
        def add(self, line):
            pass

        def flush(self, module):
            pass

    monkeypatch.setattr(
        exporter,
        'BangumiClient',
        lambda: SimpleNamespace(get_user=lambda: {'username': 'u'}),
    )
    monkeypatch.setattr(exporter, 'get_all_collections_by_pages', fake_pages)
    monkeypatch.setattr(
        exporter,
        'write_subject_markdown',
        lambda **kwargs: (True, 'file', 'title'),
    )
    monkeypatch.setattr(exporter, 'is_db_only', lambda: False)

    exporter.export(2, 1, '', '', FakeIndex(), force=False)

    assert offsets == [0]


def test_dict_to_slim_subject_v0_with_api_tags():
    """端到端验证：从 API 返回的 subject 字典构造 SlimSubjectV0 不报错。"""
    d = {
        'date': '2025-01-01',
        'images': {
            'small': 's',
            'grid': 'g',
            'large': 'l',
            'medium': 'm',
            'common': 'c',
        },
        'name': 'test',
        'name_cn': '测试',
        'short_summary': 'summary',
        'tags': [{'name': 'tag1', 'count': 1, 'total_count': 10}],
        'score': 8.0,
        'type': 2,
        'id': 1,
        'eps': 12,
        'volumes': 1,
        'collection_total': 100,
        'rank': 1,
    }
    subject = _dict_to_slim_subject_v0(d)
    assert subject.name == 'test'
    assert subject.tags[0].total_count == 10
