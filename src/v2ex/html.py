"""V2EX HTML parsing helpers."""

from bs4 import BeautifulSoup


def is_signin_page(html: str) -> bool:
    """Return True when V2EX redirected to its sign-in form."""
    soup = BeautifulSoup(html, 'html.parser')
    return soup.select_one('form[action*="/signin"]') is not None


def parse_fav_topic_ids(fav_html: str) -> list[int]:
    """从收藏页 HTML 中解析主题 ID，保留顺序并去重。"""
    soup = BeautifulSoup(fav_html, 'html.parser')
    topic_id_list = []
    for topic_link in soup.select('a[href^="/t/"]'):
        href = topic_link.get('href')
        if href:
            try:
                topic_id = int(href.split('/t/')[1].split('#')[0])
                topic_id_list.append(topic_id)
            except ValueError:
                continue
    # 使用 dict.fromkeys 保留插入顺序去重 (Python 3.7+)
    return list(dict.fromkeys(topic_id_list))
