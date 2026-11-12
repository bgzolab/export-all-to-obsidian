"""CNBlog URL parsing."""

from __future__ import annotations

from urllib.parse import urlsplit

_POST_PATH_PARTS = {'p', 'n', 'articles'}


def post_id_from_url(url: str) -> int | None:
    """Return the numeric post id from a CNBlog article URL, if any."""
    parts = [part for part in urlsplit(url).path.split('/') if part]
    for index, part in enumerate(parts[:-1]):
        if part in _POST_PATH_PARTS:
            candidate = parts[index + 1].split('.', 1)[0]
            if candidate.isdigit():
                return int(candidate)
    if 'archive' in parts:
        candidate = parts[-1].split('.', 1)[0]
        if candidate.isdigit():
            return int(candidate)
    return None
