"""牛客竞赛首页（ac.nowcoder.com/acm/home）解析器 —— method=http。

实测（2026-10）：首页服务端渲染，比赛卡片形如：
  <div class="acm-item">
    <h4><a href="/acm/contest/141374">牛客小白月赛138</a>
        <span class="match-status match-signup">报名中</span></h4>
    <div class="acm-item-time"> 2天后 19:00 </div>
  </div>
只输出"报名中/即将开始"的条目；"比赛结束"跳过。
相对时间（2天后 19:00 / 今天 12:00）按 Asia/Shanghai 换算成具体日期，换算不了 contest_start=null。
"""
from __future__ import annotations

from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import (
    base_join,
    clean_text,
    fetch_text,
    make_soup,
    parse_relative_time,
    to_iso,
)

DEFAULT_URL = "https://ac.nowcoder.com/acm/home"
# 视为"未开始"的状态文本（比赛结束/已结束等一律跳过）
OPEN_STATUSES = ("报名中", "即将开始")


class NowcoderSource(BaseSource):
    source_id = "nowcoder"
    name = "牛客竞赛"
    method = "http"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        html = await fetch_text(url)
        items = self.parse(html, base_url=url)
        if not items:
            raise SourceError("牛客首页未解析到报名中/即将开始的比赛（首页常只展示少量卡片），请复查")
        return items

    def parse(self, html: str, *, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
        soup = make_soup(html)
        out: list[dict[str, Any]] = []
        for card in soup.select("div.acm-item"):
            a = card.select_one('h4 a[href*="/acm/contest/"]')
            if not a or not a.get("href"):
                continue
            title = clean_text(a.get_text())
            if not title:
                continue
            status_el = card.select_one("span.match-status")
            status = clean_text(status_el.get_text()) if status_el else ""
            if status and not any(k in status for k in OPEN_STATUSES):
                continue  # 比赛结束等状态跳过
            time_el = card.select_one("div.acm-item-time")
            time_text = clean_text(time_el.get_text()) if time_el else ""
            start = parse_relative_time(time_text)

            tags = ["牛客"]
            if card.select_one("span.tag-rating"):
                tags.append("Rated")
            for kw, tag in (("小白月赛", "入门友好"), ("高校", "高校赛"), ("国庆", "节日赛")):
                if kw in title:
                    tags.append(tag)

            out.append(
                {
                    "title": title,
                    "url": base_join(base_url, a["href"]),
                    "category": "算法竞赛",
                    "reg_start": None,
                    "reg_deadline": None,  # 首页卡片无报名截止信息
                    "contest_start": to_iso(start),
                    "contest_end": None,  # 单日赛，结束日期未知时交由框架推导
                    "organizer": "牛客",
                    "tags": tags,
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": None,
                    "requirements": None,
                    "summary": f"开赛时间：{time_text or '未知'}（状态：{status or '未知'}）",
                }
            )
        return out


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.nowcoder
    import asyncio

    async def _main() -> None:
        for it in await NowcoderSource().fetch():
            print(it["title"], "|", it["contest_start"], "|", it["url"])

    asyncio.run(_main())
