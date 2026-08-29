"""统一加载 Netscape 格式 cookies.txt 并提取指定域名的 Cookie 请求头。

文件格式为 TAB 分隔的 7 列：domain、flag、path、secure、expiry、name、value。
解析规则：
- 跳过空行、普通 ``#`` 注释行；以 ``#HttpOnly_`` 开头的行视为有效数据行（剥掉该前缀后解析）。
- 每行字段数不足 7 时直接跳过，不中断整个文件解析。
- cookie 域以 ``.`` 开头时剥掉前导点；第 2 列 ``flag`` 为 TRUE（或 ``1``）时做后缀匹配，
  FALSE 时仅做精确域名匹配（host-only，不发送到子域）。
- 同名 Cookie 去重，保留文件中最后一条的值（首次出现的顺序位置不变）。
- 同一域名内按文件行序拼接为 ``name1=value1; name2=value2`` 形式的请求头字符串。

配置读取优先级：click 根上下文 ``ctx.obj["cookies_file"]``（由顶层 ``--cookies-file``
注入）> 环境变量 ``COOKIES``。无模块级全局可变状态。
"""

import os

import click


class CookiesConfigError(ValueError):
    """cookies.txt 配置缺失（环境变量未设、文件不存在或域名无匹配）。"""


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


def load_cookie_header(cookies_file: str, domains: tuple[str, ...]) -> str:
    """按域名匹配从 cookies.txt 提取 Cookie，按文件行序去重拼接请求头。"""
    parts: dict[str, str] = {}
    with open(cookies_file, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.rstrip("\r\n")
            if stripped.startswith("#HttpOnly_"):
                stripped = stripped[len("#HttpOnly_"):]
            elif stripped.startswith("#"):
                continue
            if not stripped.strip():
                continue
            fields = stripped.split("\t")
            if len(fields) < 7:
                continue
            cookie_domain = fields[0].strip()
            flag = fields[1].strip().upper()
            name = fields[5].strip()
            value = fields[6]
            if cookie_domain.startswith("."):
                cookie_domain = cookie_domain[1:]
            matched = any(
                cookie_domain == d
                or (flag != "FALSE" and cookie_domain.endswith("." + d))
                for d in domains
            )
            if matched:
                parts[name] = value
    return "; ".join(f"{name}={value}" for name, value in parts.items())


def get_cookie_header(
    domains: tuple[str, ...], cookies_file: str | None = None
) -> str:
    """对外统一入口：返回指定域名的 Cookie 请求头字符串。"""
    path = cookies_file or resolve_cookies_file()
    if not os.path.isfile(path):
        raise CookiesConfigError(f"Cookies file not found: {path}")
    header = load_cookie_header(path, domains)
    if not header:
        raise CookiesConfigError(f"No cookies found for domain {domains!r} in {path}")
    return header
