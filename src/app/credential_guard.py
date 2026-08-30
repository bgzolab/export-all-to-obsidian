"""导出前的凭证验活与提醒。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Literal

import click
import requests

from app.cookies import CookiesConfigError
from bangumi.api_endpoints import USER_CURRENT as BANGUMI_USER_CURRENT
from bangumi.client import BangumiClient
from bilibili.api_endpoints import BILIBILI_FAV_URL
from bilibili.cilent import BilibiliClient
from cnblog.api_endpoints import USER as CNBLOG_USER
from cnblog.client import CnblogClient
from qireader.api_endpoints import READ_LATER as QIREADER_READ_LATER
from qireader.cilent import QiReaderClient
from twitter.api_endpoints import TWITTER_LIKES_PATH
from twitter.client import TwitterClient
from twitter.like import build_likes_params
from v2ex.api_endpoints import V2EX_FAV
from v2ex.cilent import V2exClient
from weibo.api_endpoints import WEIBO_LIKE_URL
from weibo.cilent import WeiboClient
from zhihu.api_endpoints import FAV_URL as ZHIHU_FAV_URL
from zhihu.cilent import ZhihuClient


ProbeStatus = Literal["valid", "invalid", "unknown"]


@dataclass(frozen=True)
class CredentialProbeResult:
    module: str
    status: ProbeStatus
    reason: str

    @classmethod
    def valid(cls, module: str, reason: str = "") -> "CredentialProbeResult":
        return cls(module=module, status="valid", reason=reason)

    @classmethod
    def invalid(cls, module: str, reason: str) -> "CredentialProbeResult":
        return cls(module=module, status="invalid", reason=reason)

    @classmethod
    def unknown(cls, module: str, reason: str) -> "CredentialProbeResult":
        return cls(module=module, status="unknown", reason=reason)


def _http_failure_reason(response: requests.Response) -> str:
    return f"HTTP {response.status_code}"


def _telegram_chat_id() -> str | None:
    return os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_BOT_CHAT_ID")


def notify_invalid_credentials(results: list[CredentialProbeResult]) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = _telegram_chat_id()
    if not token or not chat_id or not results:
        return False

    lines = ["export-to-obsidian 凭证失效提醒"]
    for result in results:
        lines.append(f"- {result.module}: {result.reason}")

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": "\n".join(lines),
            "disable_web_page_preview": True,
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    return bool(payload.get("ok"))


def run_with_credential_guard(
    module: str,
    probe: Callable[[], CredentialProbeResult],
    export_action: Callable[[], None],
) -> bool:
    result = probe()
    if result.status == "invalid":
        click.echo(f"{module} 凭证已失效: {result.reason}，跳过导出")
        try:
            sent = notify_invalid_credentials([result])
            if sent:
                click.echo(f"{module} 凭证失效提醒已发送到 Telegram")
        except requests.RequestException as exc:
            click.echo(f"Telegram 提醒发送失败: {exc}")
        return False

    if result.status == "unknown":
        click.echo(f"{module} 凭证验活未确认: {result.reason}，继续尝试导出")

    export_action()
    return True


def probe_bangumi_credentials() -> CredentialProbeResult:
    module = "bangumi"
    try:
        client = BangumiClient()
        response = client.session.get(BANGUMI_USER_CURRENT)
    except ValueError as exc:
        return CredentialProbeResult.invalid(module, str(exc))
    except requests.RequestException as exc:
        return CredentialProbeResult.unknown(module, f"验活请求失败: {exc}")

    if response.status_code == 401:
        return CredentialProbeResult.invalid(module, "BGM_ACCESS_TOKEN 已过期或无效")
    if response.status_code != 200:
        return CredentialProbeResult.unknown(module, _http_failure_reason(response))

    try:
        payload = response.json()
    except (ValueError, TypeError, AttributeError) as exc:
        return CredentialProbeResult.unknown(module, f"响应解析失败: {exc}")
    if not isinstance(payload, dict):
        return CredentialProbeResult.unknown(module, "响应解析失败: 非 JSON 对象")
    if payload.get("username"):
        return CredentialProbeResult.valid(module)
    return CredentialProbeResult.invalid(module, "BGM_ACCESS_TOKEN 未返回有效用户信息")


def probe_cnblog_credentials() -> CredentialProbeResult:
    module = "cnblog"
    try:
        client = CnblogClient()
        response = client.session.get(CNBLOG_USER)
    except ValueError as exc:
        return CredentialProbeResult.invalid(module, str(exc))
    except requests.RequestException as exc:
        return CredentialProbeResult.unknown(module, f"验活请求失败: {exc}")

    if response.status_code in {401, 403}:
        return CredentialProbeResult.invalid(module, "CNBLOG_ACCESS_TOKEN 已过期或无效")
    if response.status_code != 200:
        return CredentialProbeResult.unknown(module, _http_failure_reason(response))
    return CredentialProbeResult.valid(module)


def probe_qireader_credentials(tag: str) -> CredentialProbeResult:
    module = "qireader"
    try:
        client = QiReaderClient()
        response = client.session.get(
            QIREADER_READ_LATER + tag,
            params={
                "articleOrder": 0,
                "count": 1,
                "id": tag,
                "unreadOnly": "False",
                "olderThan": None,
            },
        )
    except CookiesConfigError as exc:
        raise click.ClickException(f"配置缺失: {exc}")
    except ValueError as exc:
        return CredentialProbeResult.invalid(module, str(exc))
    except requests.RequestException as exc:
        return CredentialProbeResult.unknown(module, f"验活请求失败: {exc}")

    if response.status_code in {401, 403}:
        return CredentialProbeResult.invalid(module, "qireader Cookie 已过期或无效")
    if response.status_code != 200:
        return CredentialProbeResult.unknown(
            module,
            f"探针返回 {_http_failure_reason(response)}，可能是标签无效或服务异常",
        )

    try:
        payload = response.json()
    except (ValueError, TypeError, AttributeError) as exc:
        return CredentialProbeResult.unknown(module, f"响应解析失败: {exc}")
    if not isinstance(payload, dict):
        return CredentialProbeResult.unknown(module, "响应解析失败: 非 JSON 对象")
    if "result" in payload:
        return CredentialProbeResult.valid(module)
    return CredentialProbeResult.unknown(module, "探针响应缺少 result 字段")


def probe_v2ex_credentials() -> CredentialProbeResult:
    module = "v2ex"
    try:
        client = V2exClient()
        response = client.session.get(V2EX_FAV, params={"p": 1}, allow_redirects=False)
    except CookiesConfigError as exc:
        raise click.ClickException(f"配置缺失: {exc}")
    except ValueError as exc:
        return CredentialProbeResult.invalid(module, str(exc))
    except requests.RequestException as exc:
        return CredentialProbeResult.unknown(module, f"验活请求失败: {exc}")

    if response.status_code in {301, 302, 303, 307, 308}:
        return CredentialProbeResult.invalid(module, "v2ex Cookie 已过期或未登录")
    if response.status_code in {401, 403}:
        return CredentialProbeResult.invalid(module, "V2EX 凭证已过期或无效")
    if response.status_code != 200:
        return CredentialProbeResult.unknown(module, _http_failure_reason(response))
    return CredentialProbeResult.valid(module)


def probe_twitter_credentials() -> CredentialProbeResult:
    module = "twitter"
    # 注意：此处对 Likes 接口发起一次真实请求用于验活，会消耗 X 的限流配额。
    # 每次导出启动都会少掉一条配额，排障时留意为何一启动即触发 429。
    try:
        client = TwitterClient()
        response = client.session.get(
            TWITTER_LIKES_PATH,
            params=build_likes_params(client.user_id, 1),
            timeout=30,
        )
    except CookiesConfigError as exc:
        raise click.ClickException(f"配置缺失: {exc}")
    except ValueError as exc:
        return CredentialProbeResult.invalid(module, str(exc))
    except requests.RequestException as exc:
        return CredentialProbeResult.unknown(module, f"验活请求失败: {exc}")

    if response.status_code in {401, 403}:
        return CredentialProbeResult.invalid(module, "twitter Cookie 已过期或无效")
    if response.status_code != 200:
        return CredentialProbeResult.unknown(module, _http_failure_reason(response))

    try:
        payload = response.json()
    except (ValueError, TypeError, AttributeError) as exc:
        return CredentialProbeResult.unknown(module, f"响应解析失败: {exc}")
    if not isinstance(payload, dict):
        return CredentialProbeResult.unknown(module, "响应解析失败: 非 JSON 对象")
    if payload.get("data"):
        return CredentialProbeResult.valid(module)
    return CredentialProbeResult.invalid(
        module,
        "twitter Cookie 已过期或接口未返回有效登录态",
    )


def probe_zhihu_credentials(collection: str) -> CredentialProbeResult:
    module = "zhihu"
    try:
        client = ZhihuClient()
        response = client.session.get(
            ZHIHU_FAV_URL.format(collection_id=collection),
            params={"offset": 0, "limit": 1},
        )
    except CookiesConfigError as exc:
        raise click.ClickException(f"配置缺失: {exc}")
    except ValueError as exc:
        return CredentialProbeResult.invalid(module, str(exc))
    except requests.RequestException as exc:
        return CredentialProbeResult.unknown(module, f"验活请求失败: {exc}")

    if response.status_code in {401, 403}:
        return CredentialProbeResult.invalid(module, "zhihu Cookie 已过期或无效")
    if response.status_code != 200:
        return CredentialProbeResult.unknown(
            module,
            f"探针返回 {_http_failure_reason(response)}，可能是收藏夹不可访问或服务异常",
        )
    return CredentialProbeResult.valid(module)


def probe_weibo_credentials(uid: int) -> CredentialProbeResult:
    module = "weibo"
    try:
        client = WeiboClient()
        response = client.session.get(
            WEIBO_LIKE_URL,
            params={"page": 1, "uid": uid, "with_total": True},
        )
    except CookiesConfigError as exc:
        raise click.ClickException(f"配置缺失: {exc}")
    except ValueError as exc:
        return CredentialProbeResult.invalid(module, str(exc))
    except requests.RequestException as exc:
        return CredentialProbeResult.unknown(module, f"验活请求失败: {exc}")

    if response.status_code in {401, 403}:
        return CredentialProbeResult.invalid(module, "weibo Cookie 已过期或无效")
    if response.status_code != 200:
        return CredentialProbeResult.unknown(module, _http_failure_reason(response))

    try:
        payload = response.json()
    except (ValueError, TypeError, AttributeError) as exc:
        return CredentialProbeResult.unknown(module, f"响应解析失败: {exc}")
    if not isinstance(payload, dict):
        return CredentialProbeResult.unknown(module, "响应解析失败: 非 JSON 对象")
    if payload.get("ok") == 1:
        return CredentialProbeResult.valid(module)
    return CredentialProbeResult.invalid(module, "weibo Cookie 已过期或接口未返回有效登录态")


def probe_bilibili_credentials(fid: int) -> CredentialProbeResult:
    module = "bilibili"
    try:
        client = BilibiliClient()
        response = client.session.get(
            BILIBILI_FAV_URL,
            params={
                "keyword": "",
                "media_id": fid,
                "order": "mtime",
                "platform": "web",
                "pn": 1,
                "ps": 1,
                "tid": 0,
                "type": 0,
                "web_location": 333.1387,
            },
        )
    except CookiesConfigError as exc:
        raise click.ClickException(f"配置缺失: {exc}")
    except ValueError as exc:
        return CredentialProbeResult.invalid(module, str(exc))
    except requests.RequestException as exc:
        return CredentialProbeResult.unknown(module, f"验活请求失败: {exc}")

    if response.status_code in {401, 403}:
        return CredentialProbeResult.invalid(module, "bilibili Cookie 已过期或无效")
    if response.status_code != 200:
        return CredentialProbeResult.unknown(
            module,
            f"探针返回 {_http_failure_reason(response)}，可能是收藏夹不可访问或服务异常",
        )

    try:
        payload = response.json()
    except (ValueError, TypeError, AttributeError) as exc:
        return CredentialProbeResult.unknown(module, f"响应解析失败: {exc}")
    if not isinstance(payload, dict):
        return CredentialProbeResult.unknown(module, "响应解析失败: 非 JSON 对象")
    if payload.get("code") == 0:
        return CredentialProbeResult.valid(module)
    if payload.get("code") == -101:
        return CredentialProbeResult.invalid(module, "bilibili Cookie 已过期或未登录")
    return CredentialProbeResult.unknown(
        module,
        f"探针返回 code={payload.get('code')} message={payload.get('message')}",
    )