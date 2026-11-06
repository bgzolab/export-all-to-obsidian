CREATE TABLE IF NOT EXISTS sync_run (
    id INTEGER PRIMARY KEY,
    platform TEXT NOT NULL,
    operation TEXT NOT NULL,
    scope TEXT,
    command TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    error TEXT
);

CREATE TABLE IF NOT EXISTS sync_response (
    id INTEGER PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES sync_run(id),
    endpoint TEXT NOT NULL,
    request TEXT,
    status_code INTEGER,
    fetched_at TEXT NOT NULL,
    body BLOB,
    sha256 TEXT,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_response_run
    ON sync_response(run_id);

CREATE INDEX IF NOT EXISTS idx_sync_response_lookup
    ON sync_response(endpoint, fetched_at);

CREATE INDEX IF NOT EXISTS idx_sync_response_sha256
    ON sync_response(sha256);
