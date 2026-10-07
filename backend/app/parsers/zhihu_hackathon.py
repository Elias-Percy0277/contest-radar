"""知乎黑客松（www.zhihu.com/hackathon）解析器 —— method=playwright。

实测（2026-10）：SPA，未登录可渲染主页与参赛项目列表（获奖公示/队伍等子页可能需登录，
首页内容足够构建赛事条目）。数据接口（页面自身 XHR，未登录可访问）：
  GET /api/v4/brand_influence/api/hackathon/config
  → data.activity{name, code, start_date(Unix秒), end_date(Unix秒), phase}
整个黑客松作为 1 条 ContestRaw（category=应用与开发，tags 含"黑客松"）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import SH_TZ, clean_text

DEFAULT_URL = "https://www.zhihu.com/hackathon/"
CONFIG_MARK = "/api/v4/brand_influence/api/hackathon/config"


class ZhihuHackathonSource(BaseSource):
    source_id = "zhihu_hackathon"
    name = "知乎黑客松"
    method = "playwright"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise SourceError("知乎黑客松源需要 Playwright：先 pip install playwright && playwright install chromium") from exc

        try:
            async with async_playwright() as p:
                try:
                    browser = await p.chromium.launch(headless=True)
                except Exception as exc:
                    raise SourceError(
                        "知乎黑客松源需要 Playwright：先 pip install playwright && playwright install chromium"
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
            raise SourceError(f"知乎黑客松页面渲染失败：{exc.__class__.__name__}: {exc}") from exc

        items = self.build_items(captured)
        if not items:
            raise SourceError("知乎黑客松页面渲染后未提取到活动信息，站点可能改版或需登录")
        return items

    async def _render_and_capture(self, page: Any, url: str) -> dict[str, Any]:
        import asyncio as _aio

        captured: dict[str, Any] = {"activity": None, "page_text": ""}

        async def on_response(resp: Any) -> None:
            try:
                if CONFIG_MARK in resp.url:
                    data = await resp.json()
                    act = ((data or {}).get("data") or {}).get("activity") or None
                    if act:
                        captured["activity"] = act
            except Exception:
                pass

        page.on("response", lambda r: _aio.ensure_future(on_response(r)))
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        await page.wait_for_timeout(3_000)
        captured["page_text"] = clean_text(await page.inner_text("body"))[:400]
        return captured

    @staticmethod
    def build_items(captured: dict[str, Any]) -> list[dict[str, Any]]:
        act = captured.get("activity")
        items: list[dict[str, Any]] = []
        if isinstance(act, dict) and act.get("name"):
            name = clean_text(act.get("name"))
            start_ts, end_ts = act.get("start_date"), act.get("end_date")

            def _ts(v: Any) -> str | None:
                if not v:
                    return None
                try:
                    return datetime.fromtimestamp(int(v), tz=SH_TZ).date().isoformat()
                except (ValueError, OSError, OverflowError):
                    return None

            summary_bits = []
            if act.get("phase"):
                summary_bits.append(f"阶段：{act['phase']}")
            text = captured.get("page_text") or ""
            if "参赛项目" in text:
                import re

                m = re.search(r"参赛项目\s*\((\d+)\)", text)
                if m:
                    summary_bits.append(f"参赛项目 {m.group(1)} 个")
            items.append(
                {
                    "title": name,
                    "url": "https://www.zhihu.com/hackathon",
                    "category": "应用与开发",
                    "reg_start": None,
                    "reg_deadline": None,
                    "contest_start": _ts(start_ts),
                    "contest_end": _ts(end_ts),
                    "organizer": "知乎",
                    "tags": ["黑客松", "企业级"],
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": None,
                    "requirements": None,
                    "summary": "；".join(summary_bits) or None,
                }
            )
        # DOM 兜底：无接口数据时用页面标题构建 1 条
        if not items:
            text = captured.get("page_text") or ""
            if "黑客松" in text:
                items.append(
                    {
                        "title": "知乎黑客松（页面信息）",
                        "url": "https://www.zhihu.com/hackathon",
                        "category": "应用与开发",
                        "reg_start": None,
                        "reg_deadline": None,
                        "contest_start": None,
                        "contest_end": None,
                        "organizer": "知乎",
                        "tags": ["黑客松", "企业级"],
                        "ai_policy": "unknown",
                        "prize": None,
                        "eligibility": None,
                        "requirements": None,
                        "summary": text[:120] or None,
                    }
                )
        return items


def _UA() -> str:
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.zhihu_hackathon
    import asyncio

    async def _main() -> None:
        for it in await ZhihuHackathonSource().fetch():
            print(it["title"], "|", it["contest_start"], "~", it["contest_end"], "|", it["summary"])

    asyncio.run(_main())
