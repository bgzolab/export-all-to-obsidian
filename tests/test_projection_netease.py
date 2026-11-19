"""Projection tests for NetEase playlists, songs and recent plays."""

from __future__ import annotations

import pytest

from db.connection import connect
from db.projections import rebuild_platform
from db.projections._upsert import ProjectionError
from db.projections.netease import playlist_state
from tests.projection_helpers import business_rows, record_json, record_text

UID = 42
TABLES = (
    'netease_playlist',
    'netease_song',
    'netease_playlist_song',
    'netease_play_record',
)


def _playlist(
    playlist_id: int,
    *,
    creator: int = UID,
    track_count: int = 3,
    track_update_time: int = 3,
) -> dict:
    return {
        'id': playlist_id,
        'name': f'playlist-{playlist_id}',
        'coverImgUrl': f'cover-{playlist_id}',
        'description': 'description',
        'creator': {'userId': creator, 'nickname': 'owner'},
        'trackCount': track_count,
        'playCount': 10,
        'subscribedCount': 0,
        'createTime': 1,
        'updateTime': 2,
        'trackUpdateTime': track_update_time,
        'specialType': 0,
        'subscribed': False,
        'privacy': 0,
        'ordered': True,
        'tags': ['tag'],
    }


def _record_page(connection, playlists, *, uid=UID):
    return record_json(
        connection,
        'netease.playlists.page',
        {'code': 200, 'playlist': playlists, 'more': False},
        request={'meta': {'uid': uid}},
    )


def _record_detail(connection, playlist_id, song_ids):
    return record_json(
        connection,
        'netease.playlist.detail',
        {
            'code': 200,
            'playlist': {
                'id': playlist_id,
                'trackIds': [{'id': song_id} for song_id in song_ids],
            },
        },
    )


def _record_songs(connection, songs):
    return record_json(
        connection,
        'netease.songs.detail',
        {'code': 200, 'songs': songs},
    )


def _song(song_id, name):
    return {
        'id': song_id,
        'name': name,
        'ar': [{'id': 1, 'name': 'artist'}],
        'al': {'id': 2, 'name': 'album'},
        'dt': 180000,
        'publishTime': 1600000000000,
        'fee': 0,
        'mv': 0,
        'alia': ['alias'],
        'tns': ['trans'],
        'pop': 100,
        'version': 1,
    }


def _record_recent(connection, items):
    return record_json(
        connection,
        'netease.play.recent',
        {'code': 200, 'data': {'total': len(items), 'list': items}},
    )


def _recent_item(song_id, play_time, **overrides):
    item = {
        'playTime': play_time,
        'resourceType': 'SONG',
        'banned': False,
        'multiTerminalInfo': {'device': 'web'},
        'data': _song(song_id, f'song-{song_id}'),
    }
    item.update(overrides)
    return item


def test_rebuild_keeps_only_own_playlists(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7), _playlist(99, creator=1)])

    result = rebuild_platform(connection, 'netease')

    rows = [dict(row) for row in connection.execute('SELECT * FROM netease_playlist')]
    assert [row['playlist_id'] for row in rows] == [7]
    assert rows[0]['creator_id'] == UID
    assert rows[0]['tags_json'] == '["tag"]'
    assert rows[0]['detail_response_id'] is None
    assert result.rows == 1
    connection.close()


def test_rebuild_skips_invalid_playlist_items(monkeypatch):
    connection = connect(':memory:')
    _record_page(
        connection,
        [_playlist(7), {'name': 'broken', 'creator': {'userId': UID}}, 'oops'],
    )

    result = rebuild_platform(connection, 'netease')

    rows = connection.execute('SELECT playlist_id FROM netease_playlist').fetchall()
    assert [row['playlist_id'] for row in rows] == [7]
    assert result.skipped == 2
    connection.close()


