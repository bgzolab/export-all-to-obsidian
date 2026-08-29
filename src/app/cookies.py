"""统一加载 Netscape 格式 cookies.txt 并提取指定域名的 Cookie 请求头。

文件格式为 TAB 分隔的 7 列：domain、flag、path、secure、expiry、name、value。
解析规则：
- 跳过空行、普通 ``#`` 注释行；以 ``#HttpOnly_`` 开头的行视为有效数据行（剥掉该前缀后解析）。
- 每行字段数不足 7 时直接跳过，不中断整个文件解析。
- cookie 域以 ``.`` 开头时剥掉前导点后做后缀匹配；同一域名内按文件行序拼接为
  ``name1=value1; name2=value2`` 形式的请求头字符串。
"""

import os

_explicit_path: str | None = None


def set_explicit_cookies_file(path: str | None) -> None:
    """记录 CLI 顶层参数 ``--cookies-file`` 显式传入的文件路径。"""
    global _explicit_path
    _explicit_path = path


def resolve_cookies_file() -> str:
    """返回 cookies.txt 路径：优先显式参数，否则读环境变量 COOKIES。"""
    path = _explicit_path or os.getenv("COOKIES")
    if not path:
        raise ValueError(
            "COOKIES environment variable is not set and no --cookies-file provided."
        )
    return path


def load_cookie_header(cookies_file: str, domains: tuple[str, ...]) -> str:
    """按域名后缀匹配从 cookies.txt 提取 Cookie 并按文件行序拼接请求头。"""
    parts: list[str] = []
    with open(cookies_file, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip("\n")
            if stripped.startswith("#HttpOnly_"):
                stripped = stripped[len("#HttpOnly_"):]
            elif stripped.startswith("#"):
                continue
            if not stripped.strip():
                continue
            fields = stripped.split("\t")
            if len(fields) < 7:
                continue
            cookie_domain = fields[0]
            name = fields[5]
            value = fields[6].rstrip("\r\n")
            if cookie_domain.startswith("."):
                cookie_domain = cookie_domain[1:]
            if any(
                cookie_domain == d or cookie_domain.endswith("." + d)
                for d in domains
            ):
                parts.append(f"{name}={value}")
    return "; ".join(parts)


def get_cookie_header(
    domains: tuple[str, ...], cookies_file: str | None = None
) -> str:
    """对外统一入口：返回指定域名的 Cookie 请求头字符串。"""
    path = cookies_file or resolve_cookies_file()
    if not os.path.isfile(path):
        raise ValueError(f"Cookies file not found: {path}")
    header = load_cookie_header(path, domains)
    if not header:
        raise ValueError(f"No cookies found for domain {domains!r} in {path}")
    return header
