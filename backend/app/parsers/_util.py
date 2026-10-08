"""解析器公共小工具：HTTP 抓取（带 UA）、相对时间换算、日期正则。

只被 app/parsers/ 下的解析器使用，不属于对外契约。
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from bs4 import BeautifulSoup, FeatureNotFound

from app.fetcher.base import SourceError

# 统一浏览器 UA，避免被简单反爬拦截
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
SH_TZ = ZoneInfo("Asia/Shanghai")  # SPEC 规定状态推导统一用上海时区


async def fetch_text(url: str, *, timeout: float = 30.0) -> str:
    """带 UA 抓取页面文本；失败抛 SourceError。编码按响应头/meta 自动判定，兜底 utf-8。"""
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            resp = await client.get(url)
    except httpx.HTTPError as exc:
        raise SourceError(f"请求失败：{url}（{exc.__class__.__name__}: {exc}）") from exc
    if resp.status_code != 200:
        raise SourceError(f"请求失败：{url} 返回 HTTP {resp.status_code}")
    # httpx 依据响应头判定编码；头部缺失时扫 meta charset，再兜底 utf-8
    encoding = resp.charset_encoding
    if not encoding:
        m = re.search(rb'charset=["\']?([A-Za-z0-9_-]+)', resp.content[:4096], re.I)
        encoding = m.group(1).decode("ascii", "ignore") if m else "utf-8"
    try:
        text = resp.content.decode(encoding, errors="replace")
    except (LookupError, UnicodeDecodeError):
        text = resp.content.decode("utf-8", errors="replace")
    # 阿里云 WAF 等按 TLS 指纹拦截 httpx：返回 200 但正文是 JS 挑战页 → curl 重试
    if "aliyun_waf" in text or "acw_sc__v2" in text:
        try:
            alt = await _curl_fetch(url)
            if "aliyun_waf" not in alt and "acw_sc__v2" not in alt:
                return alt
        except SourceError:
            pass  # curl 不可用/失败时退回挑战页原文，由解析器判 0 条后报 SourceError
    return text


async def fetch_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> Any:
    """GET/POST 抓取 JSON 接口（带 UA）；失败抛 SourceError。

    json_body 非空时为 POST（如 LeetCode GraphQL），否则为 GET（如天池列表）。
    """
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": UA, "Accept": "application/json, text/plain, */*"},
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            if json_body is not None:
                resp = await client.post(url, json=json_body, params=params)
            else:
                resp = await client.get(url, params=params)
    except httpx.HTTPError as exc:
        raise SourceError(f"接口请求失败：{url}（{exc.__class__.__name__}: {exc}）") from exc
    if resp.status_code != 200:
        raise SourceError(f"接口请求失败：{url} 返回 HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise SourceError(f"接口返回非 JSON：{url}（{exc}）") from exc


def make_soup(html: str) -> BeautifulSoup:
    """构造 BeautifulSoup：优先 lxml（快），环境缺 lxml 二进制时回退内置 html.parser。"""
    try:
        return BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        return BeautifulSoup(html, "html.parser")


async def _curl_fetch(url: str) -> str:
    """curl 子进程抓取（带 UA）。个别站点（如 ccf.org.cn 的阿里云 WAF）按 TLS 指纹拦 httpx，
    curl 的 OpenSSL 指纹可过；Windows 10+/macOS/Linux 均自带 curl，缺失时调用方自行兜底。"""
    import asyncio as _asyncio

    proc = await _asyncio.create_subprocess_exec(
        "curl", "-sL", "--max-time", "30", "-A", UA, url,
        stdout=_asyncio.subprocess.PIPE, stderr=_asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    if proc.returncode != 0 or not out:
        raise SourceError(f"curl 抓取失败：{url}（exit={proc.returncode}）")
    return out.decode("utf-8", errors="replace")


def today_sh() -> date:
    """当前 Asia/Shanghai 日期（相对时间换算基准）。"""
    return datetime.now(SH_TZ).date()


# ---------------- 日期/时间解析 ----------------

# 2026年9月13日 / 2026-09-13 / 2026.9.13
RE_CN_DATE = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?")
RE_ISO_DATE = re.compile(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})")


def find_dates(text: str) -> list[date]:
    """从文本里抓所有形如 2026年9月13日 / 2026-09-13 的日期（用于尽力提取考试时间）。"""
    out: list[date] = []
    for rex in (RE_CN_DATE, RE_ISO_DATE):
        for y, m, d in rex.findall(text):
            try:
                out.append(date(int(y), int(m), int(d)))
            except ValueError:
                continue
    return out


def to_iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def parse_relative_time(text: str, *, base: date | None = None) -> date | None:
    """牛客风格相对时间换算成具体日期（Asia/Shanghai）。

    支持：今天 / 明天 / 后天 / 昨天 / N天后 / N天前 / N小时后（按当天算）/ N分钟前（按当天算）。
    换算不了返回 None，调用方据此把 contest_start 置 null。
    """
    t = re.sub(r"\s+", "", text or "")
    if not t:
        return None
    today = base or today_sh()
    if "今天" in t or "即将" in t or "分钟后" in t or "小时后" in t or "分钟前" in t or "小时前" in t:
        return today
    if "明天" in t:
        return today + timedelta(days=1)
    if "后天" in t:
        return today + timedelta(days=2)
    if "昨天" in t:
        return today - timedelta(days=1)
    m = re.search(r"(\d+)天后", t)
    if m:
        return today + timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)天前", t)
    if m:
        return today - timedelta(days=int(m.group(1)))
    m = re.search(r"(\d+)周后", t)
    if m:
        return today + timedelta(weeks=int(m.group(1)))
    # 已经是具体日期则直接解析
    ds = find_dates(t)
    return ds[0] if ds else None


def base_join(base_url: str, href: str) -> str:
    """相对链接补全为绝对 URL。"""
    if href.startswith(("http://", "https://")):
        return href
    return str(httpx.URL(base_url).join(href))


def clean_text(s: Any) -> str:
    """压缩空白并去掉常见 HTML 实体残留。"""
    if not s:
        return ""
    import html as _html

    return _html.unescape(re.sub(r"\s+", " ", str(s))).strip()


def playwright_launch_error(exc: Exception) -> str:
    """把 chromium 启动失败翻译成人话：区分"内核缺失"与"其它启动失败"。

    内核缺失的典型场景：多个虚拟环境装了不同版本的 playwright，它们共享
    ~/Library/Caches/ms-playwright，新版本安装时会把旧版本内核当垃圾回收掉。
    """
    msg = str(exc)
    if "Executable doesn't exist" in msg or "playwright install" in msg:
        return (
            "chromium 内核缺失：请在项目目录运行 "
            "PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright "
            ".venv/bin/python -m playwright install chromium（约150MB，一次性；"
            "多个虚拟环境请保持 playwright 版本一致，避免内核被新版本回收）"
        )
    return f"chromium 启动失败：{msg[:200]}"
