"""DataFountain 数据科学竞赛平台（datafountain.cn/competitions）—— method=http。

页面服务端渲染：div.compt-item 列表含标题/链接/主办方/赛程（YYYY.MM.DD - YYYY.MM.DD）/奖金。
徽标 state-join（allowed 等）仅供参考；状态一律以 derive_status 按日期推导为准。
字节/腾讯等大厂冠名的数据赛常驻此平台，是该调研方向的落地兜底。
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import base_join, clean_text, fetch_text, make_soup
from app.utils.timeutil import parse_date, today_local

DEFAULT_URL = "https://www.datafountain.cn/competitions"

# 与保留清理口径对齐：结束超过该天数的历史赛不入库（否则入库即被清理，还浪费 LLM 加工）
KEEP_DAYS = 30

_DATE_RANGE = re.compile(
    r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})\s*[-–~至]\s*(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})"
)


class DataFountainSource(BaseSource):
    source_id = "datafountain"
    name = "DataFountain竞赛"
    method = "http"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        html = await fetch_text(url)
        items = self.parse(html, base_url=url)
        if not items:
            raise SourceError("DataFountain 列表页解析为 0 条，可能页面改版")
        # 新鲜度过滤：历史赛季直接丢弃（0 条在办属于正常状态，不算源故障）
        cutoff = today_local() - timedelta(days=KEEP_DAYS)
        return [
            it
            for it in items
            if it["contest_end"] is None or (parse_date(it["contest_end"]) or cutoff) >= cutoff
        ]

    def parse(self, html: str, *, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
        soup = make_soup(html)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in soup.select("div.compt-item"):
            a = item.select_one("a.compt__title") or item.select_one("a[href^='/competitions/']")
            if a is None or not a.get("href"):
                continue
            link = base_join(base_url, a["href"])
            title = clean_text(a.get_text())
            if not title or link in seen:
                continue
            seen.add(link)
            block = clean_text(item.get_text(" ", strip=True))

            organizer = None
            mo = re.search(r"organizer[：:]\s*(.{2,50}?)(?:competition date|￥|¥|$)", block)
            if mo:
                organizer = mo.group(1).strip()

            contest_start = contest_end = None
            md = _DATE_RANGE.search(block)
            if md:
                contest_start = f"{md.group(1)}-{int(md.group(2)):02d}-{int(md.group(3)):02d}"
                contest_end = f"{md.group(4)}-{int(md.group(5)):02d}-{int(md.group(6)):02d}"

            prize = None
            mp = re.search(r"(?:￥|¥)\s*[\d,]+(?:\.\d+)?万?", block)
            if mp:
                prize = mp.group(0)

            tags: list[str] = ["DataFountain"]
            type_el = item.select_one(".compt__cmpt-type")
            if type_el is not None:
                t = clean_text(type_el.get_text())
                if t:
                    tags.append(t)

            out.append(
                {
                    "title": title,
                    "url": link,
                    "category": "AI与数据科学",
                    "reg_start": None,
                    "reg_deadline": None,
                    "contest_start": contest_start,
                    "contest_end": contest_end,
                    "organizer": organizer,
                    "tags": tags,
                    "ai_policy": "unknown",
                    "prize": prize,
                    "eligibility": None,
                    "requirements": None,
                    "summary": None,
                }
            )
        return out


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.datafountain
    import asyncio

    async def _main() -> None:
        try:
            for it in await DataFountainSource().fetch():
                print(it["title"][:40], "|", it["contest_start"], "→", it["contest_end"], "|", it["prize"])
        except SourceError as e:
            print("SourceError:", e)

    asyncio.run(_main())
