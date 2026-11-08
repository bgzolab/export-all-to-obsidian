"""
因为API没有提供这个接口，所以只能通过解析HTML来实现获取我的主题列表功能，进度参考：

https://www.v2ex.com/t/1035675

总体希望不大

@Author : bGZo
@Date : 2025-12-13
@Links : https://github.com/bGZo
"""

from export_runtime import http
from v2ex.api_endpoints import V2EX_FAV
from v2ex.cilent import V2exClient
from v2ex.html import is_signin_page, parse_fav_topic_ids

# shortcut: 收藏页分页上限 1000 页，防止接口重复返回最后一页时无限抓取；
# 遇到超长收藏再提高。
V2EX_MAX_FAV_PAGES = 1000


def get_fav_html_with_page(page: int, client: V2exClient | None = None) -> str:
    """
    获取我的主题页面的HTML内容

    :param page: 页码
    :param client: 可复用的 V2EX 客户端
    :return: HTML内容字符串
    """
    client = client or V2exClient()
    response = http.get(
        client.session,
        V2EX_FAV,
        endpoint='v2ex.fav.page',
        params={'p': page},
    )
    if response.status_code != 200:
        response.raise_for_status()
    if '/signin' in getattr(response, 'url', '').lower() or is_signin_page(
        response.text,
    ):
        raise RuntimeError('V2EX login required')
    return response.text


def get_fav_list_topic_id_page(
    page: int,
    client: V2exClient | None = None,
) -> list[int]:
    """
    获取我的主题页面的主题ID列表

    :param page: 页码
    :param client: 可复用的 V2EX 客户端
    :return: 主题ID列表
    """
    if page > V2EX_MAX_FAV_PAGES:
        raise RuntimeError(
            f'favorite page limit {V2EX_MAX_FAV_PAGES} reached',
        )
    return parse_fav_topic_ids(get_fav_html_with_page(page, client))


if __name__ == '__main__':
    page = 1
    # fav_html = get_fav_html_with_page(page)
    # print(fav_html)
    topic_ids = get_fav_list_topic_id_page(page)
    print(topic_ids)
