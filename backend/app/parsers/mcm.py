"""全国大学生数学建模竞赛（mcm.edu.cn）—— method=http，官网通知列表。

首页通知/新闻为服务端渲染；按标题关键词保留与赛事相关的通知
（通知/通告/赛题/报名/规定/挑战/课题），过滤"成功举行/回顾"类已办活动新闻。
"""
from __future__ import annotations

from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import base_join, clean_text, fetch_text, make_soup

DEFAULT_URL = "https://www.mcm.edu.cn/"
KEEP = ("通知", "通告", "赛题", "报名", "规定", "挑战", "课题", "竞赛")
EXCLUDE = ("成功举行", "回顾", "闭幕", "圆满")


class McmSource(BaseSource):
    source_id = "mcm"
    name = "全国大学生数学建模竞赛"
    method = "http"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        html = await fetch_text(url)
        items = self.parse(html, base_url=url)
        if not items:
            raise SourceError("数模官网通知解析为 0 条，可能页面改版")
        return items

    def parse(self, html: str, *, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
        soup = make_soup(html)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            if "/html_cn/node/" not in a["href"]:
                continue
            title = clean_text(a.get_text())
            if len(title) < 10 or not any(k in title for k in KEEP) or any(k in title for k in EXCLUDE):
                continue
            link = base_join(base_url, a["href"])
            if link in seen:
                continue
            seen.add(link)
            out.append(
                {
                    "title": title,
                    "url": link,
                    "category": "综合学科",
                    "reg_start": None,
                    "reg_deadline": None,
                    "contest_start": None,
                    "contest_end": None,
                    "organizer": "中国工业与应用数学学会",
                    "tags": ["数学建模"],
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": "全日制在校大学生",
                    "requirements": None,
                    "summary": None,
                }
            )
        return out


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.mcm
    import asyncio

    async def _main() -> None:
        try:
            for it in await McmSource().fetch():
                print(it["title"][:45], "|", it["url"][:60])
        except SourceError as e:
            print("SourceError:", e)

    asyncio.run(_main())
