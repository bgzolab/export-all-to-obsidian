"""
上游定义： https://github.com/bangumi/server

@Author : bGZo
@Date : 2025-07-31
@Links : https://github.com/bGZo
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


# https://github.com/bangumi/server/blob/fb44e70f9fac931fc29964cab9c5b5aec41433b0/web/res/image.go#L47
@dataclass
class SubjectImages:
    small: str
    grid: str
    large: str
    medium: str
    common: str


@dataclass
class PersonImages:
    small: str
    grid: str
    large: str
    medium: str
    common: str


# https://github.com/bangumi/server/blob/fb44e70f9fac931fc29964cab9c5b5aec41433b0/web/res/subject.go#L38-L42
@dataclass
class SubjectTag:
    # 根据实际结构补充字段
    name: str
    count: int
    total_count: int


# https://github.com/bangumi/server/blob/fb44e70f9fac931fc29964cab9c5b5aec41433b0/web/res/subject.go#L66C1-L81C2
@dataclass
class SlimSubjectV0:
    date: str | None
    images: SubjectImages  # 修正为 images
    name: str
    name_cn: str
    short_summary: str
    tags: list[SubjectTag]
    score: float
    type: int
    id: int
    eps: int
    volumes: int
    collection_total: int
    rank: int


# https://github.com/bangumi/server/blob/fb44e70f9fac931fc29964cab9c5b5aec41433b0/internal/collections/domain/collection/model.go#L34
@dataclass
class UserSubjectCollection:
    id: int
    updated_at: datetime
    comment: str | None
    tags: list[str]
    vol_status: int
    ep_status: int
    subject_id: int
    subject_type: int
    rate: int
    type: int
    private: bool
    subject: SlimSubjectV0


@dataclass
class Rating:
    rank: int | None = None
    total: int | None = None
    count: int | None = None
    score: float | None = None


@dataclass
class SubjectCollectionStat:
    wish: int = 0
    collect: int = 0
    doing: int = 0
    on_hold: int = 0
    dropped: int = 0
    total: int = 0


@dataclass
class SubjectV0:
    date: str | None
    platform: str | None
    images: SubjectImages
    summary: str
    name: str
    name_cn: str
    tags: list[SubjectTag]
    infobox: list[Any] | None
    rating: Rating | None
    total_episodes: int
    collection: SubjectCollectionStat | None
    id: int
    eps: int
    meta_tags: list[str]
    volumes: int
    series: bool
    locked: bool
    nsfw: bool
    type_id: int
    redirect: int | None


@dataclass
class Actor:
    id: int
    name: str
    images: PersonImages | None = None
    short_summary: str = ''
    career: list[str] = None
    type: int = 0
    locked: bool = False


@dataclass
class SubjectRelatedCharacter:
    images: PersonImages
    name: str
    relation: str
    actors: list[Actor]
    type: int
    id: int


# V0wiki 仅为 infobox 的类型别名，等价于 List[Any]
V0wiki = list[Any]
