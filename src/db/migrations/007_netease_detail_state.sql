-- NetEase: keep the metadata of the last successful playlist detail.
-- A list page may be newer than a failed detail refetch; pruning must compare
-- against the detail, otherwise stale members would look pruned forever.

ALTER TABLE netease_playlist
    ADD COLUMN detail_track_count INTEGER;

ALTER TABLE netease_playlist
    ADD COLUMN detail_track_update_time INTEGER;
