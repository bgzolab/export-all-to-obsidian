-- Twitter source relations.
-- twitter_tweet is the shared tweet entity; these tables record which source
-- observed a tweet so like/bookmark pruning and provenance stay independent.
CREATE TABLE twitter_like (
    tweet_id TEXT PRIMARY KEY REFERENCES twitter_tweet(tweet_id),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE twitter_bookmark (
    tweet_id TEXT PRIMARY KEY REFERENCES twitter_tweet(tweet_id),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

-- Before this migration twitter_tweet was written only by the likes endpoint,
-- so every existing row is a like. Future writers must revisit this assumption.
INSERT INTO twitter_like (tweet_id, response_id, db_created_at, db_updated_at)
SELECT tweet_id, response_id, db_created_at, db_updated_at
FROM twitter_tweet;
