"""Twitter liked and bookmarked tweets to projection tables."""

from __future__ import annotations

import sqlite3
from typing import Any

from db import raw
from db.projections._upsert import (
    RebuildResult,
    SkipResponse,
    apply_handler,
    iter_json_responses,
    json_dumps,
    reset_tables,
    skip_handler_response,
    upsert,
)
from twitter.entity import BookmarksPage, LikesPage

LIKES_ENDPOINT = 'twitter.likes.page'
BOOKMARKS_ENDPOINT = 'twitter.bookmarks.page'

# Relations reference twitter_tweet, so they must be deleted first.
DELETE_ORDER = ('twitter_like', 'twitter_bookmark', 'twitter_tweet')


def known_tweet_ids(
    connection: sqlite3.Connection,
    tweet_ids: list[str],
) -> set[str]:
    """Return liked tweet ids already present in the projection."""
    return _known_ids(connection, 'twitter_like', tweet_ids)


def known_bookmark_ids(
    connection: sqlite3.Connection,
    tweet_ids: list[str],
) -> set[str]:
    """Return bookmarked tweet ids already present in the projection."""
    return _known_ids(connection, 'twitter_bookmark', tweet_ids)


def rebuild(connection: sqlite3.Connection) -> RebuildResult:
    """Rebuild tweets from likes first, then bookmarks.

    The likes pass creates or refreshes the shared tweet rows; the bookmarks
    pass can only add/refresh entities and relations. The response_id guard in
    ``upsert`` keeps an older bookmark response from overwriting newer likes.
    """
    now = raw.utc_now()
    reset_tables(connection, DELETE_ORDER)
    result = RebuildResult()

    handlers = (
        (LIKES_ENDPOINT, _upsert_likes),
        (BOOKMARKS_ENDPOINT, _upsert_bookmarks),
    )
    for endpoint, handler in handlers:
        for response, payload in iter_json_responses(
            connection,
            endpoint,
            result=result,
        ):
            try:
                result.rows += apply_handler(
                    endpoint,
                    response,
                    handler,
                    connection,
                    payload,
                    response['id'],
                    now,
                )
            except SkipResponse as exc:
                skip_handler_response(result, endpoint, response, str(exc))

    return result


def _upsert_likes(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response_id: int,
    now: str,
) -> int:
    page = _parse_page(payload, LikesPage, 'likes')
    return _upsert_page(connection, page, response_id, now, 'twitter_like')


def _upsert_bookmarks(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response_id: int,
    now: str,
) -> int:
    page = _parse_page(payload, BookmarksPage, 'bookmarks')
    return _upsert_page(connection, page, response_id, now, 'twitter_bookmark')


def _parse_page(
    payload: dict[str, Any],
    page_type: type[LikesPage | BookmarksPage],
    source: str,
) -> LikesPage | BookmarksPage:
    """Validate the response envelope and parse one timeline page.

    Missing/empty data is a business-level no-data response and is skipped;
    malformed top-level types are fatal so the platform rebuild rolls back.
    """
    if not isinstance(payload, dict):
        raise TypeError(f'invalid {source} payload')
    if 'data' not in payload:
        raise SkipResponse(f'missing {source} data')
    data = payload['data']
    if data is None or data == {}:
        raise SkipResponse(f'empty {source} data')
    if not isinstance(data, dict):
        raise TypeError(f'invalid {source} data')
    return page_type.from_dict(data)


def _upsert_page(
    connection: sqlite3.Connection,
    page: LikesPage | BookmarksPage,
    response_id: int,
    now: str,
    relation_table: str,
) -> int:
    """Write each tweet once and record its source relation separately."""
    rows = 0
    for tweet in page.tweets:
        rows += upsert(
            connection,
            'twitter_tweet',
            {'tweet_id': tweet.id_str},
            {
                'created_at': tweet.created_at,
                'full_text': tweet.full_text,
                'author_json': json_dumps(
                    {
                        'screen_name': tweet.author.screen_name,
                        'name': tweet.author.name,
                        'id': tweet.author.id,
                    },
                ),
                'favorite_count': tweet.favorite_count,
                'retweet_count': tweet.retweet_count,
                'reply_count': tweet.reply_count,
                'view_count': tweet.view_count,
            },
            response_id,
            now,
        )
        rows += upsert(
            connection,
            relation_table,
            {'tweet_id': tweet.id_str},
            {},
            response_id,
            now,
        )
    return rows


def _known_ids(
    connection: sqlite3.Connection,
    table: str,
    tweet_ids: list[str],
) -> set[str]:
    if not tweet_ids:
        return set()
    placeholders = ','.join('?' for _ in tweet_ids)
    rows = connection.execute(
        f'SELECT tweet_id FROM {table} WHERE tweet_id IN ({placeholders})',
        tweet_ids,
    )
    return {row['tweet_id'] for row in rows}
