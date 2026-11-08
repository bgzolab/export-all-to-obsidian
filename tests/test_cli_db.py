from __future__ import annotations

import sqlite3
from types import SimpleNamespace

from click.testing import CliRunner

from app.credential_guard import CredentialProbeResult
from db.connection import connect
from export_to_obsidian import eto
from tests.projection_helpers import record_json, record_missing

BANGUMI_COLLECTION = {
    'subject_id': 1,
    'id': 1001,
    'updated_at': '2026-01-02T03:04:05+08:00',
    'tags': [],
    'vol_status': 0,
    'ep_status': 0,
    'subject_type': 2,
    'rate': 0,
    'type': 3,
    'private': False,
    'subject': {'id': 1, 'name': 'Subject'},
}

BANGUMI_SUBJECT = {
    'id': 1,
    'name': 'Subject',
    'name_cn': '条目',
    'date': '2020-01-01',
    'type': 2,
}


def _invoke_cnblog(monkeypatch, db_path: str | None):
    monkeypatch.setattr(
        'app.cli.probe_cnblog_credentials',
        lambda: CredentialProbeResult.valid('cnblog'),
    )
    monkeypatch.setattr('app.cli.export_cnblog', lambda output, index_writer: None)
    args = (['--db', db_path] if db_path else []) + [
        'cnblog',
        '-o',
        'output/cnblog',
    ]
    return CliRunner().invoke(eto, args)


def _query_one(db_path, sql, params=()):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(sql, params).fetchone()
    finally:
        connection.close()


