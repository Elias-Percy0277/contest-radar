"""中国大学生计算机设计大赛（jsjds.blcu.edu.cn）解析器 —— method=http。

实测（2026-10）：服务端渲染，通知列表条目：
  <li><a href="info/1041/2944.htm"><span><i>09-18</i>.2026</span><h3>…通知</h3></a></li>
日期格式为 "MM-DD.YYYY"（需重排为 YYYY-MM-DD）。
"""
from __future__ import annotations

import re
from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import base_join, clean_text, fetch_text, find_dates, make_soup, to_iso

DEFAULT_URL = "https://jsjds.blcu.edu.cn/"
ORGANIZER = "教育部高校计算机类专业教学指导委员会等"
RE_MDY = re.compile(r"(\d{1,2})\s*-\s*(\d{1,2})\s*\.\s*(20\d{2})")
KEEP_KEYWORDS = ("大赛", "通知", "公告", "竞赛", "设计大赛", "报名", "获奖")


class JsjdsSource(BaseSource):
    source_id = "jsjds"
    name = "中国大学生计算机设计大赛"
    method = "http"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        html = await fetch_text(url)
        items = self.parse(html, base_url=url)
        if not items:
            raise SourceError("计算机设计大赛首页未解析到通知条目，页面可能改版")
        return items

    def parse(self, html: str, *, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
        soup = make_soup(html)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for a in soup.select("li a[href*='info/']"):
            h3 = a.find("h3")
            if not h3:
                continue
            title = clean_text(h3.get_text())
            if not title or not any(k in title for k in KEEP_KEYWORDS):
                continue
            url = base_join(base_url, a["href"])
            if url in seen:
                continue
            seen.add(url)
            # "09-18.2026" → 2026-09-18
            publish = None
            m = RE_MDY.search(clean_text(a.get_text()))
            if m:
                try:
                    from datetime import date as _d

                    publish = _d(int(m.group(3)), int(m.group(1)), int(m.group(2)))
                except ValueError:
                    publish = None
            # 标题里如有完整日期（如"2026年7月…"）尽力提取为比赛时间
            title_dates = find_dates(title)
            out.append(
                {
                    "title": title,
                    "url": url,
                    "category": "应用与开发",
                    "reg_start": None,
                    "reg_deadline": None,
                    "contest_start": to_iso(title_dates[0]) if title_dates else None,
                    "contest_end": to_iso(title_dates[1]) if len(title_dates) > 1 else None,
                    "organizer": ORGANIZER,
                    "tags": ["国家级", "计算机设计大赛"],
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": "面向全国大学生",
                    "requirements": None,
                    "summary": f"官方通知（发布于 {publish.isoformat()}）" if publish else None,
                }
            )
        return out


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.jsjds
    import asyncio

    async def _main() -> None:
        for it in await JsjdsSource().fetch():
            print(it["title"], "|", it["contest_start"], "|", it["url"])

    asyncio.run(_main())
