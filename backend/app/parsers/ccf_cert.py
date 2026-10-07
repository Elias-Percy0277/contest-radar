"""CCF 认证总览页（www.ccf.org.cn/Activities/Certification/）解析器 —— method=http（候选源）。

实测（2026-10）：服务端渲染，页面主体是认证项目卡片列表：
  <li><h3><a href="https://csp.ccf.org.cn/" class="tj-titcolor">CSP</a></h3> 项目简介…</li>
（CSP / PTA / GESP / LMCC 四项）。简单实现：把每个认证项目转成一条 ContestRaw。
"""
from __future__ import annotations

from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import base_join, clean_text, fetch_text, make_soup

DEFAULT_URL = "https://www.ccf.org.cn/Activities/Certification/"
FULL_NAMES = {
    "CSP": "CCF计算机软件能力认证（CSP）",
    "PTA": "CCF编程培训师资认证（PTA）",
    "GESP": "CCF编程能力等级认证（GESP）",
    "LMCC": "CCF大模型能力认证（LMCC）",
}


class CcfCertSource(BaseSource):
    source_id = "ccf_cert"
    name = "CCF认证"
    method = "http"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        html = await fetch_text(url)
        items = self.parse(html, base_url=url)
        if not items:
            raise SourceError("CCF 认证页未解析到认证项目卡片，页面可能改版")
        return items

    def parse(self, html: str, *, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
        soup = make_soup(html)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for h3 in soup.select("h3 a.tj-titcolor, h3 a[href]"):
            short = clean_text(h3.get_text()).upper()
            href = h3.get("href") or ""
            if not short or not href.startswith("http") or href in seen:
                continue
            # 只要认证项目缩写（CSP/PTA/GESP/LMCC…），过滤导航杂项
            if not re_is_short_name(short):
                continue
            seen.add(href)
            li = h3.find_parent("li") or h3
            desc = clean_text(li.get_text()).replace(short, "", 1)[:160]
            out.append(
                {
                    "title": FULL_NAMES.get(short, f"CCF {short} 认证"),
                    "url": base_join(base_url, href),
                    "category": "认证考试",
                    "reg_start": None,
                    "reg_deadline": None,
                    "contest_start": None,
                    "contest_end": None,
                    "organizer": "CCF",
                    "tags": ["认证项目", short],
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": None,
                    "requirements": None,
                    "summary": desc or None,
                }
            )
        return out


def re_is_short_name(s: str) -> bool:
    """缩写形如 2-6 位大写字母（CSP/PTA/GESP/LMCC），用于过滤导航链接。"""
    import re

    return bool(re.fullmatch(r"[A-Z]{2,6}", s))


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.ccf_cert
    import asyncio

    async def _main() -> None:
        for it in await CcfCertSource().fetch():
            print(it["title"], "|", it["url"])

    asyncio.run(_main())
