"""候选源测试：ccsp / ccf_cert（服务端渲染，正常解析）+ cacc（SPA 空壳 → SourceError）。"""
from __future__ import annotations

import asyncio

import pytest

from app.fetcher.base import SourceError
from app.parsers import cacc, ccf_cert, ccsp


def test_ccsp_bulletin_list() -> None:
    from conftest import assert_contest_raw, load_fixture

    items = ccsp.CcspSource().parse(load_fixture("ccsp.html"))
    assert len(items) >= 1, "CCSP 公告至少解析出 1 条"
    for it in items:
        assert_contest_raw(it)
        assert it["organizer"] == "CCF"
    # 软文类公告（金奖说/经验分享）按关键词过滤
    assert not any("金奖说" in i["title"] for i in items)
    # "2026 CCF CCSP竞赛将于10月21~22日举办" → contest_start=2026-10-21
    host = [i for i in items if "举办" in i["title"]]
    assert any(i["contest_start"] == "2026-10-21" for i in host), "应从标题尽力提取举办日期"


def test_ccf_cert_cards() -> None:
    from conftest import assert_contest_raw, load_fixture

    items = ccf_cert.CcfCertSource().parse(load_fixture("ccf_cert.html"))
    assert len(items) >= 1, "认证项目卡片至少解析出 1 条"
    for it in items:
        assert_contest_raw(it)
        assert it["category"] == "认证考试"
    names = [t for i in items for t in i["tags"] if t in {"CSP", "PTA", "GESP", "LMCC"}]
    assert "CSP" in names, "认证页应含 CSP 项目卡片"


def test_cacc_spa_shell_raises_source_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """cacc 官网是 SPA 空壳：解析为 0 条 → fetch 抛带原因的 SourceError（不裸崩）。"""
    from conftest import load_fixture

    assert cacc.CaccSource().parse(load_fixture("cacc.html")) == []

    async def fake_fetch_text(url: str, **_: object) -> str:
        return load_fixture("cacc.html")

    monkeypatch.setattr(cacc, "fetch_text", fake_fetch_text)
    with pytest.raises(SourceError) as ei:
        asyncio.run(cacc.CaccSource().fetch())
    assert "SPA" in str(ei.value)


def test_ccsp_and_ccf_cert_fetch_patched(monkeypatch: pytest.MonkeyPatch) -> None:
    from conftest import load_fixture

    async def fake_ccsp(url: str, **_: object) -> str:
        return load_fixture("ccsp.html")

    async def fake_cert(url: str, **_: object) -> str:
        return load_fixture("ccf_cert.html")

    monkeypatch.setattr(ccsp, "fetch_text", fake_ccsp)
    monkeypatch.setattr(ccf_cert, "fetch_text", fake_cert)
    assert len(asyncio.run(ccsp.CcspSource().fetch())) >= 1
    assert len(asyncio.run(ccf_cert.CcfCertSource().fetch())) >= 1
