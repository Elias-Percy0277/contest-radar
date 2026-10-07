"""Codeforces API 解析器测试（fixture：codeforces.json，2026-10 抓取并截取前 100 条）。"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.fetcher.base import SourceError
from app.parsers import codeforces


def _fixture_payload() -> dict:
    from conftest import load_fixture

    return json.loads(load_fixture("codeforces.json"))


def test_parse_before_contests() -> None:
    from conftest import assert_contest_raw

    data = _fixture_payload()
    assert data["status"] == "OK"
    items = codeforces.CodeforcesSource().parse(data["result"])
    assert len(items) >= 1, "至少一场 phase=BEFORE 的比赛"
    for it in items:
        assert_contest_raw(it)
        assert it["organizer"] == "Codeforces"
        assert it["url"].startswith("https://codeforces.com/contest/")
        # 时长换算出的结束日期不应早于开始日期（同日或次日）
        assert it["contest_end"] >= it["contest_start"]
    # type=CF 且名称带 Div. 的应有级别 tag
    assert any(t.startswith("Div. ") for it in items for t in it["tags"]), "Div 级别应进 tags"


def test_fetch_via_patched_network(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_text(url: str, **_: object) -> str:
        return json.dumps(_fixture_payload(), ensure_ascii=False)

    monkeypatch.setattr(codeforces, "fetch_text", fake_fetch_text)
    items = asyncio.run(codeforces.CodeforcesSource().fetch())
    assert len(items) >= 1


def test_fetch_bad_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    async def bad_json(url: str, **_: object) -> str:
        return "not json"

    monkeypatch.setattr(codeforces, "fetch_text", bad_json)
    with pytest.raises(SourceError):
        asyncio.run(codeforces.CodeforcesSource().fetch())

    async def failed_status(url: str, **_: object) -> str:
        return json.dumps({"status": "FAILED", "comment": "x"})

    monkeypatch.setattr(codeforces, "fetch_text", failed_status)
    with pytest.raises(SourceError):
        asyncio.run(codeforces.CodeforcesSource().fetch())
