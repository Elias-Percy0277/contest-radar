"""赛氪（saikr.com）高校竞赛聚合平台 —— method=playwright。

首页为 SPA，渲染后提取赛事活动链接（m/event.saikr.com 上 /active/ 路径）。
- 排除课程广告（/course、wewinfuture.com）与新闻稿（/news/）
- 只保留 CS 相关赛事（关键词过滤，params.keep_keywords 可覆盖）——
  赛氪混杂大量非技术类知识竞赛，不过滤会淹没真正有价值的比赛
- 首页仅展示部分在办赛事，日期需进详情页才有，v1 留 null 由状态推导兜底
"""
from __future__ import annotations

from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import base_join, clean_text, make_soup

DEFAULT_URL = "https://www.saikr.com/"

# CS 相关性关键词（默认过滤口径）
DEFAULT_KEEP = (
    "计算机", "程序", "算法", "人工智", "AI", "软件", "网络", "数据", "数学", "建模",
    "创新创业", "电子", "信息", "物联网", "云计算", "机器人", "安全", "开发", "智能", "开源",
)
EXCLUDE_HREF = ("/course", "wewinfuture", "/news/")


class SaikrSource(BaseSource):
    source_id = "saikr"
    name = "赛氪竞赛聚合"
    method = "playwright"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise SourceError("赛氪源需要安装 playwright 包：pip install playwright") from exc

        html = ""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    page = await browser.new_page()
                    await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=15_000)
                    except Exception:
                        pass
                    await page.wait_for_timeout(3_000)
                    html = await page.content()
                finally:
                    await browser.close()
        except Exception as exc:
            from app.parsers._util import playwright_launch_error

            raise SourceError(playwright_launch_error(exc)) from exc

        items = self.parse(html, base_url=url)
        if not items:
            raise SourceError("赛氪首页渲染后未解析到 CS 相关赛事（可能站点改版或过滤过严）")
        return items

    def parse(self, html: str, *, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
        soup = make_soup(html)
        keep = tuple(self.params.get("keep_keywords") or DEFAULT_KEEP)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/active" not in href or any(x in href for x in EXCLUDE_HREF):
                continue
            title = clean_text(a.get_text())
            if not title or len(title) < 8 or not any(k in title for k in keep):
                continue
            link = base_join(base_url, href)
            if link in seen:
                continue
            seen.add(link)

            category = "综合学科"
            if any(k in title for k in ("算法", "程序", "编程")):
                category = "算法竞赛"
            elif any(k in title for k in ("人工智能", "AI", "智能", "大模型")):
                category = "AI与数据科学"
            elif any(k in title for k in ("软件", "开发", "计算机设计")):
                category = "应用与开发"
            elif "安全" in title:
                category = "网络安全"

            out.append(
                {
                    "title": title,
                    "url": link,
                    "category": category,
                    "reg_start": None,
                    "reg_deadline": None,
                    "contest_start": None,
                    "contest_end": None,
                    "organizer": "赛氪（聚合）",
                    "tags": ["赛氪"],
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": None,
                    "requirements": None,
                    "summary": None,
                }
            )
        return out


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.saikr
    import asyncio

    async def _main() -> None:
        try:
            for it in await SaikrSource().fetch():
                print(it["category"], "|", it["title"][:40], "|", it["url"][:60])
        except SourceError as e:
            print("SourceError:", e)

    asyncio.run(_main())
