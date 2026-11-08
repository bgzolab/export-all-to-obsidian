"""
@Author : bGZo
@Date : 2026-08-29
@Links : https://github.com/bGZo
"""

import pytest

from zhihu.cilent import ZhihuClient


def _write_cookies(tmp_path, content):
    p = tmp_path / 'cookies.txt'
    p.write_text(content, encoding='utf-8')
    return str(p)


def test_zhihu_client_headers_configured(monkeypatch, tmp_path):
    path = _write_cookies(tmp_path, '.zhihu.com\tTRUE\t/\tTRUE\t0\td_c0\tzv\n')
    monkeypatch.setenv('COOKIES', path)
    client = ZhihuClient()
    headers = client.session.headers
    assert headers['Cookie'] == 'd_c0=zv'
    assert 'User-Agent' in headers
    assert headers['Referer'] == 'https://www.zhihu.com'


def test_zhihu_client_missing_cookie_raises(monkeypatch, tmp_path):
    path = _write_cookies(tmp_path, '.weibo.com\tTRUE\t/\tTRUE\t0\tname\tvalue\n')
    monkeypatch.setenv('COOKIES', path)
    with pytest.raises(ValueError, match='No cookies found'):
        ZhihuClient()


def test_zhihu_export_handles_empty_list_content(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from export_runtime.index_writer import IndexWriter
    from zhihu.exporter import export

    pages = {
        0: SimpleNamespace(
            data=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        id='1',
                        content=[],
                        title=None,
                        question=None,
                        url='https://example.com/1',
                        created_time=0,
                        updated_time=0,
                    )
                ),
                SimpleNamespace(
                    content=SimpleNamespace(
                        id='2',
                        content='<p>ok</p>',
                        title='Good',
                        question=None,
                        url='https://example.com/2',
                        created_time=0,
                        updated_time=0,
                    )
                ),
            ]
        ),
        20: SimpleNamespace(data=[]),
    }
    monkeypatch.setattr(
        'zhihu.exporter.get_collection_page',
        lambda collection, offset, limit: pages[offset],
    )

    output_dir = tmp_path / 'out'
    export(
        'collection', str(output_dir), IndexWriter(file_path=str(tmp_path / 'index.md'))
    )

    files = sorted(path.name for path in output_dir.glob('*.md'))
    assert len(files) == 2
    assert '~2-Good.md' in files
