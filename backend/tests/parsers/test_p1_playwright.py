"""P1 第二批 3 个 Playwright 源测试（fixture 为 2026-10 真实渲染/XHR 捕获）。"""
from __future__ import annotations

import json
import os

import pytest

from app.parsers import astar, lanqiao, zhihu_hackathon


def _load(name: str) -> dict:
    from conftest import FIXTURES_DIR

    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"{name} 未生成（生成 fixture 的机器未装 chromium）")
    return json.loads(path.read_text(encoding="utf-8"))


def test_lanqiao_items() -> None:
    from conftest import assert_contest_raw

    captured = _load("lanqiao_api.json")
    items = lanqiao.LanqiaoSource.build_items({"news": captured["news"], "dom_html": ""})
    assert len(items) >= 1
    for it in items:
        assert_contest_raw(it)
        assert it["category"] == "算法竞赛"
        assert "/notices/" in it["url"]
    # 第N届（含中文数字"十八"）进 tags
    assert any(t.endswith("届") for i in items for t in i["tags"])


def test_lanqiao_dom_fallback() -> None:
    """接口失败时 DOM 兜底路径（用渲染 HTML 里的公告锚点）。"""
    from conftest import FIXTURES_DIR, assert_contest_raw

    html_path = FIXTURES_DIR / "lanqiao_rendered.html"
    if not html_path.exists():
        pytest.skip("lanqiao_rendered.html 未生成")
    items = lanqiao.LanqiaoSource.build_items({"news": [], "dom_html": html_path.read_text(encoding="utf-8")})
    assert len(items) >= 1
    for it in items:
        assert_contest_raw(it)


def test_zhihu_hackathon_event() -> None:
    from conftest import assert_contest_raw

    captured = _load("zhihu_hackathon_config.json")
    items = zhihu_hackathon.ZhihuHackathonSource.build_items(captured)
    assert len(items) == 1
    it = items[0]
    assert_contest_raw(it)
    assert it["category"] == "应用与开发"
    assert "黑客松" in it["tags"]
    # 活动起止由 Unix 时间戳换算
    if it["contest_start"]:
        assert len(it["contest_start"]) == 10


def test_zhihu_hackathon_dom_fallback() -> None:
    items = zhihu_hackathon.ZhihuHackathonSource.build_items(
        {"activity": None, "page_text": "黑客松 2026 参赛队伍 活动介绍 参赛项目 (135)"}
    )
    assert len(items) == 1
    assert "黑客松" in items[0]["tags"]


def test_astar_items() -> None:
    from conftest import assert_contest_raw

    captured = _load("astar_articles.json")
    items = astar.AstarSource.build_items({"articles": captured["articles"], "dom_html": ""})
    assert len(items) >= 1
    for it in items:
        assert_contest_raw(it)
        assert it["category"] == "算法竞赛"
        assert "news-info" in it["url"]
    # 公告标题带年份
    assert any("2026" in i["title"] for i in items)


@pytest.mark.skipif(not os.environ.get("CR_PW_LIVE"), reason="需要 chromium，设 CR_PW_LIVE=1 启用")
def test_live_three_sources() -> None:
    """真实渲染（已实测）：三源各 ≥1 条合法 ContestRaw。"""
    import asyncio

    from conftest import assert_contest_raw

    async def run() -> list:
        out = []
        for cls in (lanqiao.LanqiaoSource, zhihu_hackathon.ZhihuHackathonSource, astar.AstarSource):
            out.extend(await cls().fetch())
        return out

    items = asyncio.run(run())
    assert len(items) >= 3
    for it in items:
        assert_contest_raw(it)
