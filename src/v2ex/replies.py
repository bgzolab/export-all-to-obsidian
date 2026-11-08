"""Fetch and record all reply pages for a V2EX topic."""

from __future__ import annotations

from typing import Any

from export_runtime import http
from v2ex.api_endpoints import V2EX_API_REPLIES
from v2ex.cilent import V2exClient


def get_replies_page(topic_id: int, page: int) -> list[dict[str, Any]]:
    """Fetch one reply page from the V2 API."""
    client = V2exClient()
    response = http.get(
        client.session,
        V2EX_API_REPLIES.format(topic_id=topic_id),
        endpoint='v2ex.topic.replies.page',
        params={'p': page},
    )
    if response.status_code != 200:
        response.raise_for_status()
    payload = response.json()
    result = payload.get('result') if isinstance(payload, dict) else None
    return result if isinstance(result, list) else []


def fetch_all_replies(topic_id: int) -> int:
    """Fetch every reply page so the raw layer has the full thread."""
    page = 1
    total = 0
    while True:
        replies = get_replies_page(topic_id, page)
        if not replies:
            return total
        total += len(replies)
        page += 1
