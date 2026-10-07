"""canonical_url 规范化（SPEC 第 3 节）。

规则：scheme/host 小写、去 fragment、去尾部斜杠、去 utm_* / from / spm 查询参数、
其余参数按 key 排序（同 key 多值时按值排序）。
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 需要剔除的跟踪参数（前缀或精确匹配）
_DROP_EXACT = {"from", "spm"}
_DROP_PREFIX = ("utm_",)


def normalize_url(url: str) -> str:
    """把原始 URL 规范化为 canonical_url。"""
    if not url or not url.strip():
        return ""

    url = url.strip()
    parts = urlsplit(url)

    scheme = parts.scheme.lower()
    host = parts.netloc.lower()
    # 去掉 fragment
    fragment = ""

    # 路径：去尾部斜杠（保留空路径；根路径 "/" 变空）
    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or ""

    # 查询参数：剔除跟踪参数，其余按 (key, value) 排序
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _DROP_EXACT and not k.lower().startswith(_DROP_PREFIX)
    ]
    kept.sort()
    query = urlencode(kept)

    return urlunsplit((scheme, host, path, query, fragment))
