"""API 冒烟测试（TestClient + 临时库）：SPEC 第 4 节端点全覆盖。"""
from __future__ import annotations

from datetime import timedelta

from app.db import get_session
from app.models import Contest
from app.services.dedup import upsert_contest
from app.utils.timeutil import iso, now_local, today_local


def _seed_rows(n: int = 3) -> None:
    """铺几条基础数据：第 2 条 ignored、第 3 条无截止。"""
    today = today_local()
    rows = [
        {
            "title": "算法大赛甲", "url": "https://api.example.com/a", "category": "算法竞赛",
            "reg_deadline": (today + timedelta(days=5)).isoformat(),
            "contest_start": (today + timedelta(days=30)).isoformat(),
            "summary": "甲比赛",
        },
        {
            "title": "算法大赛乙", "url": "https://api.example.com/b", "category": "算法竞赛",
            "reg_deadline": (today + timedelta(days=2)).isoformat(),
            "summary": "乙比赛",
        },
        {
            "title": "认证考试丙", "url": "https://api.example.com/c", "category": "认证考试",
            "summary": "丙认证，暂无日期",
        },
    ]
    with get_session() as session:
        for i, raw in enumerate(rows[:n]):
            contest, _, _ = upsert_contest(session, raw, "seed", "种子")
            if i == 1:
                contest.my_status = "ignored"
        session.commit()


def test_list_contests_excludes_ignored_by_default(client) -> None:
    _seed_rows()
    resp = client.get("/api/contests")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(it["my_status"] != "ignored" for it in data["items"])
    # 默认按截止升序：丙无截止排最后
    titles = [it["title"] for it in data["items"]]
    assert titles == ["算法大赛甲", "认证考试丙"]


def test_hidden_includes_ignored(client) -> None:
    _seed_rows()
    data = client.get("/api/contests", params={"hidden": 1}).json()
    assert data["total"] == 3


def test_filter_and_search(client) -> None:
    _seed_rows()
    data = client.get("/api/contests", params={"category": "认证考试"}).json()
    assert data["total"] == 1 and data["items"][0]["title"] == "认证考试丙"
    # 搜索"甲"（未被忽略）
    data = client.get("/api/contests", params={"q": "甲"}).json()
    assert data["total"] == 1 and data["items"][0]["title"] == "算法大赛甲"
    # "乙"被忽略：默认搜索不到，hidden=1 可见
    assert client.get("/api/contests", params={"q": "乙"}).json()["total"] == 0
    assert client.get("/api/contests", params={"q": "乙", "hidden": 1}).json()["total"] == 1
    data = client.get("/api/contests", params={"my_status": "ignored"}).json()
    assert data["total"] == 1


def test_sort_new(client) -> None:
    _seed_rows()
    data = client.get("/api/contests", params={"hidden": 1, "sort": "new"}).json()
    firsts = [it["first_seen"] for it in data["items"]]
    assert firsts == sorted(firsts, reverse=True)


def test_manual_contest_and_validation(client) -> None:
    resp = client.post("/api/contests/manual", json={
        "title": "手动补录赛", "url": "https://manual.example.com/x?utm_source=me",
        "category": "应用与开发", "reg_deadline": "2026-12-01",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_id"] == "manual"
    assert data["canonical_url"] == "https://manual.example.com/x"

    # 缺字段 → 400 中文
    resp = client.post("/api/contests/manual", json={"title": "缺 url"})
    assert resp.status_code == 400
    assert "url" in resp.json()["detail"]
    # 非法分类 → 400 中文
    resp = client.post("/api/contests/manual", json={
        "title": "t", "url": "https://a.com/t", "category": "不存在的分类"})
    assert resp.status_code == 400

    # 重复补录同 URL → 更新而非新增
    resp = client.post("/api/contests/manual", json={
        "title": "手动补录赛（改）", "url": "https://manual.example.com/x",
        "category": "应用与开发"})
    assert resp.status_code == 200
    assert client.get("/api/contests").json()["total"] == 1


def test_my_status_lifecycle(client) -> None:
    _seed_rows(1)
    cid = client.get("/api/contests").json()["items"][0]["id"]

    resp = client.post(f"/api/contests/{cid}/my_status", json={"value": "joined"})
    assert resp.status_code == 200 and resp.json()["my_status"] == "joined"

    resp = client.post(f"/api/contests/{cid}/my_status", json={"value": "none"})
    assert resp.status_code == 200 and resp.json()["my_status"] == "none"

    # 非法值 → 400 中文
    resp = client.post(f"/api/contests/{cid}/my_status", json={"value": "maybe"})
    assert resp.status_code == 400 and "detail" in resp.json()
    # 不存在的 id → 404 中文
    resp = client.post("/api/contests/99999/my_status", json={"value": "joined"})
    assert resp.status_code == 404 and resp.json()["detail"] == "竞赛不存在"


def test_refresh_trigger_and_status(client) -> None:
    import time

    resp = client.post("/api/refresh")
    assert resp.status_code == 200 and resp.json() == {"started": True}
    # 后台任务异步执行，短暂等待其完成记录（手动刷新强制全量）
    for _ in range(100):
        if client.stub_scheduler.calls:
            break
        time.sleep(0.02)
    assert client.stub_scheduler.calls == [True]

    data = client.get("/api/refresh/status").json()
    assert data["running"] is False
    assert data["cache_hours"] == 6
    assert {"running", "last_run", "last_ok", "cache_hours"} == set(data.keys())


def test_sources_empty_then_list(client) -> None:
    assert client.get("/api/sources").json() == []


def test_stats_shape_and_values(client) -> None:
    _seed_rows()
    with get_session() as session:
        contest, _, _ = upsert_contest(session, {
            "title": "已报名的赛", "url": "https://api.example.com/j",
            "category": "算法竞赛",
            "reg_deadline": (today_local() + timedelta(days=1)).isoformat(),
            "summary": "j",
        }, "seed", "种子")
        contest.my_status = "joined"
        session.commit()

    data = client.get("/api/stats").json()
    assert set(data.keys()) == {"by_category", "by_status", "weekly_new", "upcoming_deadlines",
                                "joined_count", "last_refresh", "sources"}
    assert data["by_category"].get("算法竞赛") == 3
    assert data["joined_count"] == 1
    assert len(data["weekly_new"]) == 8
    assert all(set(w.keys()) == {"week", "count"} for w in data["weekly_new"])
    # 即将截止 joined 优先
    assert data["upcoming_deadlines"][0]["title"] == "已报名的赛"
    # 种子都是今天 first_seen → 本周新增 ≥ 4
    this_week = data["weekly_new"][-1]["count"]
    assert this_week >= 4


def test_cors_headers_for_vite_origins(client) -> None:
    resp = client.get("/api/contests", headers={"Origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    resp = client.get("/api/contests", headers={"Origin": "http://127.0.0.1:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"


def test_error_shape_is_chinese_detail(client) -> None:
    resp = client.get("/api/contests", params={"my_status": "wat"})
    assert resp.status_code == 400
    assert set(resp.json().keys()) == {"detail"}
    assert resp.json()["detail"] == "my_status 只能是 joined/ignored/none"
