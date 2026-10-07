"""CCF 算法能力大赛（cacc.ccf.org.cn）解析器 —— method=http（候选源，enabled=false）。

实测（2026-10）：该站是 Vue SPA 空壳（HTML 仅 685 字节、<div id="app"> 空），
纯 HTTP 拿不到赛事列表（站内仅见 /prod-api/modules/* 私有接口，无公开列表 API）。
简单实现：抓首页 → 若检测到 SPA 空壳则抛 SourceError 说明原因（候选源，默认不启用）；
若日后改回服务端渲染，则按 a 链接 + 竞赛关键词尽力解析。
"""
from __future__ import annotations

from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import base_join, clean_text, fetch_text, make_soup

DEFAULT_URL = "https://cacc.ccf.org.cn/"
KEEP_KEYWORDS = ("大赛", "竞赛", "比赛", "报名", "初赛", "决赛", "CACC")


class CaccSource(BaseSource):
    source_id = "ccf_cacc"
    name = "CCF算法能力大赛"
    method = "http"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        html = await fetch_text(url)
        items = self.parse(html, base_url=url)
        if not items:
            raise SourceError(
                "CACC 官网是前端单页应用（SPA），纯 HTTP 无法获取赛事列表；"
                "启用该源前需改造成 Playwright 方案（候选源，默认 enabled=false）"
            )
        return items

    def parse(self, html: str, *, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
        # SPA 空壳检测：没有可解析的超文本列表
        soup = make_soup(html)
        mount = soup.find(id="app")
        if mount is not None and not mount.find_all("a", href=True):
            return []  # fetch() 会转成带原因的 SourceError
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            title = clean_text(a.get_text())
            if not title or not any(k in title for k in KEEP_KEYWORDS):
                continue
            url = base_join(base_url, a["href"])
            if url in seen:
                continue
            seen.add(url)
            out.append(
                {
                    "title": title,
                    "url": url,
                    "category": "算法竞赛",
                    "reg_start": None,
                    "reg_deadline": None,
                    "contest_start": None,
                    "contest_end": None,
                    "organizer": "CCF",
                    "tags": ["CACC"],
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": None,
                    "requirements": None,
                    "summary": None,
                }
            )
        return out


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.cacc
    import asyncio

    async def _main() -> None:
        try:
            for it in await CaccSource().fetch():
                print(it["title"], "|", it["url"])
        except SourceError as e:
            print("SourceError:", e)

    asyncio.run(_main())
