-- NetEase playlists, songs, membership and recent-play history.
-- Play ranks are intentionally not projected; their raw responses stay in
-- sync_response for read-only replay.

CREATE TABLE netease_playlist (
    playlist_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    cover_img_url TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    creator_id INTEGER NOT NULL DEFAULT 0,
    creator_json TEXT CHECK (json_valid(creator_json)),
    track_count INTEGER NOT NULL DEFAULT 0,
    play_count INTEGER NOT NULL DEFAULT 0,
    subscribed_count INTEGER NOT NULL DEFAULT 0,
    create_time INTEGER NOT NULL DEFAULT 0,
    update_time INTEGER NOT NULL DEFAULT 0,
    track_update_time INTEGER NOT NULL DEFAULT 0,
    special_type INTEGER NOT NULL DEFAULT 0,
    subscribed INTEGER NOT NULL DEFAULT 0 CHECK (subscribed IN (0, 1)),
    privacy INTEGER NOT NULL DEFAULT 0,
    ordered INTEGER NOT NULL DEFAULT 0 CHECK (ordered IN (0, 1)),
    tags_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tags_json)),
    detail_response_id INTEGER REFERENCES sync_response(id),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

CREATE INDEX idx_netease_playlist_creator
    ON netease_playlist(creator_id);

CREATE INDEX idx_netease_playlist_special_type
    ON netease_playlist(special_type);

CREATE TABLE netease_song (
    song_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    artists_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(artists_json)),
    album_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(album_json)),
    duration INTEGER NOT NULL DEFAULT 0,
    publish_time INTEGER NOT NULL DEFAULT 0,
    fee INTEGER NOT NULL DEFAULT 0,
    mv INTEGER NOT NULL DEFAULT 0,
    alias_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(alias_json)),
    trans_names_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(trans_names_json)),
    pop INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 0,
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE netease_playlist_song (
    playlist_id INTEGER NOT NULL REFERENCES netease_playlist(playlist_id),
    song_id INTEGER NOT NULL REFERENCES netease_song(song_id),
    position INTEGER NOT NULL DEFAULT 0,
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL,
    PRIMARY KEY (playlist_id, song_id)
) STRICT;

CREATE INDEX idx_netease_playlist_song_song
    ON netease_playlist_song(song_id);

-- History is an independent log: it keeps a song snapshot instead of a
-- netease_song foreign key so play records never pollute the song library.
CREATE TABLE netease_play_record (
    song_id INTEGER NOT NULL,
    play_time INTEGER NOT NULL,
    resource_type TEXT NOT NULL DEFAULT 'SONG',
    banned INTEGER NOT NULL DEFAULT 0 CHECK (banned IN (0, 1)),
    device_json TEXT CHECK (json_valid(device_json)),
    song_json TEXT NOT NULL CHECK (json_valid(song_json)),
    response_id INTEGER NOT NULL REFERENCES sync_response(id),
    db_created_at TEXT NOT NULL,
    db_updated_at TEXT NOT NULL,
    PRIMARY KEY (song_id, play_time)
) STRICT;

CREATE INDEX idx_netease_play_record_play_time
    ON netease_play_record(play_time);
