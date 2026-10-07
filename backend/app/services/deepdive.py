"""手动深挖：抓赛事详情页正文，供 LLM 抽取 AI 政策/参赛要求/奖金。"""
from __future__ import annotations

from app.fetcher.base import SourceError
from app.parsers._util import clean_text, fetch_text, make_soup

MIN_TEXT_LEN = 400  # 纯 HTTP 拿到的正文低于该长度，认为页面是动态渲染，回退 Playwright


def html_to_text(html: str) -> str:
    """HTML → 纯文本（去脚本/样式，压缩空白）。"""
    soup = make_soup(html)
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()
    return clean_text(soup.get_text(" ", strip=True))


async def fetch_detail_text(url: str) -> str:
    """抓详情页正文：先纯 HTTP；正文过短（SPA 空壳）时用 Playwright 渲染兜底。

    失败抛 SourceError（中文原因，由路由转 502）。
    """
    html = await fetch_text(url)
    text = html_to_text(html)
    if len(text) >= MIN_TEXT_LEN:
        return text

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise SourceError("详情页为动态渲染且未安装 Playwright，无法深挖") from exc

    rendered = ""
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
                await page.wait_for_timeout(2_000)
                rendered = html_to_text(await page.content())
            finally:
                await browser.close()
    except SourceError:
        raise
    except Exception as exc:
        raise SourceError(f"详情页渲染失败：{type(exc).__name__}: {exc}") from exc

    return rendered if len(rendered) > len(text) else text
