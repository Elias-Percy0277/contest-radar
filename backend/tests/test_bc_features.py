"""B/C 批次新特性测试：AI政策筛选/后端分页/CSV导出/周报/深挖日期/自动深挖触发。"""
from __future__ import annotations

from typing import Any

import pytest


def _seed(n: int = 3) -> list[int]:
    from app.db import get_session
    from app.models import Contest

    policies = ("allowed", "forbidden", "unknown")
    ids: list[int] = []
    db = get_session()
    try:
        for i in range(n):
            c = Contest(
                source_id="t", source_name="测试",
                title=f"测试竞赛编号{i}",
                url=f"https://example.com/c{i}",
                canonical_url=f"https://example.com/c{i}",
                category="算法竞赛",
                ai_policy=policies[i % 3],
                reg_deadline="2099-01-0" + str(i + 1),
                first_seen=__import__("app.utils.timeutil", fromlist=["iso", "now_local"]).iso(
                    __import__("app.utils.timeutil", fromlist=["iso", "now_local"]).now_local()
                ),
            )
            db.add(c)
            db.commit()
            ids.append(c.id)
        return ids
    finally:
        db.close()


def test_ai_policy_filter_and_pagination(client: Any) -> None:
    _seed(3)
    r = client.get("/api/contests", params={"ai_policy": "allowed"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert all(it["ai_policy"] == "allowed" for it in data["items"])

    r2 = client.get("/api/contests", params={"page": 1, "page_size": 2})
    d2 = r2.json()
    assert len(d2["items"]) <= 2
    assert d2["page"] == 1 and d2["page_size"] == 2
    assert d2["total"] >= 3


def test_csv_export(client: Any) -> None:
    _seed(2)
    r = client.get("/api/contests.csv")
    assert r.status_code == 200
    assert "csv" in r.headers.get("content-type", "")
    body = r.content.decode("utf-8")
    assert body.startswith("\ufeff")
    assert "标题" in body and "测试竞赛" in body


def test_weekly_report_fallback(client: Any) -> None:
    _seed(2)
    r = client.get("/api/weekly-report")
    assert r.status_code == 200
    data = r.json()
    assert data["text"]
    assert "generated_at" in data
    assert data["new_count"] >= 2


def test_deepdive_extracts_dates(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import routes as routes_mod
    from app.llm.client import LLMClient

    ids = _seed(1)

    async def _fake_detail(url: str) -> str:
        return "报名截止 2026-10-20，比赛 2026-11-01 至 2026-11-02。允许使用 AI。" * 30

    async def _fake_deep(self: LLMClient, contest: dict, detail_text: str) -> dict:
        return {
            "ai_policy": "allowed",
            "reg_deadline": "2026-10-20",
            "contest_start": "2026-11-01",
            "contest_end": "2026-11-02",
        }

    monkeypatch.setattr(routes_mod, "fetch_detail_text", _fake_detail)
    monkeypatch.setattr(LLMClient, "deep_dive", _fake_deep)
    r = client.post(f"/api/contests/{ids[0]}/deepdive")
    assert r.status_code == 200
    data = r.json()
    assert data["reg_deadline"] == "2026-10-20"
    assert data["contest_start"] == "2026-11-01"
    assert "reg_deadline" in data["deepdive_changed"]


def test_join_triggers_auto_deepdive(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import routes as routes_mod

    ids = _seed(1)
    called: list[int] = []

    async def _fake_auto(contest_id: int) -> None:
        called.append(contest_id)

    monkeypatch.setattr(routes_mod, "_auto_deepdive", _fake_auto)
    r = client.post(f"/api/contests/{ids[0]}/my_status", json={"value": "joined"})
    assert r.status_code == 200
    assert called == [ids[0]]

    called.clear()
    r2 = client.post(f"/api/contests/{ids[0]}/my_status", json={"value": "none"})
    assert r2.status_code == 200
    assert called == []  # 取消标记不触发
