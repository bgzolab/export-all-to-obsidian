"""Fetch and record all reply pages for a V2EX topic."""

from __future__ import annotations

from typing import Any

from export_runtime import http
from v2ex.api_endpoints import V2EX_API_REPLIES
from v2ex.cilent import V2exClient

# 每个主题只保留前 200 条回复；超过部分不再抓取。按 20 条/页约 10 页，
# 也天然防止接口忽略 p 参数时无限循环。
V2EX_MAX_REPLIES = 200


def get_replies_page(
    topic_id: int,
    page: int,
    client: V2exClient | None = None,
) -> list[dict[str, Any]]:
    """Fetch one reply page from the V2 API."""
    client = client or V2exClient()
    response = http.get(
        client.session,
        V2EX_API_REPLIES.format(topic_id=topic_id),
        endpoint='v2ex.topic.replies.page',
        params={'p': page},
    )
    if response.status_code != 200:
        response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError('unexpected replies payload')
    result = payload.get('result')
    if result is None:
        return []
    if not isinstance(result, list):
        raise TypeError('unexpected replies result')
    return result


def fetch_all_replies(topic_id: int, client: V2exClient | None = None) -> int:
    """Fetch reply pages until the thread ends or the 200-reply cap is reached."""
    client = client or V2exClient()
    page = 1
    total = 0
    while total < V2EX_MAX_REPLIES:
        replies = get_replies_page(topic_id, page, client)
        if not replies:
            break
        total += len(replies)
        page += 1
    return total
