"""百度之星（astar.baidu.com）解析器 —— method=playwright。

实测（2026-10）：SPA（curl 仅 2.2KB 壳），渲染后"大赛公告"列表来自公开接口：
  GET /web/getArticlesByClassId.do?classId=14&start=0&limit=4   （公告，total=61）
  GET /web/getArticlesByClassId.do?classId=13&start=0&limit=4   （新闻）
字段：encryptId/title/updateTime(Unix毫秒)/simpleContent。
详情页 URL：https://astar.baidu.com/#/news-info?tab=3&id={encryptId}。
策略：渲染 → 捕获公告接口 → 页面内重放 limit=20 → DOM 公告锚点兜底。无登录墙。
"""
from __future__ import annotations

import re
from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import clean_text, make_soup, today_sh

DEFAULT_URL = "https://astar.baidu.com/#/"
API_MARK = "/web/getArticlesByClassId.do"
ORGANIZER = "百度"
KEEP_KEYWORDS = ("大赛", "通知", "公示", "名单", "公告", "初赛", "决赛", "获奖")


class AstarSource(BaseSource):
    source_id = "astar"
    name = "百度之星"
    method = "playwright"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise SourceError("百度之星源需要 Playwright：先 pip install playwright && playwright install chromium") from exc

        try:
            async with async_playwright() as p:
                try:
                    browser = await p.chromium.launch(headless=True)
                except Exception as exc:
                    raise SourceError(
                        "百度之星源需要 Playwright：先 pip install playwright && playwright install chromium"
                        f"（启动 chromium 失败：{exc}）"
                    ) from exc
                try:
                    page = await browser.new_page(user_agent=_UA())
                    captured = await self._render_and_capture(page, url)
                finally:
                    await browser.close()
        except SourceError:
            raise
        except Exception as exc:
            raise SourceError(f"百度之星页面渲染失败：{exc.__class__.__name__}: {exc}") from exc

        items = self.build_items(captured)
        if not items:
            raise SourceError("百度之星页面渲染后未提取到大赛公告，站点可能改版")
        return items

    async def _render_and_capture(self, page: Any, url: str) -> dict[str, Any]:
        import asyncio as _aio

        captured: dict[str, Any] = {"articles": [], "dom_html": ""}

        async def on_response(resp: Any) -> None:
            try:
                if API_MARK in resp.url:
                    data = await resp.json()
                    captured["articles"].extend((data or {}).get("data", {}).get("datas") or [])
            except Exception:
                pass

        page.on("response", lambda r: _aio.ensure_future(on_response(r)))
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        await page.wait_for_timeout(3_000)
        captured["dom_html"] = await page.content()

        # 增强：页面内重放公告接口（classId=14），limit 提到 20
        try:
            more = await page.evaluate(
                """async () => {
                const u = '/web/getArticlesByClassId.do?classId=14&start=0&limit=20';
                const r = await fetch(u, {credentials: 'omit'});
                const j = await r.json();
                return (j && j.data && j.data.datas) || [];
            }"""
            )
            captured["articles"].extend(more or [])
        except Exception:
            pass
        return captured

    @staticmethod
    def build_items(captured: dict[str, Any]) -> list[dict[str, Any]]:
        from datetime import datetime as _dt
        from datetime import timedelta

        floor = (today_sh() - timedelta(days=180)).isoformat()
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for x in captured.get("articles", []):
            title = clean_text(x.get("title"))
            eid = x.get("encryptId")
            if not title or not eid or not any(k in title for k in KEEP_KEYWORDS):
                continue
            url = f"https://astar.baidu.com/#/news-info?tab=3&id={eid}"
            if url in seen:
                continue
            seen.add(url)
            pub = None
            ut = x.get("updateTime")
            if ut:
                try:
                    pub = _dt.fromtimestamp(int(ut) / 1000, tz=None).date().isoformat()
                except (ValueError, OSError, OverflowError):
                    pub = None
            if pub and pub < floor:
                continue
            tags = ["百度之星", "国家级"]
            m = re.search(r"第([0-9一二三四五六七八九十百]+)届", title)
            if m:
                tags.append(f"第{m.group(1)}届")
            items.append(
                {
                    "title": title,
                    "url": url,
                    "category": "算法竞赛",
                    "reg_start": None,
                    "reg_deadline": None,
                    "contest_start": None,
                    "contest_end": None,
                    "organizer": ORGANIZER,
                    "tags": tags,
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": "面向全社会（含高校学生）",
                    "requirements": None,
                    "summary": f"官方公告（发布于 {pub}）" if pub else clean_text(x.get("simpleContent"))[:100] or None,
                }
            )
        # DOM 兜底：接口失败时从渲染后的公告锚点提取
        if not items and captured.get("dom_html"):
            soup = make_soup(captured["dom_html"])
            for a in soup.find_all("a", href=True):
                m = re.search(r"news-info.*?[?&]id=([A-F0-9]+)", a["href"], re.I)
                if not m:
                    continue
                title = clean_text(a.get_text())
                if not title or len(title) < 10 or not any(k in title for k in KEEP_KEYWORDS):
                    continue
                url = f"https://astar.baidu.com/#/news-info?tab=3&id={m.group(1)}"
                if url in seen:
                    continue
                seen.add(url)
                items.append(
                    {
                        "title": title,
                        "url": url,
                        "category": "算法竞赛",
                        "reg_start": None,
                        "reg_deadline": None,
                        "contest_start": None,
                        "contest_end": None,
                        "organizer": ORGANIZER,
                        "tags": ["百度之星", "国家级"],
                        "ai_policy": "unknown",
                        "prize": None,
                        "eligibility": "面向全社会（含高校学生）",
                        "requirements": None,
                        "summary": None,
                    }
                )
                if len(items) >= 12:
                    break
        return items


def _UA() -> str:
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.astar
    import asyncio

    async def _main() -> None:
        for it in await AstarSource().fetch():
            print(it["title"][:44], "|", it["url"][:80])

    asyncio.run(_main())
