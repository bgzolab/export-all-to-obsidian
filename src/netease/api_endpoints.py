"""Upstream NetEase weapi paths and raw endpoint names.

Raw endpoint names are part of the database contract: the projection parser
replays responses by these exact strings, so renaming one requires a rebuild
migration or a parser update.
"""

BASE_URL = 'https://music.163.com'

ACCOUNT_PATH = '/weapi/w/nuser/account/get'
PLAYLISTS_PATH = '/weapi/user/playlist'
PLAYLIST_DETAIL_PATH = '/weapi/v6/playlist/detail'
SONG_DETAIL_PATH = '/weapi/v3/song/detail'
RECENT_PLAYS_PATH = '/weapi/play-record/song/list'
PLAY_RANK_PATH = '/weapi/v1/play/record'

ENDPOINT_ACCOUNT = 'netease.account'
ENDPOINT_PLAYLISTS = 'netease.playlists.page'
ENDPOINT_PLAYLIST_DETAIL = 'netease.playlist.detail'
ENDPOINT_SONGS_DETAIL = 'netease.songs.detail'
ENDPOINT_PLAY_RECENT = 'netease.play.recent'
ENDPOINT_PLAY_RANK_WEEK = 'netease.play.rank.week'
ENDPOINT_PLAY_RANK_ALL = 'netease.play.rank.all'

# ``type=0`` is all-time and ``type=1`` is the recent week. The exporter asks
# for both and stores them under separate endpoints.
PLAY_RANK_TYPES = {
    'all': 0,
    'week': 1,
}
