"""Fetch and record all reply pages for a V2EX topic."""

from __future__ import annotations

from typing import Any

from export_runtime import http
from v2ex.api_endpoints import V2EX_API_REPLIES
from v2ex.cilent import V2exClient

# 每个主题只保留前 200 条回复；超过部分不再抓取。按 20 条/页约 10 页，
# 也天然防止接口忽略 p 参数时无限循环。
V2EX_MAX_REPLIES = 200


def get_replies_page_info(
    topic_id: int,
    page: int,
    client: V2exClient | None = None,
) -> tuple[list[dict[str, Any]], int | None]:
    """Fetch one reply page plus its total page count when the API reports it.

    V2EX returns the last page again for out-of-range ``p`` instead of an
    empty list, so callers must stop using ``pages`` rather than waiting for
    an empty page.
    """
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
        return [], _reply_pages(payload)
    if not isinstance(result, list):
        raise TypeError('unexpected replies result')
    return result, _reply_pages(payload)


def get_replies_page(
    topic_id: int,
    page: int,
    client: V2exClient | None = None,
) -> list[dict[str, Any]]:
    """Fetch one reply page, keeping the historical list-only return value."""
    replies, _pages = get_replies_page_info(topic_id, page, client)
    return replies


def _reply_pages(payload: dict[str, Any]) -> int | None:
    """Read ``pagination.pages``; older responses may omit the block."""
    pagination = payload.get('pagination')
    if not isinstance(pagination, dict):
        return None
    pages = pagination.get('pages')
    if isinstance(pages, int) and pages >= 0:
        return pages
    return None


def fetch_all_replies(topic_id: int, client: V2exClient | None = None) -> int:
    """Fetch reply pages until the thread ends or the 200-reply cap is reached."""
    client = client or V2exClient()
    page = 1
    total = 0
    previous_ids: list[Any] | None = None
    while total < V2EX_MAX_REPLIES:
        replies, pages = get_replies_page_info(topic_id, page, client)
        if not replies:
            break
        current_ids = [reply.get('id') for reply in replies]
        # Older payloads have no pagination block; the repeated last page is
        # then the only reliable end marker.
        if previous_ids is not None and current_ids == previous_ids:
            break
        previous_ids = current_ids
        total += len(replies)
        if pages is not None and page >= pages:
            break
        page += 1
    return total