def test_cli_db_explicit_path_creates_run_with_command(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    monkeypatch.setattr(
        'app.context.sys.argv',
        ['eto', '--db', db_path, 'cnblog', '-o', 'output/cnblog'],
    )

    result = _invoke_cnblog(monkeypatch, db_path)

    assert result.exit_code == 0, result.output
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['platform'] == 'cnblog'
    assert run['operation'] == 'bookmarks'
    assert run['status'] == 'success'
    assert run['command'].startswith('eto --db')


def test_cli_db_default_path(monkeypatch, tmp_path):
    default_db = tmp_path / 'default' / 'eto.db'
    monkeypatch.setattr('db.connection.DEFAULT_DB_PATH', str(default_db))

    result = _invoke_cnblog(monkeypatch, None)

    assert result.exit_code == 0, result.output
    assert default_db.exists()


def test_cli_db_directory_is_rejected(monkeypatch, tmp_path):
    result = _invoke_cnblog(monkeypatch, str(tmp_path))

    assert result.exit_code == 1
    assert 'Database path is a directory' in result.output


def test_cli_db_help_lists_option():
    result = CliRunner().invoke(eto, ['--help'])

    assert result.exit_code == 0
    assert '--db' in result.output


def test_cli_marks_run_partial(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')

    def fake_export(output, index_writer):
        from app.context import mark_run_partial

        mark_run_partial()

    monkeypatch.setattr(
        'app.cli.probe_cnblog_credentials',
        lambda: CredentialProbeResult.valid('cnblog'),
    )
    monkeypatch.setattr('app.cli.export_cnblog', fake_export)

    result = CliRunner().invoke(
        eto,
        ['--db', db_path, 'cnblog', '-o', 'output/cnblog'],
    )

    assert result.exit_code == 0, result.output
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'partial'


def test_cli_marks_run_failed_on_exception(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')

    def fake_export(output, index_writer):
        raise RuntimeError('boom')

    monkeypatch.setattr(
        'app.cli.probe_cnblog_credentials',
        lambda: CredentialProbeResult.valid('cnblog'),
    )
    monkeypatch.setattr('app.cli.export_cnblog', fake_export)

    result = CliRunner().invoke(
        eto,
        ['--db', db_path, 'cnblog', '-o', 'output/cnblog'],
    )

    assert result.exit_code != 0
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'failed'
    assert 'RuntimeError: boom' in run['error']


def test_cli_import_markdown(tmp_path):
    db_path = str(tmp_path / 'eto.db')
    vault = tmp_path / 'vault'
    vault.mkdir()
    (vault / 'a.md').write_text('# A\n', encoding='utf-8')

    runner = CliRunner()
    first = runner.invoke(eto, ['--db', db_path, 'import-markdown', str(vault)])
    second = runner.invoke(eto, ['--db', db_path, 'import-markdown', str(vault)])

    assert first.exit_code == 0, first.output
    assert '导入完成: 1 个' in first.output
    assert second.exit_code == 0, second.output
    assert '跳过 1 个' in second.output


def test_twitter_failure_marks_run_partial(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    monkeypatch.setattr(
        'app.cli.probe_twitter_credentials',
        lambda: CredentialProbeResult.valid('twitter'),
    )
    monkeypatch.setattr('twitter.exporter.TwitterClient', lambda: object())

    def fail(*args, **kwargs):
        raise RuntimeError('network down')

    monkeypatch.setattr('twitter.exporter.get_twitter_like_list', fail)

    result = CliRunner().invoke(
        eto,
        [
            '--db',
            db_path,
            'twitter',
            '-o',
            str(tmp_path / 'output'),
            '--max-pages',
            '1',
        ],
    )

    assert result.exit_code == 0, result.output
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'partial'


def test_twitter_none_page_marks_run_partial(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    monkeypatch.setattr(
        'app.cli.probe_twitter_credentials',
        lambda: CredentialProbeResult.valid('twitter'),
    )
    monkeypatch.setattr('twitter.exporter.TwitterClient', lambda: object())
    monkeypatch.setattr(
        'twitter.exporter.get_twitter_like_list',
        lambda *args, **kwargs: None,
    )

    result = CliRunner().invoke(
        eto,
        ['--db', db_path, 'twitter', '-o', str(tmp_path / 'output')],
    )

    assert result.exit_code == 0, result.output
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'partial'


def _run_weibo_with_page(monkeypatch, tmp_path, page):
    db_path = str(tmp_path / 'eto.db')
    monkeypatch.setattr(
        'app.cli.probe_weibo_credentials',
        lambda uid: CredentialProbeResult.valid('weibo'),
    )
    monkeypatch.setattr(
        'weibo.exporter.get_weibo_like_list',
        lambda *args, **kwargs: page,
    )

    result = CliRunner().invoke(
        eto,
        ['--db', db_path, 'weibo', '-u', '1', '-o', str(tmp_path / 'output')],
    )

    assert result.exit_code == 0, result.output
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'partial'


def test_weibo_none_page_marks_run_partial(monkeypatch, tmp_path):
    _run_weibo_with_page(monkeypatch, tmp_path, None)


def test_weibo_error_page_marks_run_partial(monkeypatch, tmp_path):
    class ErrorPage:
        ok = 0
        data = None

    _run_weibo_with_page(monkeypatch, tmp_path, ErrorPage())


def test_cli_survives_finish_run_failure(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    monkeypatch.setattr(
        'app.cli.probe_cnblog_credentials',
        lambda: CredentialProbeResult.valid('cnblog'),
    )
    monkeypatch.setattr('app.cli.export_cnblog', lambda output, index_writer: None)

    def fail_finish(*args, **kwargs):
        raise sqlite3.OperationalError('database is locked')

    monkeypatch.setattr('app.context.raw.finish_run', fail_finish)

    result = CliRunner().invoke(
        eto,
        ['--db', db_path, 'cnblog', '-o', 'output/cnblog'],
    )

    assert result.exit_code == 0, result.output
    assert '结束 sync_run 失败' in result.output


def _seed_bangumi_raw(db_path) -> None:
    connection = connect(db_path)
    record_json(
        connection,
        'bangumi.collections.page',
        {'data': [BANGUMI_COLLECTION]},
    )
    record_json(connection, 'bangumi.subject.detail', BANGUMI_SUBJECT)
    connection.close()


def test_db_only_does_not_require_output(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    seen = {}

    def fake_export(output, index_writer):
        seen['output'] = output
        seen['enabled'] = index_writer.enabled

    monkeypatch.setattr(
        'app.cli.probe_cnblog_credentials',
        lambda: CredentialProbeResult.valid('cnblog'),
    )
    monkeypatch.setattr('app.cli.export_cnblog', fake_export)

    result = CliRunner().invoke(eto, ['--db', db_path, '--db-only', 'cnblog'])

    assert result.exit_code == 0, result.output
    assert seen == {'output': '', 'enabled': False}
    assert '投影完成: 0 个响应，0 行' in result.output


def test_without_db_only_output_is_required(tmp_path):
    result = CliRunner().invoke(
        eto,
        ['--db', str(tmp_path / 'eto.db'), 'cnblog'],
    )

    assert result.exit_code == 2
    assert '--output/-o is required' in result.output


def test_without_db_only_template_is_required(tmp_path):
    result = CliRunner().invoke(
        eto,
        [
            '--db',
            str(tmp_path / 'eto.db'),
            'bangumi',
            '-s',
            '2',
            '-o',
            str(tmp_path / 'output'),
        ],
    )

    assert result.exit_code == 2
    assert '--template/-t is required' in result.output


def test_db_only_rejects_index_file(tmp_path):
    result = CliRunner().invoke(
        eto,
        [
            '--db-only',
            '--index-file',
            str(tmp_path / 'index.md'),
            '--db',
            str(tmp_path / 'eto.db'),
            'cnblog',
        ],
    )

    assert result.exit_code == 2
    assert '--index-file cannot be used with --db-only' in result.output


def test_db_only_suppresses_markdown_and_index(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    output_dir = tmp_path / 'output'

    def fake_export(output, index_writer):
        from export_runtime.exporter_support import (
            add_index_entry,
            stop_if_output_exists,
            write_markdown_output,
        )

        assert output == ''
        assert not stop_if_output_exists(
            str(output_dir),
            'demo',
            index_writer=index_writer,
            section_name='cnblog',
        )
        write_markdown_output(str(output_dir), 'demo', {'title': 'demo'}, 'body')
        add_index_entry(index_writer, link_target='demo', title='demo')
        index_writer.flush('cnblog')

    monkeypatch.setattr(
        'app.cli.probe_cnblog_credentials',
        lambda: CredentialProbeResult.valid('cnblog'),
    )
    monkeypatch.setattr('app.cli.export_cnblog', fake_export)

    result = CliRunner().invoke(eto, ['--db', db_path, '--db-only', 'cnblog'])

    assert result.exit_code == 0, result.output
    assert not output_dir.exists()
    assert '导出index' not in result.output


def test_db_only_projects_after_fetch(monkeypatch, tmp_path):
    db_path = tmp_path / 'eto.db'

    def fake_export(subject_type, collection_type, output, template, writer, force):
        assert output == ''
        assert template == ''
        connection = connect(db_path)
        record_json(
            connection,
            'bangumi.collections.page',
            {'data': [BANGUMI_COLLECTION]},
        )
        record_json(connection, 'bangumi.subject.detail', BANGUMI_SUBJECT)
        connection.close()

    monkeypatch.setattr(
        'app.cli.probe_bangumi_credentials',
        lambda: CredentialProbeResult.valid('bangumi'),
    )
    monkeypatch.setattr('app.cli.export_bangumi', fake_export)

    result = CliRunner().invoke(
        eto,
        ['--db', str(db_path), '--db-only', 'bangumi', '-s', '2', '-c', '3'],
    )

    assert result.exit_code == 0, result.output
    assert '投影完成: 2 个响应，2 行' in result.output
    connection = connect(db_path)
    assert (
        connection.execute('SELECT count(*) FROM bangumi_collection').fetchone()[0] == 1
    )
    assert connection.execute('SELECT count(*) FROM bangumi_subject').fetchone()[0] == 1
    run = connection.execute(
        "SELECT status FROM sync_run WHERE platform = 'bangumi' "
        'ORDER BY id DESC LIMIT 1'
    ).fetchone()
    assert run['status'] == 'success'
    connection.close()


def test_db_only_projection_failure_marks_run_partial(monkeypatch, tmp_path):
    db_path = tmp_path / 'eto.db'

    def fake_export(subject_type, collection_type, output, template, writer, force):
        connection = connect(db_path)
        record_json(connection, 'bangumi.collections.page', {'data': 'bad'})
        connection.close()

    monkeypatch.setattr(
        'app.cli.probe_bangumi_credentials',
        lambda: CredentialProbeResult.valid('bangumi'),
    )
    monkeypatch.setattr('app.cli.export_bangumi', fake_export)

    result = CliRunner().invoke(
        eto,
        ['--db', str(db_path), '--db-only', 'bangumi', '-s', '2', '-c', '3'],
    )

    assert result.exit_code != 0
    assert '投影失败' in result.output
    connection = connect(db_path)
    run = connection.execute(
        "SELECT status FROM sync_run WHERE platform = 'bangumi' "
        'ORDER BY id DESC LIMIT 1'
    ).fetchone()
    assert run['status'] == 'partial'
    connection.close()


def test_db_only_v2ex_fetches_all_pages(monkeypatch, tmp_path):
    pages = {1: [1], 2: [2], 3: []}
    page_calls = []
    topic_calls = []
    reply_calls = []

    def fake_page(page, client=None):
        page_calls.append(page)
        return pages[page]

    def fake_topic(topic_id):
        topic_calls.append(topic_id)
        return SimpleNamespace(
            result=SimpleNamespace(
                title=f'Topic {topic_id}',
                content='body',
                created=0,
                last_modified=0,
                url=f'https://www.v2ex.com/t/{topic_id}',
                replies=1 if topic_id == 1 else 0,
            )
        )

    output_dir = tmp_path / 'output'
    output_dir.mkdir()
    (output_dir / '~1-Topic-1.md').write_text('exists', encoding='utf-8')

    monkeypatch.setattr(
        'app.cli.probe_v2ex_credentials',
        lambda: CredentialProbeResult.valid('v2ex'),
    )
    monkeypatch.setattr('v2ex.exporter.V2exClient', lambda: object())
    monkeypatch.setattr('v2ex.exporter.get_fav_list_topic_id_page', fake_page)
    monkeypatch.setattr('v2ex.exporter.get_v2ex_topic_info', fake_topic)
    monkeypatch.setattr(
        'v2ex.exporter.fetch_all_replies',
        lambda topic_id: reply_calls.append(topic_id),
    )

    result = CliRunner().invoke(
        eto,
        ['--db', str(tmp_path / 'eto.db'), '--db-only', 'v2ex', '-o', str(output_dir)],
    )

    assert result.exit_code == 0, result.output
    assert page_calls == [1, 2, 3]
    assert topic_calls == [1, 2]
    assert reply_calls == [1]
    assert (output_dir / '~1-Topic-1.md').read_text(encoding='utf-8') == 'exists'


def test_db_rebuild_bangumi(tmp_path):
    db_path = tmp_path / 'eto.db'
    _seed_bangumi_raw(db_path)

    result = CliRunner().invoke(
        eto,
        ['--db', str(db_path), 'db', 'rebuild', 'bangumi'],
    )

    assert result.exit_code == 0, result.output
    assert '重建完成: 2 个响应，2 行' in result.output
    connection = connect(db_path)
    assert (
        connection.execute(
            'SELECT name_cn FROM bangumi_subject WHERE subject_id = 1'
        ).fetchone()[0]
        == '条目'
    )
    connection.close()


def test_db_rebuild_skips_transport_errors(tmp_path):
    db_path = tmp_path / 'eto.db'
    _seed_bangumi_raw(db_path)
    connection = connect(db_path)
    record_missing(connection, 'bangumi.subject.characters')
    connection.close()

    result = CliRunner().invoke(
        eto,
        ['--db', str(db_path), 'db', 'rebuild', 'bangumi'],
    )

    assert result.exit_code == 0, result.output
    assert '跳过 1 条错误响应' in result.output
    connection = connect(db_path)
    assert connection.execute('SELECT count(*) FROM bangumi_subject').fetchone()[0] == 1
    connection.close()


def test_db_rebuild_rejects_unknown_platform(tmp_path):
    result = CliRunner().invoke(
        eto,
        ['--db', str(tmp_path / 'eto.db'), 'db', 'rebuild', 'unknown'],
    )

    assert result.exit_code == 2
    assert 'Invalid value' in result.output


def test_db_rebuild_reports_projection_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        'app.cli.rebuild_platform',
        lambda connection, platform: (_ for _ in ()).throw(RuntimeError('boom')),
    )

    result = CliRunner().invoke(
        eto,
        ['--db', str(tmp_path / 'eto.db'), 'db', 'rebuild', 'bangumi'],
    )

    assert result.exit_code == 1
    assert '投影失败: boom' in result.output


def test_v2ex_list_failure_marks_run_failed(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    monkeypatch.setattr(
        'app.cli.probe_v2ex_credentials',
        lambda: CredentialProbeResult.valid('v2ex'),
    )

    def fail(page, client=None):
        raise RuntimeError('list page failed')

    monkeypatch.setattr('v2ex.exporter.V2exClient', lambda: object())
    monkeypatch.setattr('v2ex.exporter.get_fav_list_topic_id_page', fail)

    result = CliRunner().invoke(
        eto,
        ['--db', db_path, 'v2ex', '-o', str(tmp_path / 'output')],
    )

    assert result.exit_code != 0
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'failed'
    assert 'RuntimeError: list page failed' in run['error']


def test_bilibili_item_error_marks_run_partial(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    media = SimpleNamespace(
        bvid='BV1',
        title='Video',
        pubtime=0,
        fav_time=0,
        intro='',
        upper=None,
    )

    def fake_favlist(fid, page, size):
        if page == 1:
            return SimpleNamespace(data=SimpleNamespace(medias=[media]))
        return SimpleNamespace(data=SimpleNamespace(medias=[]))

    monkeypatch.setattr(
        'app.cli.probe_bilibili_credentials',
        lambda fid: CredentialProbeResult.valid('bilibili'),
    )
    monkeypatch.setattr('bilibili.exporter.get_bilibili_favlistd', fake_favlist)

    result = CliRunner().invoke(
        eto,
        ['--db', db_path, 'bilibili', '-f', '1', '-o', str(tmp_path / 'output')],
    )

    assert result.exit_code == 0, result.output
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'partial'


def test_weibo_item_error_marks_run_partial(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    item = SimpleNamespace(
        mblogid='m1',
        user=None,
        text_raw='text',
        isLongText=False,
    )

    def fake_like(uid, page_index):
        if page_index == 1:
            return SimpleNamespace(ok=1, data=SimpleNamespace(list=[item]))
        return SimpleNamespace(ok=1, data=SimpleNamespace(list=[]))

    monkeypatch.setattr(
        'app.cli.probe_weibo_credentials',
        lambda uid: CredentialProbeResult.valid('weibo'),
    )
    monkeypatch.setattr('weibo.exporter.get_weibo_like_list', fake_like)

    result = CliRunner().invoke(
        eto,
        ['--db', db_path, 'weibo', '-u', '1', '-o', str(tmp_path / 'output')],
    )

    assert result.exit_code == 0, result.output
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'partial'


def test_twitter_item_error_marks_run_partial(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    tweet = SimpleNamespace(author=None, id_str='1', full_text='text')
    page = SimpleNamespace(tweets=[tweet], cursor_bottom=None)

    monkeypatch.setattr(
        'app.cli.probe_twitter_credentials',
        lambda: CredentialProbeResult.valid('twitter'),
    )
    monkeypatch.setattr('twitter.exporter.TwitterClient', lambda: object())
    monkeypatch.setattr(
        'twitter.exporter.get_twitter_like_list',
        lambda *args, **kwargs: page,
    )

    result = CliRunner().invoke(
        eto,
        ['--db', db_path, 'twitter', '-o', str(tmp_path / 'output')],
    )

    assert result.exit_code == 0, result.output
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'partial'


def test_v2ex_write_error_marks_partial_and_continues(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    pages = {1: [1, 2], 2: []}
    writes = []

    def fake_page(page, client=None):
        return pages[page]

    def fake_topic(topic_id):
        return SimpleNamespace(
            result=SimpleNamespace(
                title=f'Topic {topic_id}',
                content='body',
                created=0,
                last_modified=0,
                url=f'https://www.v2ex.com/t/{topic_id}',
                replies=0,
            )
        )

    def fake_write(output_dir, filename, metadata, content):
        writes.append(filename)
        if len(writes) == 1:
            raise OSError('disk full')

    monkeypatch.setattr(
        'app.cli.probe_v2ex_credentials',
        lambda: CredentialProbeResult.valid('v2ex'),
    )
    monkeypatch.setattr('v2ex.exporter.V2exClient', lambda: object())
    monkeypatch.setattr('v2ex.exporter.get_fav_list_topic_id_page', fake_page)
    monkeypatch.setattr('v2ex.exporter.get_v2ex_topic_info', fake_topic)
    monkeypatch.setattr('v2ex.exporter.write_markdown_output', fake_write)

    result = CliRunner().invoke(
        eto,
        ['--db', db_path, 'v2ex', '-o', str(tmp_path / 'output')],
    )

    assert result.exit_code == 0, result.output
    assert writes == ['1-Topic-1', '2-Topic-2']
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'partial'


def test_v2ex_null_topic_result_marks_partial(monkeypatch, tmp_path):
    db_path = str(tmp_path / 'eto.db')
    pages = {1: [1], 2: []}

    def fake_page(page, client=None):
        return pages[page]

    monkeypatch.setattr(
        'app.cli.probe_v2ex_credentials',
        lambda: CredentialProbeResult.valid('v2ex'),
    )
    monkeypatch.setattr('v2ex.exporter.V2exClient', lambda: object())
    monkeypatch.setattr('v2ex.exporter.get_fav_list_topic_id_page', fake_page)
    monkeypatch.setattr(
        'v2ex.exporter.get_v2ex_topic_info',
        lambda topic_id: SimpleNamespace(result=None),
    )

    result = CliRunner().invoke(
        eto,
        ['--db', db_path, 'v2ex', '-o', str(tmp_path / 'output')],
    )

    assert result.exit_code == 0, result.output
    run = _query_one(
        db_path,
        'SELECT * FROM sync_run ORDER BY id DESC LIMIT 1',
    )
    assert run['status'] == 'partial'
