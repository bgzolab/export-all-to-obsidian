"""
@Author : bGZo
@Date : 2025-07-27
@Links : https://github.com/bGZo
"""

from cnblog.api_endpoints import BLOG_POST
from cnblog.client import CnblogClient
from export_runtime import http


def get_cnblog_post_body_by_url(url: str):
    """
    获取指定 ID 的博客文章正文内容。

    :param id: 博客文章的 ID
    :return: 博客文章正文内容
    """
    client = CnblogClient()

    # 从 URL 中提取 ID，并去除 .html 后缀
    id = url.split('/')[-1]
    # NOTE: 这里假设 URL 的最后一部分是 ID，且可能以 .html 结尾。如：
    #  https://api.cnblogs.com/api/blogposts/755751.html/body
    id = id.removesuffix('.html')

    response = http.get(
        client.session,
        BLOG_POST % id,
        endpoint='cnblog.post.body',
    )
    # % 是 Python 早期的字符串格式化操作符。它会查找字符串中的 % 占位符（如 %s），并用后面的值替换它。

    if response.status_code == 200:
        return response.text
    else:
        print(f'Error fetching post body for ID {id}: {response.status_code}')
        return ''
        # response.raise_for_status()  # Raise an error for bad responses
