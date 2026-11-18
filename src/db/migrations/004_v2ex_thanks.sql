-- V2EX sent-thanks transactions from the balance page.
-- This is a fourth V2EX table on purpose: tipping is an independent source
-- relation, and the transaction fields drive page-level incremental pruning.
-- No foreign key to v2ex_topic: thanks rows arrive before topic details and
-- some topics may already be deleted.
CREATE TABLE v2ex_thanks (
    thanked_at TEXT NOT NULL,
    topic_id INTEGER NOT NULL,
    content_kind TEXT NOT NULL CHECK (content_kind IN ('reply', 'topic')),
    member TEXT NOT NULL DEFAULT '',
    amount REAL NOT NULL,
    balance REAL NOT NULL,
    topic_title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL,
    PRIMARY KEY (thanked_at, topic_id, content_kind, member, balance)
) STRICT;

CREATE INDEX idx_v2ex_thanks_topic
    ON v2ex_thanks(topic_id);
