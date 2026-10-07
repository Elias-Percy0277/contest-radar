"""P1 第一批 5 个 HTTP 源测试（fixture 均为 2026-10 真实抓取）。"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.fetcher.base import SourceError
from app.parsers import cy_ncss, jsjds, leetcode, tianchi, tiaozhanbei


def _patch(monkeypatch: pytest.MonkeyPatch, module: object, fixture: str) -> None:
    from conftest import load_fixture

    data = load_fixture(fixture)

    async def fake_fetch_text(url: str, **_: object) -> str:
        return data

    async def fake_fetch_json(url: str, **_: object) -> object:
        return json.loads(data)

    if hasattr(module, "fetch_text"):
        monkeypatch.setattr(module, "fetch_text", fake_fetch_text)
    if hasattr(module, "fetch_json"):
        monkeypatch.setattr(module, "fetch_json", fake_fetch_json)


# ---------------- 挑战杯 ----------------
def test_tiaozhanbei_items(monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import assert_contest_raw

    _patch(monkeypatch, tiaozhanbei, "tiaozhanbei.html")
    items = asyncio.run(tiaozhanbei.TiaozhanbeiSource().fetch())
    assert len(items) >= 1
    for it in items:
        assert_contest_raw(it)
        assert it["category"] == "综合学科"
        assert it["organizer"]  # 主办方非空
    # 第N届 进 tags
    assert any(any(t.startswith("第") and t.endswith("届") for t in i["tags"]) for i in items)


# ---------------- 互联网+ ----------------
def test_cy_ncss_items(monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import assert_contest_raw

    _patch(monkeypatch, cy_ncss, "cy_ncss.html")
    items = asyncio.run(cy_ncss.CyNcssSource().fetch())
    assert len(items) >= 1
    for it in items:
        assert_contest_raw(it)
        assert it["category"] == "综合学科"
        assert "/information/" in it["url"]
    # 官方动态应与"大赛"相关
    assert all(any(k in i["title"] for k in ("大赛", "创新大赛")) for i in items)


# ---------------- 计算机设计大赛 ----------------
def test_jsjds_items(monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import assert_contest_raw

    _patch(monkeypatch, jsjds, "jsjds.html")
    items = asyncio.run(jsjds.JsjdsSource().fetch())
    assert len(items) >= 1
    for it in items:
        assert_contest_raw(it)
        assert it["category"] == "应用与开发"
    # MM-DD.YYYY 日期被重排进 summary（官方通知（发布于 YYYY-MM-DD））
    assert any(i["summary"] and "发布于 20" in i["summary"] for i in items)


# ---------------- LeetCode ----------------
def test_leetcode_items(monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import assert_contest_raw

    _patch(monkeypatch, leetcode, "leetcode_upcoming.json")
    items = asyncio.run(leetcode.LeetcodeSource().fetch())
    assert len(items) >= 1
    for it in items:
        assert_contest_raw(it)
        assert it["category"] == "算法竞赛"
        assert it["contest_start"] and it["contest_end"]
        assert it["contest_end"] >= it["contest_start"]
        assert it["url"].startswith("https://leetcode.cn/contest/")
    # 周赛/双周赛标注
    assert any("双周赛" in t for i in items for t in i["tags"]) or all("周赛" in t for i in items for t in i["tags"])


def test_leetcode_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(url: str, **_: object) -> object:
        return {"data": {"contestV2UpcomingContests": []}}

    monkeypatch.setattr(leetcode, "fetch_json", fake)
    with pytest.raises(SourceError):
        asyncio.run(leetcode.LeetcodeSource().fetch())


# ---------------- 天池 ----------------
def test_tianchi_items(monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import assert_contest_raw

    _patch(monkeypatch, tianchi, "tianchi_race_page.json")
    items = asyncio.run(tianchi.TianchiSource().fetch())
    assert len(items) >= 1
    for it in items:
        assert_contest_raw(it)
        assert it["category"] == "AI与数据科学"
        assert "/competition/entrance/" in it["url"]
    # 真实数据里至少一场带奖金
    assert any(i["prize"] for i in items)
    # 时间字段规范化
    assert all(i["contest_end"] is None or len(i["contest_end"]) == 10 for i in items)


def test_tianchi_stale_filter() -> None:
    """结束超 45 天且无有效报名截止的历史赛应被过滤。"""
    raw = [
        {"raceId": 1, "name": "进行中大赛", "raceStartTime": "2026-09-01 00:00:00",
         "raceEndTime": "2026-12-31 23:59:59", "bonus": 10000, "currency": "￥"},
        {"raceId": 2, "name": "陈年旧赛", "raceStartTime": "2020-01-01 00:00:00",
         "raceEndTime": "2020-02-01 23:59:59", "signupEndTime": "2020-01-15 00:00:00", "bonus": 0},
        {"raceId": 3, "name": "无结束时间长期赛", "raceStartTime": "2026-01-01 00:00:00",
         "raceEndTime": None, "bonus": 0},
    ]
    items = tianchi.TianchiSource().parse(raw)
    names = [i["title"] for i in items]
    assert "进行中大赛" in names and "无结束时间长期赛" in names
    assert "陈年旧赛" not in names
