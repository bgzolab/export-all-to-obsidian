"""Discover V2EX tipped topics from the account balance history.

V2EX has no API for "things I sent thanks for". The logged-in /balance page
lists every coin transaction and its description contains the member and the
topic link, so it is the only complete source for tipped replies/topics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from export_runtime import http
from v2ex.api_endpoints import V2EX_BALANCE
from v2ex.cilent import V2exClient
from v2ex.html import is_signin_page

# shortcut: balance history is capped at 1000 pages, matching the favourites
# guard. Raise it only when a real account exceeds roughly 20k transactions.
V2EX_MAX_BALANCE_PAGES = 1000

# Only sent-thanks transactions carry an outgoing coin movement we care about;
# received thanks and daily rewards describe events without a tipped topic.
THANKS_TYPE = '发送谢意'

_TOPIC_HREF_RE = re.compile(r'/t/(\d+)')
_MEMBER_PATTERN = re.compile(r'感谢\s+(\S+?)\s+的(回复|主题)')


@dataclass(frozen=True)
class ThanksEntry:
    """One sent-thanks transaction describing a tipped reply or topic."""

    thanked_at: str
    topic_id: int
    content_kind: str
    member: str
    amount: float
    balance: float
    topic_title: str
    description: str


@dataclass(frozen=True)
class BalancePage:
    """Parsed balance page: thanks transactions plus duplicate-page markers.

    ``transaction_keys`` covers every transaction on the page, not only
    thanks, because the last page can repeat itself and callers need to detect
    that regardless of which transaction types it contains.
    """

    max_page: int | None
    thanks: list[ThanksEntry]
    transaction_keys: list[str]


def parse_balance_page(html: str) -> BalancePage:
    """Parse the /balance HTML table into thanks entries and page markers.

    Missing ``table.data`` (for example a signin or error page) yields an
    empty page instead of raising: the projection layer treats a signin body
    as fatal, while the fetch layer detects it before calling the parser.
    """
    soup = BeautifulSoup(html, 'html.parser')
    max_page = _parse_max_page(soup)
    table = soup.select_one('table.data')
    if table is None:
        return BalancePage(max_page=max_page, thanks=[], transaction_keys=[])

    thanks: list[ThanksEntry] = []
    transaction_keys: list[str] = []
    for row in table.select('tr'):
        cells = row.select('td')
        # The header row uses <th> cells and therefore has no <td> children.
        if not cells:
            continue
        texts = [_cell_text(cell) for cell in cells]
        transaction_keys.append('\t'.join(texts))
        if len(cells) < 5 or texts[1] != THANKS_TYPE:
            continue
        entry = _parse_thanks_row(cells, texts)
        if entry is not None:
            thanks.append(entry)
    return BalancePage(
        max_page=max_page,
        thanks=thanks,
        transaction_keys=transaction_keys,
    )


def get_balance_page(
    page: int,
    client: V2exClient | None = None,
) -> BalancePage:
    """Fetch and parse one balance page, recording it under raw endpoint.

    A 200 response can still be the signin form when the cookie expired, so
    login state is checked before parsing; otherwise the empty page would look
    like "no more thanks".
    """
    if page > V2EX_MAX_BALANCE_PAGES:
        raise RuntimeError(
            f'balance page limit {V2EX_MAX_BALANCE_PAGES} reached',
        )
    client = client or V2exClient()
    response = http.get(
        client.session,
        V2EX_BALANCE,
        endpoint='v2ex.balance.page',
        params={'p': page},
    )
    if response.status_code != 200:
        response.raise_for_status()
    if '/signin' in getattr(response, 'url', '').lower() or is_signin_page(
        response.text,
    ):
        raise RuntimeError('V2EX login required')
    return parse_balance_page(response.text)


def _parse_thanks_row(
    cells: list[Tag],
    texts: list[str],
) -> ThanksEntry | None:
    """Build one thanks entry, or skip rows that cannot name a topic.

    The kind comes from the fixed "感谢 <member> 的(回复|主题)" prefix, not from
    a bare substring: a topic title may itself contain "的回复", which would
    otherwise turn a topic thanks into a reply one. A row without a numeric
    topic link cannot be tied to an entity, so it is ignored rather than
    failing the whole page.
    """
    description_cell = cells[4]
    description = texts[4]
    topic_link = description_cell.select_one('a[href*="/t/"]')
    if topic_link is None:
        return None
    match = _TOPIC_HREF_RE.search(topic_link.get('href') or '')
    if match is None:
        return None

    kind_match = _MEMBER_PATTERN.search(description)
    if kind_match is None:
        return None
    content_kind = 'reply' if kind_match.group(2) == '回复' else 'topic'

    amount = _parse_float(texts[2])
    balance = _parse_float(texts[3])
    if amount is None or balance is None:
        return None

    member_link = description_cell.select_one('a[href^="/member/"]')
    member = _cell_text(member_link) if member_link is not None else kind_match.group(1)

    return ThanksEntry(
        thanked_at=texts[0],
        topic_id=int(match.group(1)),
        content_kind=content_kind,
        member=member,
        amount=amount,
        balance=balance,
        topic_title=_cell_text(topic_link),
        description=description,
    )


def _parse_max_page(soup: BeautifulSoup) -> int | None:
    """Read the total page count from the pager input's ``max`` attribute."""
    input_tag = soup.select_one('input.page_input[max]')
    if input_tag is None:
        return None
    try:
        return int(input_tag['max'])
    except (KeyError, TypeError, ValueError):
        return None


def _cell_text(tag: Tag) -> str:
    """Collapse the browser's incidental whitespace in one table cell."""
    return ' '.join(tag.get_text(' ', strip=True).split())


def _parse_float(text: str) -> float | None:
    """Parse coin amounts, tolerating stray currency text around the number."""
    try:
        return float(text.replace(',', '').strip())
    except ValueError:
        return None
