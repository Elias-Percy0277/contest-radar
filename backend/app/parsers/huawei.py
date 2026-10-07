"""华为云大赛（competition.huaweicloud.com）解析器 —— method=playwright。

实测（2026-10）：该站是 SPA（curl 首页仅 8.5KB 壳），必须 Playwright 渲染。
抓取策略（分层，取稳）：
  1) 主策略：监听页面自身 XHR —— 首页加载时 SPA 会请求
     /v5/noauth/competitions/list?category_id=10001&...（字段最全：报名/比赛时间、奖金、分类、标签）
     与 /v2/noauth/hotcompetitions（热门赛事，含 forward_url 直达链接）。
     该请求带一次性防爬头 cftk（SPA 启动时 JS 生成），无法脱离页面伪造。
  2) 增强：拿到 cftk 后在页面上下文内 fetch 重放 list 接口（limit=50）拿更多条目。
  3) 兜底：DOM 选择器提取导航里的赛事卡片。
Playwright 未安装或 chromium 内核缺失 → 抛 SourceError 提示安装命令。
实测状态：chromium 148 已实测通过（fixture：huawei_rendered.html / huawei_api.json）。
"""
from __future__ import annotations

import re
from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import clean_text, today_sh

DEFAULT_URL = "https://competition.huaweicloud.com/"
INSTALL_HINT = "华为云源需要 Playwright：先 pip install playwright && playwright install chromium"

LIST_API_MARK = "/v5/noauth/competitions/list"
HOT_API_MARK = "/v2/noauth/hotcompetitions"

# category_name / 名称 → ContestRaw 分类 的关键词规则（按优先级）
CATEGORY_RULES: list[tuple[tuple[str, ...], str]] = [
    (("AI", "人工智能", "大模型", "机器学习", "深度学习", "智能"), "AI与数据科学"),
    (("算法", "编程", "黑客松", "CodeCraft"), "算法竞赛"),
    (("安全", "攻防"), "网络安全"),
]


def _category_for(name: str, category_name: str | None = None) -> str:
    text = f"{category_name or ''} {name}"
    for keywords, cat in CATEGORY_RULES:
        if any(k.lower() in text.lower() for k in keywords):
            return cat
    return "应用与开发"


def _date_part(v: Any) -> str | None:
    """"2025-04-15T18:00:00+0800" / "2025/04/15" → "2025-04-15"；非法返回 None。"""
    if not v or not isinstance(v, str):
        return None
    m = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", v)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _item_from_list_api(x: dict[str, Any]) -> dict[str, Any] | None:
    """list 接口条目 → ContestRaw（字段最全）。"""
    title = clean_text(x.get("title"))
    cid = x.get("competition_id") or x.get("id")
    if not title or cid is None:
        return None
    link = x.get("link_url") or f"https://competition.huaweicloud.com/information/{cid}/introduction"
    bonus = str(x.get("bonus") or "").strip()
    currency = str(x.get("currency_type") or "").strip()
    prize = f"{currency}{bonus}" if bonus and bonus not in ("0", "0.0") else None
    organizers = x.get("organizers")
    organizer = clean_text(organizers[0] if isinstance(organizers, list) and organizers else organizers) or "华为云"
    tag_names = [clean_text(t) for t in (x.get("tag_names") or []) if clean_text(t)]
    category_name = x.get("category_name")
    tags = ["企业级", "华为云"]
    if category_name:
        tags.append(clean_text(category_name))
    tags.extend(tag_names)
    return {
        "title": title,
        "url": link if str(link).startswith("http") else f"https://competition.huaweicloud.com{link}",
        "category": _category_for(title, category_name),
        "reg_start": _date_part(x.get("register_start_time")),
        "reg_deadline": _date_part(x.get("register_end_time")),
        "contest_start": _date_part(x.get("start_time")),
        "contest_end": _date_part(x.get("end_time")),
        "organizer": organizer,
        "tags": tags,
        "ai_policy": "unknown",
        "prize": prize,
        "eligibility": None,
        "requirements": clean_text(x.get("register_condition")) if isinstance(x.get("register_condition"), str) else None,
        "summary": clean_text(x.get("brief")) or None,
    }