def test_rebuild_coerces_fractional_numbers(monkeypatch):
    connection = connect(':memory:')
    playlist = _playlist(7)
    playlist.update({'trackCount': 2.0, 'playCount': 10.5})
    _record_page(connection, [playlist])
    _record_detail(connection, 7, [1])
    song = _song(1, 'one')
    song.update({'pop': 97.5, 'dt': 180000.9})
    _record_songs(connection, [song])

    rebuild_platform(connection, 'netease')

    playlist_row = connection.execute(
        'SELECT track_count, play_count FROM netease_playlist'
    ).fetchone()
    assert (playlist_row['track_count'], playlist_row['play_count']) == (2, 10)
    song_row = connection.execute(
        'SELECT pop, duration FROM netease_song WHERE song_id = 1'
    ).fetchone()
    assert (song_row['pop'], song_row['duration']) == (97, 180000)
    connection.close()


def test_rebuild_marks_songs_omitted_by_successful_batch(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7, track_count=2, track_update_time=5)])
    _record_detail(connection, 7, [1, 2])
    record_json(
        connection,
        'netease.songs.detail',
        {'code': 200, 'songs': [_song(1, 'one')]},
        request={'meta': {'song_ids': [1, 2]}},
    )
    rebuild_platform(connection, 'netease')

    flags = {
        row['song_id']: row['metadata_missing']
        for row in connection.execute(
            'SELECT song_id, metadata_missing FROM netease_song'
        )
    }
    # Song 2 was requested successfully but not returned (unavailable); it
    # must not keep the playlist pending forever.
    assert flags == {1: 0, 2: 1}
    assert playlist_state(connection) == {7: (2, 5)}
    connection.close()


def test_rebuild_keeps_hydrated_song_when_later_batch_omits_it(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7, track_count=1, track_update_time=5)])
    _record_detail(connection, 7, [1])
    record_json(
        connection,
        'netease.songs.detail',
        {'code': 200, 'songs': [_song(1, 'one')]},
        request={'meta': {'song_ids': [1]}},
    )
    record_json(
        connection,
        'netease.songs.detail',
        {'code': 200, 'songs': []},
        request={'meta': {'song_ids': [1]}},
    )
    rebuild_platform(connection, 'netease')

    row = connection.execute(
        'SELECT metadata_missing FROM netease_song WHERE song_id = 1'
    ).fetchone()
    assert row['metadata_missing'] == 0
    assert playlist_state(connection) == {7: (1, 5)}
    connection.close()


def test_rebuild_replaces_members_and_keeps_placeholders(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7)])
    first_detail = _record_detail(connection, 7, [1, 2, 3])
    _record_songs(connection, [_song(1, 'one'), _song(2, 'two')])

    rebuild_platform(connection, 'netease')

    members = [
        dict(row)
        for row in connection.execute(
            'SELECT song_id, position FROM netease_playlist_song ORDER BY position'
        )
    ]
    assert members == [
        {'song_id': 1, 'position': 0},
        {'song_id': 2, 'position': 1},
        {'song_id': 3, 'position': 2},
    ]
    songs = {
        row['song_id']: dict(row)
        for row in connection.execute('SELECT * FROM netease_song')
    }
    assert songs[1]['name'] == 'one'
    assert songs[2]['name'] == 'two'
    assert songs[3]['name'] == ''
    playlist = connection.execute(
        'SELECT detail_response_id, track_update_time FROM netease_playlist'
    ).fetchone()
    assert playlist['detail_response_id'] == first_detail

    second_detail = _record_detail(connection, 7, [2, 2, 4])
    rebuild_platform(connection, 'netease')

    members = [
        dict(row)
        for row in connection.execute(
            'SELECT song_id, position FROM netease_playlist_song ORDER BY position'
        )
    ]
    # Duplicate ids keep only the first position; removed songs leave the
    # song library untouched but disappear from membership.
    assert members == [
        {'song_id': 2, 'position': 0},
        {'song_id': 4, 'position': 2},
    ]
    assert {
        row['song_id'] for row in connection.execute('SELECT song_id FROM netease_song')
    } == {1, 2, 3, 4}
    playlist = connection.execute(
        'SELECT detail_response_id FROM netease_playlist'
    ).fetchone()
    assert playlist['detail_response_id'] == second_detail
    connection.close()


