"""CCF 算法能力大赛（cacc.ccf.org.cn）解析器 —— method=playwright。

实测（2026-10）：该站是 Vue SPA 空壳（HTML 仅 685 字节、<div id="app"> 空），
纯 HTTP 拿不到赛事列表（站内仅见 /prod-api/modules/* 私有接口，无公开列表 API）。
方案：Playwright 渲染首页（domcontentloaded + networkidle + 缓冲），
对渲染后的 DOM 复用"锚点 + 竞赛关键词"解析（与原 http 版 parse 完全一致）。
Playwright 未安装或 chromium 内核缺失 → 抛 SourceError 提示安装命令。
"""
from __future__ import annotations

from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import base_join, clean_text, make_soup

DEFAULT_URL = "https://cacc.ccf.org.cn/"
KEEP_KEYWORDS = ("大赛", "竞赛", "比赛", "报名", "初赛", "决赛", "CACC")
INSTALL_HINT = "CACC 源需要 Playwright：先 pip install playwright && playwright install chromium"


class CaccSource(BaseSource):
    source_id = "ccf_cacc"
    name = "CCF算法能力大赛"
    method = "playwright"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise SourceHintError() from exc

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
                        pass  # SPA 常驻轮询时 networkidle 可能等不到
                    await page.wait_for_timeout(3_000)
                    html = await page.content()
                finally:
                    await browser.close()
        except Exception as exc:
            msg = str(exc).lower()
            if "chromium" in msg or "browser" in msg or "executable" in msg:
                raise SourceError(f"{INSTALL_HINT}（启动 chromium 失败：{exc}）") from exc
            raise SourceError(f"CACC 官网渲染失败：{type(exc).__name__}: {exc}") from exc

        items = self.parse(html, base_url=url)
        if not items:
            raise SourceError("CACC 官网渲染成功但未解析到赛事条目（可能页面改版），请检查解析器")
        return items

    def parse(self, html: str, *, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
        """对（渲染后的）页面做锚点+关键词解析；SPA 空壳返回空列表。"""
        soup = make_soup(html)
        mount = soup.find(id="app")
        if mount is not None and not mount.find_all("a", href=True):
            return []  # 渲染失败仍是空壳
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            title = clean_text(a.get_text())
            if not title or not any(k in title for k in KEEP_KEYWORDS):
                continue
            href = a["href"]
            if "/login" in href:
                continue  # 登录入口按钮，不是赛事信息
            if href.startswith("javascript"):
                # SPA 伪链接：仅保留像"关于…的通知"这类公告标题，链接回退官网首页
                if len(title) < 12 or not any(k in title for k in ("通知", "公告", "新闻", "第")):
                    continue
                link = base_url
            else:
                link = base_join(base_url, href)
            if link in seen and link == base_url:
                continue
            if link in seen:
                continue
            seen.add(link)
            out.append(
                {
                    "title": title,
                    "url": link,
                    "category": "算法竞赛",
                    "reg_start": None,
                    "reg_deadline": None,
                    "contest_start": None,
                    "contest_end": None,
                    "organizer": "CCF",
                    "tags": ["CACC"],
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": None,
                    "requirements": None,
                    "summary": None,
                }
            )
        return out


class SourceHintError(SourceError):
    def __init__(self) -> None:
        super().__init__(INSTALL_HINT)


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.cacc
    import asyncio

    async def _main() -> None:
        try:
            for it in await CaccSource().fetch():
                print(it["title"], "|", it["url"])
        except SourceError as e:
            print("SourceError:", e)

    asyncio.run(_main())
