"""CNBlog URL parsing."""

from __future__ import annotations

from urllib.parse import urlsplit

# /n/ 是新闻，id 与 /blogposts/{id}/body 的博客命名空间不同，不能混用。
_POST_PATH_PARTS = {'p', 'articles'}
# 站点级路由（如 /sitehome/p/2）也含 p，但它们是列表页，不是文章详情。
_RESERVED_ROUTES = {'sitehome', 'agg', 'cmt', 'news', 'topic', 'picker'}
_ARTICLE_SUFFIXES = ('.html', '.aspx')


def _is_cnblogs_host(host: str) -> bool:
    return host == 'cnblogs.com' or host.endswith('.cnblogs.com')


def _numeric(value: str) -> int | None:
    return int(value) if value.isascii() and value.isdigit() else None


def post_id_from_url(url: str) -> int | None:
    """Return the numeric post id from a CNBlog article URL, if any."""
    split = urlsplit(url)
    if not _is_cnblogs_host(split.hostname or ''):
        return None
    parts = [part for part in split.path.split('/') if part]
    for index, part in enumerate(parts[:-1]):
        if part not in _POST_PATH_PARTS:
            continue
        # 详情 URL 始终是 /{user}/p/{id}，首段或站点级路由前的不是文章。
        if index == 0 or parts[index - 1].lower() in _RESERVED_ROUTES:
            continue
        raw = parts[index + 1]
        # 文章详情固定为 /{user}/articles/{id}.html，其余形态按列表页处理。
        if part == 'articles' and not raw.lower().endswith(_ARTICLE_SUFFIXES):
            continue
        candidate = _numeric(raw.split('.', 1)[0])
        if candidate is not None:
            return candidate
    if 'archive' in parts:
        index = parts.index('archive')
        # 归档列表页也含 archive，只有完整 /archive/YYYY/MM/DD/{id} 才是文章。
        if len(parts) != index + 5:
            return None
        year, month, day = parts[index + 1 : index + 4]
        if not all(
            len(part) == width and part.isascii() and part.isdigit()
            for part, width in zip((year, month, day), (4, 2, 2), strict=True)
        ):
            return None
        return _numeric(parts[index + 4].split('.', 1)[0])
    return None