def test_rebuild_empty_playlist_clears_members(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7)])
    _record_detail(connection, 7, [1])
    rebuild_platform(connection, 'netease')

    detail_id = _record_detail(connection, 7, [])
    rebuild_platform(connection, 'netease')

    assert (
        connection.execute('SELECT count(*) FROM netease_playlist_song').fetchone()[0]
        == 0
    )
    playlist = connection.execute(
        'SELECT detail_response_id FROM netease_playlist'
    ).fetchone()
    assert playlist['detail_response_id'] == detail_id
    connection.close()


def test_rebuild_history_dedupes_and_does_not_touch_song_library(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7)])
    _record_recent(connection, [_recent_item(1, 1000), _recent_item(1, 1000)])
    _record_recent(connection, [_recent_item(1, 1000), _recent_item(1, 2000)])
    _record_recent(
        connection,
        [
            _recent_item(2, 3000, resourceType='PROGRAM'),
            _recent_item(2, 0),
            'bad-item',
        ],
    )

    result = rebuild_platform(connection, 'netease')

    records = [
        dict(row)
        for row in connection.execute(
            'SELECT song_id, play_time, resource_type, device_json '
            'FROM netease_play_record ORDER BY song_id, play_time'
        )
    ]
    assert records == [
        {
            'song_id': 1,
            'play_time': 1000,
            'resource_type': 'SONG',
            'device_json': '{"device": "web"}',
        },
        {
            'song_id': 1,
            'play_time': 2000,
            'resource_type': 'SONG',
            'device_json': '{"device": "web"}',
        },
    ]
    assert connection.execute('SELECT count(*) FROM netease_song').fetchone()[0] == 0
    assert result.skipped >= 3
    connection.close()


def test_rebuild_detail_for_unknown_playlist_counts_aux_missed(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7)])
    _record_detail(connection, 999, [])

    result = rebuild_platform(connection, 'netease')

    assert result.aux_missed == 1
    assert connection.execute('SELECT count(*) FROM netease_song').fetchone()[0] == 0
    connection.close()


def test_rebuild_skips_bad_auxiliary_responses(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7)])
    _record_detail(connection, 7, [1, 2])
    record_text(connection, 'netease.songs.detail', 'not-json')
    _record_recent(
        connection,
        [
            'bad-item',
            {'data': {'id': 2}, 'playTime': 0},
            {'data': {'id': 3}, 'playTime': 100, 'resourceType': 'SONG'},
        ],
    )

    result = rebuild_platform(connection, 'netease')

    assert (
        connection.execute('SELECT count(*) FROM netease_playlist_song').fetchone()[0]
        == 2
    )
    assert (
        connection.execute('SELECT count(*) FROM netease_play_record').fetchone()[0]
        == 1
    )
    assert result.skipped >= 3
    connection.close()


def test_rebuild_playlist_auth_code_rolls_back(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7)])
    _record_detail(connection, 7, [1, 2, 3])
    rebuild_platform(connection, 'netease')

    record_json(
        connection,
        'netease.playlists.page',
        {'code': 301, 'message': 'need login'},
        request={'meta': {'uid': UID}},
    )

    with pytest.raises(ProjectionError, match='code=301'):
        rebuild_platform(connection, 'netease')

    # The whole platform transaction rolled back, so the previous projection
    # survives a login-expired response.
    assert (
        connection.execute('SELECT count(*) FROM netease_playlist').fetchone()[0] == 1
    )
    assert (
        connection.execute('SELECT count(*) FROM netease_playlist_song').fetchone()[0]
        == 3
    )
    connection.close()


def test_rebuild_playlist_missing_uid_is_fatal(monkeypatch):
    connection = connect(':memory:')
    record_json(
        connection,
        'netease.playlists.page',
        {'code': 200, 'playlist': [_playlist(7)], 'more': False},
    )

    with pytest.raises(ProjectionError, match='meta.uid'):
        rebuild_platform(connection, 'netease')

    connection.close()


def test_rebuild_playlist_missing_list_is_fatal(monkeypatch):
    connection = connect(':memory:')
    record_json(
        connection,
        'netease.playlists.page',
        {'code': 200, 'more': False},
        request={'meta': {'uid': UID}},
    )

    with pytest.raises(ProjectionError, match='missing playlist'):
        rebuild_platform(connection, 'netease')

    connection.close()


