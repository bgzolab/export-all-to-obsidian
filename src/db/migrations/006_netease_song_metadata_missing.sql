-- NetEase: remember songs that a successful batch reported as unavailable,
-- so a playlist with delisted tracks is not refetched on every run.

ALTER TABLE netease_song
    ADD COLUMN metadata_missing INTEGER NOT NULL DEFAULT 0
    CHECK (metadata_missing IN (0, 1));
