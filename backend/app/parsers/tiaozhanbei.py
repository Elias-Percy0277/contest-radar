"""挑战杯官网（www.tiaozhanbei.net）解析器 —— method=http。

实测（2026-10）：首页为 Alpine.js 模板 + 服务端渲染混合；"竞赛/通知"列表条目：
  SSR 锚点 <a href="/article/15842/">标题</a>，另有 JS 数组 { title:'...', url:'/article/...' }（轮播图）。
首页无日期字段，日期一律 null（详情页才有，列表层尽力而为）。
"""
from __future__ import annotations

import re
from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import base_join, clean_text, fetch_text, make_soup

DEFAULT_URL = "https://www.tiaozhanbei.net/"
ORGANIZER = "共青团中央、中国科协、教育部、中国科学院、全国学联"
# 只保留与赛事/官方通知相关的文章，过滤纯新闻软文里的杂项
KEEP_KEYWORDS = ("挑战杯", "竞赛", "大赛", "通知", "擂台赛", "揭榜挂帅", "举办")


class TiaozhanbeiSource(BaseSource):
    source_id = "tiaozhanbei"
    name = "挑战杯"
    method = "http"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        html = await fetch_text(url)
        items = self.parse(html, base_url=url)
        if not items:
            raise SourceError("挑战杯首页未解析到竞赛相关文章，页面可能改版")
        return items

    def parse(self, html: str, *, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
        soup = make_soup(html)
        found: dict[str, dict[str, Any]] = {}

        def add(title: str, href: str) -> None:
            title = clean_text(title)
            if not title or len(title) < 8 or not any(k in title for k in KEEP_KEYWORDS):
                return
            url = base_join(base_url, href)
            if url in found:
                return
            tags = ["国家级", "挑战杯"]
            m = re.search(r"第([0-9一二三四五六七八九十百\s]+)届", title)
            if m:
                tags.append(f"第{m.group(1)}届")
            found[url] = {
                "title": title,
                "url": url,
                "category": "综合学科",
                "reg_start": None,
                "reg_deadline": None,
                "contest_start": None,
                "contest_end": None,
                "organizer": ORGANIZER,
                "tags": tags,
                "ai_policy": "unknown",
                "prize": None,
                "eligibility": "面向全国大学生",
                "requirements": None,
                "summary": None,
            }

        # 1) SSR 锚点列表
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/article/" in href:
                add(a.get_text(), href)
        # 2) JS 数组（轮播 slides）：title: '...' , url: '/article/...'
        for m in re.finditer(r"title:\s*'([^']{8,120})',\s*url:\s*'(/article/\d+/)'", html):
            add(m.group(1), m.group(2))
        return list(found.values())[:12]  # 首页条目有限，取前 12 条防噪音


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.tiaozhanbei
    import asyncio

    async def _main() -> None:
        for it in await TiaozhanbeiSource().fetch():
            print(it["title"], "|", it["url"])

    asyncio.run(_main())
