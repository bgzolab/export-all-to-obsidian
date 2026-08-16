#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
@Author : bGZo
@Date : 2025-08-19
@Links : https://github.com/bGZo
"""
from bangumi.bangumi import get_subject_info, get_subject_character
from bangumi.collection import _dict_to_subject_tag_list, _dict_to_slim_subject_v0
from bangumi.entity import SubjectTag

def test_subject_get():
    res = get_subject_info(1)
    print(res)

def test_subject_character():
    res = get_subject_character(2)
    print(res)

def test_subject_tag_accepts_total_count():
    """API 实际返回 total_count 字段，SubjectTag 必须能接受该参数。"""
    tag = SubjectTag(name="科幻", count=10, total_count=100)
    assert tag.name == "科幻"
    assert tag.count == 10
    assert tag.total_count == 100

def test_dict_to_subject_tag_list_with_total_count():
    """从 API 返回的字典构造 tag 列表，字段名应为 total_count。"""
    lst = [
        {"name": "科幻", "count": 10, "total_count": 100},
        {"name": "动画", "count": 5, "total_count": 50},
    ]
    tags = _dict_to_subject_tag_list(lst)
    assert len(tags) == 2
    assert tags[0].name == "科幻"
    assert tags[0].total_count == 100
    assert tags[1].total_count == 50

def test_dict_to_slim_subject_v0_with_api_tags():
    """端到端验证：从 API 返回的 subject 字典构造 SlimSubjectV0 不报错。"""
    d = {
        "date": "2025-01-01",
        "images": {
            "small": "s", "grid": "g", "large": "l", "medium": "m", "common": "c"
        },
        "name": "test",
        "name_cn": "测试",
        "short_summary": "summary",
        "tags": [{"name": "tag1", "count": 1, "total_count": 10}],
        "score": 8.0,
        "type": 2,
        "id": 1,
        "eps": 12,
        "volumes": 1,
        "collection_total": 100,
        "rank": 1,
    }
    subject = _dict_to_slim_subject_v0(d)
    assert subject.name == "test"
    assert subject.tags[0].total_count == 10
