"""牛客首页解析器测试（fixture：nowcoder.html，2026-10 抓取）。"""
from __future__ import annotations

import asyncio
from datetime import date

import pytest

from app.fetcher.base import SourceError
from app.parsers import nowcoder
from app.parsers._util import parse_relative_time


def test_parse_signup_items() -> None:
    from conftest import assert_contest_raw, load_fixture

    items = nowcoder.NowcoderSource().parse(load_fixture("nowcoder.html"))
    assert len(items) >= 1, "首页应有报名中的比赛"
    for it in items:
        assert_contest_raw(it)
        assert it["category"] == "算法竞赛"
        assert "/acm/contest/" in it["url"]
    # 比赛结束的条目必须被过滤
    assert not any("集训派对" in i["title"] for i in items), "已结束比赛不应出现"


def test_fetch_via_patched_network(monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import load_fixture

    async def fake_fetch_text(url: str, **_: object) -> str:
        return load_fixture("nowcoder.html")

    monkeypatch.setattr(nowcoder, "fetch_text", fake_fetch_text)
    items = asyncio.run(nowcoder.NowcoderSource().fetch())
    assert len(items) >= 1


def test_relative_time_conversion() -> None:
    """相对时间换算：以固定基准日避免测试随日期漂移。"""
    base = date(2026, 10, 7)
    assert parse_relative_time("2天后 19:00", base=base) == date(2026, 10, 9)
    assert parse_relative_time("今天 12:00", base=base) == base
    assert parse_relative_time("明天 19:00", base=base) == date(2026, 10, 8)
    assert parse_relative_time("后天 19:00", base=base) == date(2026, 10, 9)
    assert parse_relative_time("1天前 12:00", base=base) == date(2026, 10, 6)
    assert parse_relative_time("3小时后", base=base) == base
    assert parse_relative_time("2026-10-21 09:00", base=base) == date(2026, 10, 21)
    assert parse_relative_time("2026年10月21日", base=base) == date(2026, 10, 21)
    # 换算不了 → None（调用方写 contest_start=null）
    assert parse_relative_time("敬请期待", base=base) is None
    assert parse_relative_time("", base=base) is None


def test_fetch_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_fetch_text(url: str, **_: object) -> str:
        return "<html><body></body></html>"

    monkeypatch.setattr(nowcoder, "fetch_text", fake_fetch_text)
    with pytest.raises(SourceError):
        asyncio.run(nowcoder.NowcoderSource().fetch())