def test_playlist_state_tracks_detail_and_update_fields(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7, track_count=5, track_update_time=123)])
    rebuild_platform(connection, 'netease')

    assert playlist_state(connection) == {}

    _record_detail(connection, 7, [])
    rebuild_platform(connection, 'netease')

    assert playlist_state(connection) == {7: (5, 123)}
    connection.close()


def test_playlist_state_requires_song_metadata(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7, track_count=2, track_update_time=123)])
    _record_detail(connection, 7, [1, 2])
    _record_songs(connection, [_song(1, 'one')])
    rebuild_platform(connection, 'netease')

    # Song 2 is still a placeholder, so the playlist must be fetched again.
    assert playlist_state(connection) == {}

    _record_songs(connection, [_song(2, 'two')])
    rebuild_platform(connection, 'netease')

    assert playlist_state(connection) == {7: (2, 123)}
    connection.close()


def test_rebuild_is_idempotent(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7)])
    _record_detail(connection, 7, [1, 2, 3])
    _record_songs(connection, [_song(1, 'one'), _song(2, 'two')])
    _record_recent(connection, [_recent_item(1, 1000), _recent_item(2, 2000)])

    rebuild_platform(connection, 'netease')
    first = business_rows(connection, TABLES)
    rebuild_platform(connection, 'netease')
    second = business_rows(connection, TABLES)

    assert first == second
    connection.close()


def test_bad_detail_keeps_existing_members(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7)])
    first_detail = _record_detail(connection, 7, [1, 2])
    rebuild_platform(connection, 'netease')

    record_json(
        connection,
        'netease.playlist.detail',
        {'code': 200, 'playlist': {'id': 7}},
    )
    result = rebuild_platform(connection, 'netease')

    assert (
        connection.execute('SELECT count(*) FROM netease_playlist_song').fetchone()[0]
        == 2
    )
    playlist = connection.execute(
        'SELECT detail_response_id FROM netease_playlist'
    ).fetchone()
    assert playlist['detail_response_id'] == first_detail
    assert result.skipped == 1
    connection.close()


def test_rebuild_drops_malformed_track_ids_entries(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7, track_count=2, track_update_time=5)])
    record_json(
        connection,
        'netease.playlist.detail',
        {
            'code': 200,
            'playlist': {
                'id': 7,
                'trackIds': [{'id': 1}, {'bad': 2}, 'oops', {'id': 2}],
            },
        },
    )
    _record_songs(connection, [_song(1, 'one'), _song(2, 'two')])

    result = rebuild_platform(connection, 'netease')

    members = [
        row['song_id']
        for row in connection.execute(
            'SELECT song_id FROM netease_playlist_song ORDER BY position'
        )
    ]
    # The exporter fetches the same subset, so the detail is accepted and the
    # playlist converges instead of being refetched forever.
    assert members == [1, 2]
    assert playlist_state(connection) == {7: (2, 5)}
    assert result.skipped == 2
    connection.close()


def test_rebuild_all_malformed_track_ids_keeps_members(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7)])
    first_detail = _record_detail(connection, 7, [1])
    rebuild_platform(connection, 'netease')

    record_json(
        connection,
        'netease.playlist.detail',
        {'code': 200, 'playlist': {'id': 7, 'trackIds': [{'foo': 1}, 'bad']}},
    )
    result = rebuild_platform(connection, 'netease')

    members = [
        row['song_id']
        for row in connection.execute('SELECT song_id FROM netease_playlist_song')
    ]
    assert members == [1]
    playlist = connection.execute(
        'SELECT detail_response_id FROM netease_playlist'
    ).fetchone()
    assert playlist['detail_response_id'] == first_detail
    assert result.skipped == 1
    connection.close()


def test_business_no_data_playlist_page_is_skipped(monkeypatch):
    connection = connect(':memory:')
    _record_page(connection, [_playlist(7)])
    record_json(
        connection,
        'netease.playlists.page',
        {'code': 500, 'message': 'server error'},
        request={'meta': {'uid': UID}},
    )

    result = rebuild_platform(connection, 'netease')

    assert (
        connection.execute('SELECT count(*) FROM netease_playlist').fetchone()[0] == 1
    )
    assert result.skipped == 1
    connection.close()
