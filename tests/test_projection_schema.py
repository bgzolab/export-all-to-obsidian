from __future__ import annotations

import sqlite3

import pytest

from db.connection import connect
from db.migrate import MIGRATIONS_DIR
from db.raw import finish_run, record_response, start_run

PROJECTION_TABLES = {
    'bangumi_collection',
    'bangumi_subject',
    'bilibili_fav',
    'bilibili_media',
    'bilibili_fav_item',
    'cnblog_bookmark',
    'cnblog_post',
    'github_star',
    'qireader_entry',
    'qireader_article',
    'twitter_tweet',
    'v2ex_topic',
    'v2ex_reply',
    'v2ex_favorite',
    'weibo_post',
    'zhihu_content',
    'zhihu_collection_item',
}

PROJECTION_INDEXES = {
    'idx_bangumi_collection_type',
    'idx_bangumi_subject_type',
    'idx_bilibili_fav_fid',
    'idx_bilibili_media_bvid',
    'idx_bilibili_fav_item_media',
    'idx_cnblog_bookmark_link_url',
    'idx_github_star_owner',
    'idx_github_star_starred_at',
    'idx_qireader_entry_url',
    'idx_qireader_entry_timestamp',
    'idx_twitter_tweet_created_at',
    'idx_v2ex_topic_last_touched',
    'idx_v2ex_reply_topic_thanks',
    'idx_v2ex_reply_created',
    'idx_weibo_post_created_at',
    'idx_zhihu_content_type',
    'idx_zhihu_content_updated_time',
    'idx_zhihu_collection_item_content',
}

COMMON_COLUMNS = {'response_id', 'db_created_at', 'db_updated_at'}

PLATFORM_TIME_COLUMNS = {
    'bangumi_collection': {'updated_at'},
    'bangumi_subject': {'date'},
    'bilibili_fav': {'ctime', 'mtime'},
    'bilibili_media': {'ctime', 'pubtime'},
    'bilibili_fav_item': {'fav_time'},
    'cnblog_bookmark': {'date_added'},
    'cnblog_post': set(),
    'github_star': {'created_at', 'updated_at', 'pushed_at', 'starred_at'},
    'qireader_entry': {'published_at', 'crawled_at', 'timestamp'},
    'qireader_article': set(),
    'twitter_tweet': {'created_at'},
    'v2ex_topic': {'created', 'last_modified', 'last_touched'},
    'v2ex_reply': {'created', 'last_modified'},
    'v2ex_favorite': set(),
    'weibo_post': {'created_at'},
    'zhihu_content': {'created_time', 'updated_time'},
    'zhihu_collection_item': {'created'},
}


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row['name']
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def _index_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row['name']
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }


def _columns(connection: sqlite3.Connection, table: str) -> dict[str, sqlite3.Row]:
    return {
        row['name']: row for row in connection.execute(f'PRAGMA table_info({table})')
    }


def _seed_response(connection: sqlite3.Connection) -> int:
    run_id = start_run(connection, 'test', 'seed')
    response_id = record_response(
        connection,
        run_id,
        endpoint='test.page',
        request={},
        status_code=200,
        body=b'{}',
    )
    finish_run(connection, run_id, 'success')
    return response_id


def test_migration_creates_projection_tables_and_indexes():
    connection = connect(':memory:')

    assert PROJECTION_TABLES <= _table_names(connection)
    assert PROJECTION_INDEXES <= _index_names(connection)
    assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
    connection.close()


def test_every_projection_table_has_provenance_columns():
    connection = connect(':memory:')

    for table in PROJECTION_TABLES:
        columns = _columns(connection, table)
        assert COMMON_COLUMNS <= set(columns), table
        assert columns['response_id']['notnull'] == 1, table
        assert columns['db_created_at']['notnull'] == 1, table
        assert columns['db_updated_at']['notnull'] == 1, table

    connection.close()


def test_projection_tables_are_strict_and_have_platform_time_columns():
    connection = connect(':memory:')

    strict_tables = {
        row['name'] for row in connection.execute('PRAGMA table_list') if row['strict']
    }
    assert PROJECTION_TABLES <= strict_tables

    all_columns: set[str] = set()
    for table, expected in PLATFORM_TIME_COLUMNS.items():
        columns = set(_columns(connection, table))
        assert expected <= columns, table
        all_columns |= columns

    assert 'fav_at' not in all_columns
    assert 'raw_json' not in all_columns
    connection.close()


def test_json_columns_reject_invalid_json():
    connection = connect(':memory:')
    response_id = _seed_response(connection)

    connection.execute(
        'INSERT INTO github_star '
        '(repo_id, full_name, response_id, db_created_at, db_updated_at) '
        "VALUES (1, 'owner/repo', ?, 'now', 'now')",
        (response_id,),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE github_star SET topics_json = 'not-json' WHERE repo_id = 1"
        )

    connection.rollback()
    connection.close()


def test_strict_tables_reject_wrong_scalar_types():
    connection = connect(':memory:')
    response_id = _seed_response(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            'INSERT INTO github_star '
            '(repo_id, full_name, response_id, db_created_at, db_updated_at) '
            "VALUES ('not-an-integer', 'owner/repo', ?, 'now', 'now')",
            (response_id,),
        )

    connection.rollback()
    connection.close()


def test_natural_key_uniqueness_is_enforced():
    connection = connect(':memory:')
    response_id = _seed_response(connection)
    connection.execute(
        'INSERT INTO github_star '
        '(repo_id, full_name, response_id, db_created_at, db_updated_at) '
        "VALUES (1, 'owner/repo', ?, 'now', 'now')",
        (response_id,),
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            'INSERT INTO github_star '
            '(repo_id, full_name, response_id, db_created_at, db_updated_at) '
            "VALUES (2, 'owner/repo', ?, 'now', 'now')",
            (response_id,),
        )

    connection.rollback()
    connection.close()


def test_response_foreign_keys_are_enforced():
    connection = connect(':memory:')

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            'INSERT INTO github_star '
            '(repo_id, full_name, response_id, db_created_at, db_updated_at) '
            "VALUES (1, 'owner/repo', 999, 'now', 'now')"
        )

    connection.rollback()
    connection.close()


def test_relationship_foreign_keys_are_enforced():
    connection = connect(':memory:')
    response_id = _seed_response(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            'INSERT INTO bilibili_fav_item '
            '(fav_id, media_id, response_id, db_created_at, db_updated_at) '
            "VALUES (1, 2, ?, 'now', 'now')",
            (response_id,),
        )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            'INSERT INTO zhihu_collection_item '
            '(collection_id, content_id, response_id, db_created_at, db_updated_at) '
            "VALUES ('c1', 'missing', ?, 'now', 'now')",
            (response_id,),
        )

    connection.rollback()
    connection.close()


def test_migrates_existing_layer1_database(tmp_path):
    db_path = tmp_path / 'eto.db'
    layer1 = sqlite3.connect(db_path)
    layer1.executescript(
        (MIGRATIONS_DIR / '001_raw_layer.sql').read_text(encoding='utf-8')
    )
    layer1.execute('PRAGMA user_version = 1')
    layer1.execute(
        'INSERT INTO sync_run (platform, operation, started_at, status) '
        "VALUES ('test', 'seed', '2026-01-01T00:00:00+00:00', 'success')"
    )
    layer1.commit()
    layer1.close()

    connection = connect(db_path)

    assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
    assert connection.execute('SELECT count(*) FROM sync_run').fetchone()[0] == 1
    assert PROJECTION_TABLES <= _table_names(connection)
    connection.close()
