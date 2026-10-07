"""深挖端点测试：无 Key 503；正常路径更新字段并打"已深挖"标签。全程不触网。"""
from __future__ import annotations

from typing import Any

import pytest


def _seed_one() -> int:
    from app.db import get_session
    from app.models import Contest

    db = get_session()
    try:
        c = Contest(
            source_id="t",
            source_name="测试",
            title="某算法竞赛",
            url="https://example.com/contest",
            canonical_url="https://example.com/contest",
            category="算法竞赛",
        )
        db.add(c)
        db.commit()
        return c.id
    finally:
        db.close()


def _fake_detail(text: str = "比赛规则正文" * 120) -> Any:
    async def _fetch(url: str) -> str:
        return text

    return _fetch


def test_deepdive_without_llm_key_returns_503(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import routes as routes_mod

    cid = _seed_one()
    monkeypatch.setattr(routes_mod, "fetch_detail_text", _fake_detail())
    resp = client.post(f"/api/contests/{cid}/deepdive")
    assert resp.status_code == 503
    assert "Key" in resp.json()["detail"] or "深挖" in resp.json()["detail"]


def test_deepdive_updates_fields_and_tag(client: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import routes as routes_mod
    from app.llm.client import LLMClient

    cid = _seed_one()
    monkeypatch.setattr(routes_mod, "fetch_detail_text", _fake_detail("本届比赛允许使用 AI 辅助编程" * 60))

    async def _fake_deep(self: LLMClient, contest: dict, detail_text: str) -> dict:
        return {
            "ai_policy": "allowed",
            "policy_evidence": "允许使用 AI 辅助编程",
            "requirements": "全日制在校生，每队 1-3 人",
        }

    monkeypatch.setattr(LLMClient, "deep_dive", _fake_deep)
    resp = client.post(f"/api/contests/{cid}/deepdive")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ai_policy"] == "allowed"
    assert data["requirements"] == "全日制在校生，每队 1-3 人"
    assert "已深挖" in data["tags"]
    assert "ai_policy" in data["deepdive_changed"]


def test_deepdive_404(client: Any) -> None:
    resp = client.post("/api/contests/99999/deepdive")
    assert resp.status_code == 404
