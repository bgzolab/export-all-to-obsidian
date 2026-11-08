"""Twitter liked tweets to projection tables."""

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
from twitter.entity import LikesPage

ENDPOINT = 'twitter.likes.page'

DELETE_ORDER = ('twitter_tweet',)


def rebuild(connection: sqlite3.Connection) -> RebuildResult:
    """Rebuild liked tweets from GraphQL responses."""
    now = raw.utc_now()
    reset_tables(connection, DELETE_ORDER)
    result = RebuildResult()

    for response, payload in iter_json_responses(
        connection,
        ENDPOINT,
        result=result,
    ):
        try:
            result.rows += apply_handler(
                ENDPOINT,
                response,
                _upsert_tweets,
                connection,
                payload,
                response['id'],
                now,
            )
        except SkipResponse as exc:
            skip_handler_response(result, ENDPOINT, response, str(exc))

    return result


def _upsert_tweets(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    response_id: int,
    now: str,
) -> int:
    if not isinstance(payload, dict):
        raise TypeError('invalid likes payload')
    if 'data' not in payload:
        raise SkipResponse('missing data')
    data = payload['data']
    if data is None or data == {}:
        raise SkipResponse('empty likes data')
    if not isinstance(data, dict):
        raise TypeError('invalid likes data')
    page = LikesPage.from_dict(data)
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
    return rows
