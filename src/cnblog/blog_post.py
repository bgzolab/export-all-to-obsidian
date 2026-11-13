"""
@Author : bGZo
@Date : 2025-07-27
@Links : https://github.com/bGZo
"""

from cnblog.api_endpoints import BLOG_POST
from cnblog.client import CnblogClient
from cnblog.urls import post_id_from_url
from export_runtime import http


def get_cnblog_post_body_by_url(url: str):
    """
    获取指定 URL 的博客文章正文内容。

    :param url: 博客文章的 URL
    :return: 博客文章正文内容；无法解析文章 ID 时返回空字符串
    """
    client = CnblogClient()

    post_id = post_id_from_url(url)
    if post_id is None:
        print(f'无法从 URL 解析文章 ID，跳过正文抓取: {url}')
        return ''

    response = http.get(
        client.session,
        BLOG_POST % post_id,
        endpoint='cnblog.post.body',
    )

    if response.status_code == 200:
        return response.text
    else:
        print(f'Error fetching post body for ID {post_id}: {response.status_code}')
        return ''
        # response.raise_for_status()  # Raise an error for bad responses
