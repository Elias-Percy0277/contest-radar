"""CSP 认证官网解析器测试（fixture：cspro.html，2026-10 抓取的真实通知公告页）。"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.fetcher.base import SourceError
from app.parsers import cspro


def _patch_fetch(monkeypatch: pytest.MonkeyPatch, fixture: str) -> None:
    async def fake_fetch_text(url: str, **_: object) -> str:
        return fixture

    monkeypatch.setattr(cspro, "fetch_text", fake_fetch_text)


def test_parse_notice_list(monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import assert_contest_raw, load_fixture

    src = cspro.CsproSource()
    items = src.parse(load_fixture("cspro.html"))
    assert len(items) >= 1, "通知公告至少解析出 1 条"
    for it in items:
        assert_contest_raw(it)
        assert it["category"] == "认证考试"
        assert it["organizer"] == "CCF"
    # 实测样例：第43次报名通知（2026年9月13日）→ contest_start=2026-09-13
    signup = [i for i in items if "报名通知" in i["title"]]
    assert signup, "fixture 里应有报名通知条目"
    assert any(i["contest_start"] == "2026-09-13" for i in signup), "报名通知应提取认证日期"
    # 批次标签：第N次
    assert any("第43次" in i["tags"] for i in items), "tags 应含认证批次"


def test_fetch_via_patched_network(monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import load_fixture

    _patch_fetch(monkeypatch, load_fixture("cspro.html"))
    items = asyncio.run(cspro.CsproSource().fetch())
    assert len(items) >= 1


def test_fetch_empty_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def fake_fetch_text(url: str, **_: object) -> str:
        return "<html><body>空页面</body></html>"

    monkeypatch.setattr(cspro, "fetch_text", fake_fetch_text)
    with pytest.raises(SourceError):
        asyncio.run(cspro.CsproSource().fetch())
