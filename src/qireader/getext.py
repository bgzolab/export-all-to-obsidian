"""
@Author : bGZo
@Date : 2025-12-07
@Links : https://github.com/bGZo
"""

from export_runtime import http
from qireader.cilent import QiReaderClient


def get_html_text_from_url(url) -> str:
    client = QiReaderClient()
    response = http.get(
        client.session,
        client.api_endpoints.FULL_TEXT,
        endpoint='qireader.article',
        params={
            'keep-classes': 1,
            'url': url,
        },
    )
    print(f'获取{url}响应成功')
    return response.json()['content']


if __name__ == '__main__':
    test_url = (
        'https://www.hecaitou.com/2023/06/go-through-the-window-to-get-a-haircut.html'
    )
    html_text = get_html_text_from_url(test_url)
    print(html_text)
