"""调度器测试：并发抓取 / 超时重试 / 缓存跳过 / 源健康 / LLM 规则降级。

用桩解析器替换 instantiate_parser，不触网。
"""
from __future__ import annotations

from typing import Any

import pytest
import yaml
from sqlalchemy import select

from app.db import get_session
from app.fetcher import scheduler as sched_mod
from app.fetcher.base import SourceError
from app.fetcher.scheduler import Scheduler, load_sources
from app.models import Contest, SourceHealth

RAW_A = {
    "title": "调度测试赛 A", "url": "https://sched.example.com/a?utm_source=x",
    "category": "算法竞赛", "reg_deadline": "2099-01-01",
    "summary": "这是调度测试赛 A 的原始介绍文本，" + "细节" * 80,
}
RAW_B = {
    "title": "调度测试赛 B", "url": "https://sched.example.com/b",
    "category": "认证考试",
}


class FakeSource:
    """成功源：返回固定两条 ContestRaw。"""

    source_id = "fake_ok"
    name = "成功源"
    method = "http"

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params = params or {}

    async def fetch(self) -> list[dict[str, Any]]:
        return [dict(RAW_A), dict(RAW_B)]


class FlakySource:
    """总是失败的源：抛 SourceError。"""

    source_id = "fake_bad"
    name = "失败源"
    method = "http"

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params = params or {}
        self.calls = 0

    async def fetch(self) -> list[dict[str, Any]]:
        raise SourceError("模拟页面改版，解析失败")


@pytest.fixture()
def no_retry_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sched_mod, "_RETRY_BACKOFF_SECONDS", 0.01)


def _write_sources(path: Any, sources: list[dict[str, Any]]) -> None:
    path.write_text(yaml.safe_dump({"sources": sources}, allow_unicode=True), encoding="utf-8")


@pytest.mark.asyncio
async def test_refresh_success_ingests_and_health(tmp_path, monkeypatch, no_retry_backoff) -> None:
    src = tmp_path / "sources.yaml"
    _write_sources(src, [{
        "id": "fake_ok", "name": "成功源", "method": "http",
        "parser": "app.parsers.fake.FakeSource", "enabled": True, "params": {},
    }])
    monkeypatch.setattr(sched_mod, "instantiate_parser", lambda p, params: FakeSource(params))

    sch = Scheduler(sources_path=src)
    summary = await sch.refresh(force=True)

    assert summary["started"] is True and summary["ok"] == 1
    assert summary["enriched"] == 2  # 两条新增都走了 LLM 环节（规则降级）
    with get_session() as session:
        rows = session.scalars(select(Contest)).all()
        assert len(rows) == 2
        # canonical_url 已规范化（去掉 utm）
        assert any(r.canonical_url == "https://sched.example.com/a" for r in rows)
        # 无 Key → 规则降级摘要
        for r in rows:
            assert r.summary_by == "rule"
            assert r.summary and len(r.summary) <= 120
        health = session.get(SourceHealth, "fake_ok")
        assert health is not None and health.last_ok and health.last_error is None


@pytest.mark.asyncio
async def test_cache_skip_within_window(tmp_path, monkeypatch, no_retry_backoff) -> None:
    src = tmp_path / "sources.yaml"
    _write_sources(src, [{
        "id": "fake_ok", "name": "成功源", "method": "http",
        "parser": "app.parsers.fake.FakeSource", "enabled": True,
    }])
    calls: list[int] = []

    class CountingFake(FakeSource):
        async def fetch(self) -> list[dict[str, Any]]:
            calls.append(1)
            return await super().fetch()

    monkeypatch.setattr(sched_mod, "instantiate_parser", lambda p, params: CountingFake(params))

    sch = Scheduler(sources_path=src)
    await sch.refresh(force=True)
    assert len(calls) == 1
    # 非强制：6h 内命中缓存 → 跳过真实抓取
    summary = await sch.refresh(force=False)
    assert summary["skipped_cache"] == 1
    assert len(calls) == 1
    # 强制：重新抓取，条目 upsert 而非重复插入
    summary = await sch.refresh(force=True)
    assert len(calls) == 2
    with get_session() as session:
        assert len(session.scalars(select(Contest)).all()) == 2


@pytest.mark.asyncio
async def test_failure_retries_and_health_error(tmp_path, monkeypatch, no_retry_backoff) -> None:
    src = tmp_path / "sources.yaml"
    _write_sources(src, [
        {"id": "fake_bad", "name": "失败源", "method": "http",
         "parser": "app.parsers.fake.FlakySource", "enabled": True},
        {"id": "disabled_src", "name": "停用源", "method": "http",
         "parser": "app.parsers.fake.Never", "enabled": False},
    ])
    attempts: list[int] = []

    class CountingFlaky(FlakySource):
        async def fetch(self) -> list[dict[str, Any]]:
            attempts.append(1)
            return await super().fetch()

    monkeypatch.setattr(sched_mod, "instantiate_parser", lambda p, params: CountingFlaky(params))

    sch = Scheduler(sources_path=src)
    summary = await sch.refresh(force=True)

    assert summary["failed"] == 1  # 停用源不参与
    assert len(attempts) == 3  # 初次 + 重试 2 次
    with get_session() as session:
        health = session.get(SourceHealth, "fake_bad")
        assert health is not None
        assert health.last_ok is None
        assert "模拟页面改版" in (health.last_error or "")
        # 停用源不该被创建健康行（refresh 只处理 enabled）
        assert session.get(SourceHealth, "disabled_src") is None


@pytest.mark.asyncio
async def test_mixed_sources_partial_success(tmp_path, monkeypatch, no_retry_backoff) -> None:
    src = tmp_path / "sources.yaml"
    _write_sources(src, [
        {"id": "fake_ok", "name": "成功源", "parser": "app.parsers.fake.FakeSource"},
        {"id": "fake_bad", "name": "失败源", "parser": "app.parsers.fake.FlakySource"},
    ])

    def _factory(path: str, params: dict[str, Any]) -> Any:
        return FakeSource(params) if "Fake" in path else FlakySource(params)

    monkeypatch.setattr(sched_mod, "instantiate_parser", _factory)
    sch = Scheduler(sources_path=src)
    summary = await sch.refresh(force=True)

    assert summary["ok"] == 1 and summary["failed"] == 1
    with get_session() as session:
        assert len(session.scalars(select(Contest)).all()) == 2  # 失败源不拖累成功源


@pytest.mark.asyncio
async def test_playwright_timeout_uses_config(tmp_path, monkeypatch, no_retry_backoff) -> None:
    """playwright 源使用 playwright_timeout_seconds（60s 配置透传给 wait_for）。"""
    src = tmp_path / "sources.yaml"
    _write_sources(src, [{
        "id": "fake_pw", "name": "浏览器源", "method": "playwright",
        "parser": "app.parsers.fake.PwSource", "enabled": True,
    }])
    seen_timeouts: list[float] = []

    async def spy_wait_for(coro: Any, timeout: float) -> Any:
        seen_timeouts.append(timeout)
        return await coro

    monkeypatch.setattr(sched_mod, "_wait_for", spy_wait_for)
    monkeypatch.setattr(sched_mod, "instantiate_parser", lambda p, params: FakeSource(params))

    sch = Scheduler(sources_path=src)
    await sch.refresh(force=True)
    assert seen_timeouts == [sch.config.fetch.playwright_timeout_seconds]


def test_load_sources_missing_file(tmp_path, capsys) -> None:
    assert load_sources(tmp_path / "nope.yaml") == []
    assert "未找到信息源配置" in capsys.readouterr().out