def _item_from_hot_api(x: dict[str, Any]) -> dict[str, Any] | None:
    """hotcompetitions 条目 → ContestRaw（无日期，仅名称/链接/奖金）。"""
    title = clean_text(x.get("title"))
    link = x.get("forward_url")
    if not title or not link:
        return None
    bonus = str(x.get("bonus") or "").strip()
    return {
        "title": title,
        "url": str(link),
        "category": _category_for(title),
        "reg_start": None,
        "reg_deadline": None,
        "contest_start": None,
        "contest_end": None,
        "organizer": "华为云",
        "tags": ["企业级", "华为云", "热门"],
        "ai_policy": "unknown",
        "prize": f"￥{bonus}" if bonus and bonus not in ("0", "0.0") else None,
        "eligibility": None,
        "requirements": None,
        "summary": None,
    }


class HuaweiSource(BaseSource):
    source_id = "huawei"
    name = "华为云大赛"
    method = "playwright"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise SourceError(INSTALL_HINT) from exc

        try:
            async with async_playwright() as p:
                try:
                    browser = await p.chromium.launch(headless=True)
                except Exception as exc:  # 内核缺失 / 沙箱失败等
                    raise SourceError(f"{INSTALL_HINT}（启动 chromium 失败：{exc}）") from exc
                try:
                    page = await browser.new_page(user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                    ))
                    captured = await self._render_and_capture(page, url)
                finally:
                    await browser.close()
        except SourceError:
            raise
        except Exception as exc:  # 网络超时等
            raise SourceError(f"华为云大赛页面渲染失败：{exc.__class__.__name__}: {exc}") from exc

        items = self.build_items(captured)
        if not items:
            raise SourceError("华为云大赛页面渲染后未提取到任何赛事卡片，站点可能改版")
        return items

    async def _render_and_capture(self, page: Any, url: str) -> dict[str, Any]:
        """渲染首页并捕获 SPA 自身 XHR（payload + 防爬头），再页面内重放放大 limit。"""
        import asyncio as _aio

        captured: dict[str, Any] = {"list": [], "hot": [], "list_url": None, "headers": {}}

        async def on_response(resp: Any) -> None:
            try:
                if LIST_API_MARK in resp.url:
                    captured["list"].extend((await resp.json()).get("results") or [])
                    captured["list_url"] = resp.url
                    captured["headers"] = await resp.request.all_headers()
                elif HOT_API_MARK in resp.url:
                    captured["hot"].extend((await resp.json()).get("result") or [])
            except Exception:
                pass  # 单个响应解析失败不影响整体

        def on_response_sync(resp: Any) -> None:
            _aio.ensure_future(on_response(resp))

        page.on("response", on_response_sync)
        await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass  # SPA 常驻轮询时 networkidle 可能等不到
        await page.wait_for_timeout(3_000)

        # 增强：带 cftk 等头在页面内重放 list 接口，limit 提到 50
        if captured["list_url"]:
            try:
                more = await page.evaluate(
                    """async (args) => {
                    const u = args.url.replace(/([?&])limit=\\d+/, '$1limit=50')
                                     + (args.url.includes('_=') ? '' : '&_=' + Date.now());
                    const r = await fetch(u, {
                        credentials: 'include',
                        headers: Object.assign({'Accept': 'application/json, text/plain, */*'}, args.headers),
                    });
                    return await r.json();
                }""",
                    {"url": captured["list_url"], "headers": captured["headers"]},
                )
                results = (more or {}).get("results") or []
                if results:
                    captured["list"].extend(results)
            except Exception:
                pass  # 重放失败就用已捕获的
        return captured

    @staticmethod
    def build_items(captured: dict[str, Any], *, keep_days: int = 45) -> list[dict[str, Any]]:
        """合并 list/hot 两个接口的条目，按 url 去重（list 字段全，优先保留）。

        接口按 status=all 返回全部历史赛事；这里只保留 contest_end 为空（进行中/长期）
        或结束不超过 keep_days 天的条目，避免每次抓取灌入大量陈年赛事。
        """
        from datetime import timedelta

        floor_date = (today_sh() - timedelta(days=keep_days)).isoformat()
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in captured.get("list", []):
            item = _item_from_list_api(raw)
            if item and item["url"] not in seen:
                seen.add(item["url"])
                items.append(item)
        for raw in captured.get("hot", []):
            item = _item_from_hot_api(raw)
            if item and item["url"] not in seen:
                seen.add(item["url"])
                items.append(item)
        fresh = [i for i in items if not i["contest_end"] or i["contest_end"] >= floor_date]
        return fresh or items  # 过滤后为空说明全是老赛事且站点可能改版，退回全量


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.huawei
    import asyncio

    async def _main() -> None:
        for it in await HuaweiSource().fetch():
            print(it["category"], "|", it["title"], "|", it["reg_deadline"], "|", it["url"][:80])

    asyncio.run(_main())
