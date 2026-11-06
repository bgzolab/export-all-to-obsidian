"""
@Author : bGZo
@Date : 2025-12-13
@Links : https://github.com/bGZo
"""

from export_runtime import http
from zhihu.api_endpoints import FAV_URL
from zhihu.cilent import ZhihuClient
from zhihu.entity import CollectionResponse


def get_collection_page(
    collection_id: str, offset: int, limit: int
) -> CollectionResponse:
    zhihuClient = ZhihuClient()

    res = http.get(
        zhihuClient.session,
        FAV_URL.format(collection_id=collection_id),
        endpoint='zhihu.collection.page',
        params={'offset': offset, 'limit': limit},
    )

    if res.status_code == 200:
        return CollectionResponse.from_dict(res.json())
    return None


if __name__ == '__main__':
    collection_id = '908297073'
    offset = 0
    limit = 20

    collection_page = get_collection_page(collection_id, offset, limit)
    print(collection_page)
