"""统一加载 Netscape 格式 cookies.txt 并提取指定域名的 Cookie 请求头。

文件格式为 TAB 分隔的 7 列：domain、flag、path、secure、expiry、name、value。
解析规则：
- 跳过空行、普通 ``#`` 注释行；以 ``#HttpOnly_`` 开头的行视为有效数据行（剥掉该前缀后解析）。
- 每行字段数不足 7 时直接跳过，不中断整个文件解析。
- cookie 域以 ``.`` 开头时剥掉前导点；第 2 列 ``flag`` 为 FALSE 或 ``0`` 时仅做精确
  域名匹配（host-only，不发送到子域），其余（TRUE/``1`` 等）做后缀匹配。
- 第 5 列 ``expiry`` 为非零正整数且早于当前时间时跳过该条（已过期）；``0`` 表示
  会话 Cookie，保留。
- 同一 (cookie 域, name) 去重，保留文件中最后一条的值（首次出现的顺序位置不变）；
  多域同名 Cookie 默认各自保留（如 x.com 与 twitter.com 的同名 Cookie 共存），
  也可通过 ``dedupe_by_name=True`` 按域名优先级（domains 元组顺序）去重。
- name 与 value 均做空白清理（strip），避免拼入非法的 cookie-octet。
- 同一域名内按文件行序拼接为 ``name1=value1; name2=value2`` 形式的请求头字符串。

配置读取优先级：click 根上下文 ``ctx.obj["cookies_file"]``（由顶层 ``--cookies-file``
注入）> 环境变量 ``COOKIES``。无模块级全局可变状态。
"""

import os
import time

import click


class CookiesConfigError(ValueError):
    """cookies.txt 配置缺失或数据错误（环境变量未设、文件不存在、编码错误或域名无匹配）。"""


def resolve_cookies_file() -> str:
    """返回 cookies.txt 路径：优先 click 根上下文，否则读环境变量 COOKIES。"""
    context = click.get_current_context(silent=True)
    if context is not None:
        root_obj = context.find_root().obj
        if root_obj:
            path = root_obj.get("cookies_file")
            if path:
                return path
    path = os.getenv("COOKIES")
    if not path:
        raise CookiesConfigError(
            "COOKIES environment variable is not set and no --cookies-file provided."
        )
    return path


def load_cookie_header(
    cookies_file: str,
    domains: tuple[str, ...],
    dedupe_by_name: bool = False,
) -> str:
    """按域名匹配从 cookies.txt 提取 Cookie，按文件行序去重拼接请求头。

    ``dedupe_by_name`` 为 True 时对跨域同名 Cookie 按域名优先级去重：
    ``domains`` 元组中的顺序即优先级（越靠前优先级越高），保留优先级最高
    域名的值；适用于 twitter 这类「主域 + 旧域」场景，避免同一请求头里
    出现重复同名 Cookie。
    """
    domain_priority = {d: i for i, d in enumerate(domains)}
    parts: dict[tuple[str, str], str] = {}
    deduped: dict[str, tuple[int, str]] = {}
    try:
        with open(cookies_file, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
    except OSError as exc:
        # 文件不可读 / 预检后被删除（TOCTOU）等，均转成配置错误而非裸 traceback
        raise CookiesConfigError(f"Cookies file not readable: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise CookiesConfigError(f"Cookies file encoding error: {exc}") from exc
    now = time.time()
    for line in lines:
        # 先统一 strip，容忍行首空白：保证 #HttpOnly_ 前缀检测不被前导空格破坏，
        # 否则该行会按普通数据解析，去重键的域名也因残留前缀而错乱
        stripped = line.strip()
        if stripped.startswith("#HttpOnly_"):
            stripped = stripped[len("#HttpOnly_"):]
        elif stripped.startswith("#"):
            continue
        if not stripped:
            continue
        fields = stripped.split("\t")
        if len(fields) < 7:
            continue
        cookie_domain = fields[0].strip()
        if cookie_domain.startswith("."):
            cookie_domain = cookie_domain[1:]
        flag = fields[1].strip().upper()
        expiry = fields[4].strip()
        name = fields[5].strip()
        # value 是最后一列：若其本身含 TAB，需把剩余列拼回，不能取 fields[6] 截断
        value = "\t".join(fields[6:]).strip()
        if not name:
            # 空 name 会拼出 "=value" 这类非法 Cookie 头，直接跳过
            continue
        if expiry.isdigit() and expiry != "0" and int(expiry) < now:
            continue
        # 按 domains 元组顺序取第一个命中的域名：既决定是否匹配，
        # 也作为 dedupe_by_name 的优先级依据（子域如 api.x.com 命中 x.com，
        # 应继承 x.com 的优先级，而非用 cookie_domain 本身查表）
        matched_domain = None
        for d in domains:
            if cookie_domain == d or (
                flag not in ("FALSE", "0") and cookie_domain.endswith("." + d)
            ):
                matched_domain = d
                break
        if matched_domain is not None:
            if dedupe_by_name:
                prio = domain_priority[matched_domain]
                prev = deduped.get(name)
                # <= 使同优先级（同域/同匹配域）的重复同名 Cookie 保留最后一条，
                # 与 docstring 的「保留文件中最后一条的值」一致
                if prev is None or prio <= prev[0]:
                    deduped[name] = (prio, value)
            else:
                parts[(cookie_domain, name)] = value
    if dedupe_by_name:
        return "; ".join(f"{name}={value}" for name, (_, value) in deduped.items())
    return "; ".join(f"{name}={value}" for (_, name), value in parts.items())


def get_cookie_header(
    domains: tuple[str, ...],
    cookies_file: str | None = None,
    dedupe_by_name: bool = False,
) -> str:
    """对外统一入口：返回指定域名的 Cookie 请求头字符串。"""
    path = cookies_file or resolve_cookies_file()
    # 区分「不存在」与「是目录」：isfile 对目录返回 False，
    # 一律报 not found 会误导用户以为文件不存在
    if not os.path.exists(path):
        raise CookiesConfigError(f"Cookies file not found: {path}")
    if not os.path.isfile(path):
        raise CookiesConfigError(f"Cookies file is not a regular file: {path}")
    header = load_cookie_header(path, domains, dedupe_by_name=dedupe_by_name)
    if not header:
        # 文件存在但无目标域 Cookie 属于「该平台凭证不可用」而非「整体配置缺失」：
        # 抛 ValueError 由 credential_guard 判为 invalid 走「跳过+提醒」，
        # 不复用 CookiesConfigError 的硬退出语义（与改造前行为一致）。
        raise ValueError(f"No cookies found for domain {domains!r} in {path}")
    return header
