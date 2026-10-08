"""AtCoder（atcoder.jp/contests）—— method=http，Upcoming 表格服务端渲染。

时间为带 +0900 偏移的 JST 时间戳，精确换算为 Asia/Shanghai 后取日期；
Duration（HH:MM）换算 contest_end。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import base_join, clean_text, fetch_text, make_soup

DEFAULT_URL = "https://atcoder.jp/contests"
_JST = timezone(timedelta(hours=9))
_DT = re.compile(r"(20\d{2}-\d{2}-\d{2}) (\d{2}):(\d{2}):(\d{2})\+0900")
_DUR = re.compile(r"^(\d{2}):(\d{2})$")


class AtCoderSource(BaseSource):
    source_id = "atcoder"
    name = "AtCoder"
    method = "http"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        html = await fetch_text(url)
        items = self.parse(html, base_url=url)
        if not items:
            raise SourceError("AtCoder Upcoming 表解析为 0 条，可能页面改版")
        return items

    def parse(self, html: str, *, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
        soup = make_soup(html)
        box = soup.select_one("#contest-table-upcoming") or soup
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for tr in box.select("tbody tr"):
            a = tr.select_one("a[href^='/contests/']")
            time_el = tr.select_one("time.fixtime-full")
            if a is None or time_el is None:
                continue
            title = clean_text(a.get_text())
            link = base_join(base_url, a["href"])
            if not title or link in seen:
                continue
            seen.add(link)

            contest_start = contest_end = None
            md = _DT.search(time_el.get_text() or "")
            if md:
                start_dt = datetime.strptime(md.group(1) + " " + md.group(2) + ":" + md.group(3), "%Y-%m-%d %H:%M").replace(tzinfo=_JST)
                contest_start = start_dt.strftime("%Y-%m-%d")
                tds = tr.select("td")
                dur = None
                if len(tds) >= 3:
                    mdu = _DUR.match(clean_text(tds[2].get_text()))
                    if mdu:
                        dur = timedelta(hours=int(mdu.group(1)), minutes=int(mdu.group(2)))
                end_dt = start_dt + (dur or timedelta(hours=2))
                contest_end = end_dt.strftime("%Y-%m-%d")

            tags = ["AtCoder"]
            if len(tr.select("td")) >= 4:
                rated = clean_text(tr.select("td")[3].get_text())
                if rated:
                    tags.append("Rated " + rated)

            out.append(
                {
                    "title": title,
                    "url": link,
                    "category": "算法竞赛",
                    "reg_start": None,
                    "reg_deadline": None,
                    "contest_start": contest_start,
                    "contest_end": contest_end,
                    "organizer": "AtCoder",
                    "tags": tags,
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": None,
                    "requirements": None,
                    "summary": None,
                }
            )
        return out


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.atcoder
    import asyncio

    async def _main() -> None:
        try:
            for it in await AtCoderSource().fetch():
                print(it["title"][:40], "|", it["contest_start"], "→", it["contest_end"], "|", it["tags"])
        except SourceError as e:
            print("SourceError:", e)

    asyncio.run(_main())
