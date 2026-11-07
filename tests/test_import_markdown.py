from __future__ import annotations

import hashlib
import json
import zlib

import pytest

from db.connection import connect
from db.import_markdown import import_markdown


def test_import_markdown_stores_files(tmp_path):
    root = tmp_path / 'vault'
    (root / 'nested').mkdir(parents=True)
    (root / 'a.md').write_text('---\ntitle: A\n---\n\n# A\n', encoding='utf-8')
    (root / 'nested' / 'b.md').write_text('# B\n', encoding='utf-8')

    connection = connect(tmp_path / 'eto.db')
    stats = import_markdown(connection, root)

    assert stats == {'run_id': 1, 'imported': 2, 'skipped': 0, 'failed': 0}
    run = connection.execute('SELECT * FROM sync_run').fetchone()
    assert run['platform'] == 'local'
    assert run['operation'] == 'import.markdown'
    assert run['status'] == 'success'

    rows = connection.execute('SELECT * FROM sync_response ORDER BY id').fetchall()
    assert len(rows) == 2
    first = rows[0]
    request = json.loads(first['request'])
    assert request['path'] == 'a.md'
    assert request['size'] == len((root / 'a.md').read_bytes())
    assert zlib.decompress(first['body']) == (root / 'a.md').read_bytes()
    assert first['sha256'] == hashlib.sha256((root / 'a.md').read_bytes()).hexdigest()
    connection.close()


def test_import_markdown_is_idempotent(tmp_path):
    root = tmp_path / 'vault'
    root.mkdir()
    (root / 'a.md').write_text('# A\n', encoding='utf-8')
    connection = connect(tmp_path / 'eto.db')

    first = import_markdown(connection, root)
    second = import_markdown(connection, root)

    assert first['imported'] == 1
    assert second['imported'] == 0
    assert second['skipped'] == 1
    assert connection.execute('SELECT COUNT(*) FROM sync_response').fetchone()[0] == 1
    connection.close()


def test_import_markdown_adds_changed_file(tmp_path):
    root = tmp_path / 'vault'
    root.mkdir()
    file_path = root / 'a.md'
    file_path.write_text('# A\n', encoding='utf-8')
    connection = connect(tmp_path / 'eto.db')

    import_markdown(connection, root)
    file_path.write_text('# A changed\n', encoding='utf-8')
    stats = import_markdown(connection, root)

    assert stats['imported'] == 1
    assert stats['skipped'] == 0
    assert connection.execute('SELECT COUNT(*) FROM sync_response').fetchone()[0] == 2
    connection.close()


def test_import_markdown_scopes_idempotency_by_directory(tmp_path):
    first = tmp_path / 'vault-a'
    second = tmp_path / 'vault-b'
    first.mkdir()
    second.mkdir()
    for root in (first, second):
        (root / 'same.md').write_text('# Same\n', encoding='utf-8')
    connection = connect(tmp_path / 'eto.db')

    first_stats = import_markdown(connection, first)
    second_stats = import_markdown(connection, second)

    assert first_stats['imported'] == 1
    assert second_stats['imported'] == 1
    assert connection.execute('SELECT COUNT(*) FROM sync_response').fetchone()[0] == 2
    connection.close()


def test_import_markdown_rejects_non_directory(tmp_path):
    connection = connect(tmp_path / 'eto.db')

    with pytest.raises(ValueError, match='Not a directory'):
        import_markdown(connection, tmp_path / 'missing')
    connection.close()


def test_import_markdown_marks_run_failed_on_unexpected_error(tmp_path, monkeypatch):
    root = tmp_path / 'vault'
    root.mkdir()
    (root / 'a.md').write_text('# A\n', encoding='utf-8')
    connection = connect(tmp_path / 'eto.db')

    def fail(*args, **kwargs):
        raise RuntimeError('disk error')

    monkeypatch.setattr('db.import_markdown.raw.record_response', fail)

    with pytest.raises(RuntimeError, match='disk error'):
        import_markdown(connection, root)

    run = connection.execute('SELECT * FROM sync_run').fetchone()
    assert run['status'] == 'failed'
    assert 'RuntimeError: disk error' in run['error']
    connection.close()
