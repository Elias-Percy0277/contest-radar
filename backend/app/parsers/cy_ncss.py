"""中国国际大学生创新大赛（原互联网+，cy.ncss.cn）解析器 —— method=http。

实测（2026-10）：首页服务端渲染，"大赛动态"栏目条目：
  <li class="dynamics-block">
    <a href="/information/{id}" class="dynamics-img">…</a>
    <h2 class="dynamics-text-title">关于加强中国国际大学生创新大赛（2026）…的通知</h2>
    <p class="dynamics-text-time">2026-09-04</p>
  </li>
日期为发布日期（写入 summary，不冒充比赛日期）。
"""
from __future__ import annotations

from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import base_join, clean_text, fetch_text, make_soup

DEFAULT_URL = "https://cy.ncss.cn/"
ORGANIZER = "教育部等部委"
KEEP_KEYWORDS = ("大赛", "创新大赛", "通知", "赛道", "命题", "报名", "评审", "专家")


class CyNcssSource(BaseSource):
    source_id = "cy_ncss"
    name = "中国国际大学生创新大赛"
    method = "http"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        html = await fetch_text(url)
        items = self.parse(html, base_url=url)
        if not items:
            raise SourceError("互联网+首页未解析到大赛动态条目，页面可能改版")
        return items

    def parse(self, html: str, *, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
        soup = make_soup(html)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for li in soup.select("li.dynamics-block"):
            a = li.select_one("a.dynamics-img[href], a[href*='/information/']")
            h2 = li.select_one(".dynamics-text-title")
            if not a or not h2:
                continue
            title = clean_text(h2.get_text())
            if not title or not any(k in title for k in KEEP_KEYWORDS):
                continue
            url = base_join(base_url, a["href"])
            if url in seen:
                continue
            seen.add(url)
            time_el = li.select_one(".dynamics-text-time")
            pub = clean_text(time_el.get_text()) if time_el else ""
            out.append(
                {
                    "title": title,
                    "url": url,
                    "category": "综合学科",
                    "reg_start": None,
                    "reg_deadline": None,
                    "contest_start": None,
                    "contest_end": None,
                    "organizer": ORGANIZER,
                    "tags": ["国家级", "创新大赛"],
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": "面向全国大学生",
                    "requirements": None,
                    "summary": f"官方动态（发布于 {pub}）" if pub else None,
                }
            )
        return out


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.cy_ncss
    import asyncio

    async def _main() -> None:
        for it in await CyNcssSource().fetch():
            print(it["title"], "|", it["url"])

    asyncio.run(_main())
