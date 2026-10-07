"""蓝桥杯大赛（dasai.lanqiao.cn）解析器 —— method=playwright。

实测（2026-10）：首页为 Vue SPA（curl 仅 1.8KB 壳），渲染后"大赛通知"列表由
公开接口提供：GET https://www.guoxinlanqiao.com/api/news/find?progid=20&pageno=1&pagesize=10&status=1
（total=738；字段 title/publishTime/nnid/synopsis）。详情页 URL：/notices/{nnid}/。
策略：渲染首页 → 监听捕获该接口 → 页面内 fetch 重放 pagesize=20 → DOM 通知列表兜底。
无登录墙（未登录可渲染通知列表）。
"""
from __future__ import annotations

import re
from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import clean_text, make_soup, today_sh

DEFAULT_URL = "https://dasai.lanqiao.cn/"
API_MARK = "/api/news/find"
ORGANIZER = "工业和信息化部人才交流中心"
KEEP_KEYWORDS = ("大赛", "通知", "竞赛", "蓝桥杯", "举办", "报名")


def _date_part(v: Any) -> str | None:
    """"2026-09-10T13:23:09" → "2026-09-10"。"""
    if not v or not isinstance(v, str):
        return None
    m = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", v)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


class LanqiaoSource(BaseSource):
    source_id = "lanqiao"
    name = "蓝桥杯大赛"
    method = "playwright"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise SourceError("蓝桥杯源需要 Playwright：先 pip install playwright && playwright install chromium") from exc

        try:
            async with async_playwright() as p:
                try:
                    browser = await p.chromium.launch(headless=True)
                except Exception as exc:
                    raise SourceError(
                        "蓝桥杯源需要 Playwright：先 pip install playwright && playwright install chromium"
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
            raise SourceError(f"蓝桥杯页面渲染失败：{exc.__class__.__name__}: {exc}") from exc

        items = self.build_items(captured)
        if not items:
            raise SourceError("蓝桥杯页面渲染后未提取到大赛通知，站点可能改版")
        return items

    async def _render_and_capture(self, page: Any, url: str) -> dict[str, Any]:
        import asyncio as _aio

        captured: dict[str, Any] = {"news": [], "dom_html": ""}

        async def on_response(resp: Any) -> None:
            try:
                if API_MARK in resp.url:
                    data = await resp.json()
                    captured["news"].extend((data or {}).get("datalist") or [])
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

        # 增强：页面内重放通知接口，pagesize 提到 20（跨域由站点自身 CORS 允许）
        try:
            more = await page.evaluate(
                """async () => {
                const u = 'https://www.guoxinlanqiao.com/api/news/find?progid=20&pageno=1&pagesize=20&status=1';
                const r = await fetch(u, {credentials: 'omit'});
                return await r.json();
            }"""
            )
            captured["news"].extend((more or {}).get("datalist") or [])
        except Exception:
            pass
        return captured

    @staticmethod
    def build_items(captured: dict[str, Any]) -> list[dict[str, Any]]:
        from datetime import timedelta

        floor = (today_sh() - timedelta(days=120)).isoformat()
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        # 1) 接口数据（优先）
        for x in captured.get("news", []):
            title = clean_text(x.get("title"))
            nnid = x.get("nnid")
            if not title or nnid is None or not any(k in title for k in KEEP_KEYWORDS):
                continue
            url = f"https://dasai.lanqiao.cn/notices/{nnid}/"
            if url in seen:
                continue
            seen.add(url)
            pub = _date_part(x.get("publishTime"))
            if pub and pub < floor:
                continue  # 过滤太久远的历史通知
            tags = ["蓝桥杯", "国家级"]
            m = re.search(r"第([0-9一二三四五六七八九十百]+)届", title)
            if m:
                tags.append(f"第{m.group(1)}届")
            if "设计" in title:
                tags.append("设计赛")
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
                    "eligibility": "面向全国大学生",
                    "requirements": None,
                    "summary": f"官方通知（发布于 {pub}）" if pub else clean_text(x.get("synopsis"))[:100] or None,
                }
            )
        # 2) DOM 兜底（接口失败时）
        if not items and captured.get("dom_html"):
            soup = make_soup(captured["dom_html"])
            for a in soup.find_all("a", href=True):
                m = re.search(r"/notices/(\d+)/?", a["href"])
                if not m:
                    continue
                title = clean_text(a.get_text())
                if not title or len(title) < 10 or not any(k in title for k in KEEP_KEYWORDS):
                    continue
                url = f"https://dasai.lanqiao.cn/notices/{m.group(1)}/"
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
                        "tags": ["蓝桥杯", "国家级"],
                        "ai_policy": "unknown",
                        "prize": None,
                        "eligibility": "面向全国大学生",
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


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.lanqiao
    import asyncio

    async def _main() -> None:
        for it in await LanqiaoSource().fetch():
            print(it["title"][:40], "|", it["url"])

    asyncio.run(_main())
