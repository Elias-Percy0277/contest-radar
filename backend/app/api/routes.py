"""REST API 路由（SPEC 第 4 节，前缀 /api）。

- 错误统一 {"detail":"中文原因"}（请求体解析失败亦转中文）
- Contest 序列化时动态重算 status / is_new（与存储快照不一致则回写）
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_config
from app.db import get_db, get_session, meta_get
from app.llm.rules import CATEGORIES
from app.models import Contest, SourceHealth
from app.services.dedup import upsert_contest
from app.services.status import derive_is_new, derive_status_of
from app.utils.timeutil import iso_week_label, parse_date, today_local

router = APIRouter(prefix="/api")

_MY_STATUS_VALUES = ("none", "joined", "ignored")


# ---- 序列化与公共工具 ----

def contest_dict(session: Session, contest: Contest) -> dict[str, Any]:
    """序列化并同步派生快照（status / is_new 以实时计算为准）。"""
    status = derive_status_of(contest)
    is_new = derive_is_new(contest.first_seen)
    if contest.status != status:
        contest.status = status
    if bool(contest.is_new) != is_new:
        contest.is_new = is_new
    return contest.to_dict(status=status, is_new=is_new)


def _get_or_404(session: Session, contest_id: int) -> Contest:
    contest = session.get(Contest, contest_id)
    if contest is None:
        raise HTTPException(status_code=404, detail="竞赛不存在")
    return contest


async def _read_json_body(request: Request) -> dict[str, Any]:
    """读取 JSON 请求体；非法时抛 400（中文原因）。"""
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="请求体必须是合法 JSON") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="请求体必须是 JSON 对象")
    return body


def _get_scheduler(request: Request) -> Any:
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=503, detail="调度器尚未初始化，请稍后重试")
    return scheduler


# ---- 竞赛列表 ----

@router.get("/contests")
def list_contests(
    category: str | None = None,
    status: str | None = None,
    my_status: str | None = None,
    q: str | None = None,
    source_id: str | None = None,
    hidden: int = 0,
    sort: str = "deadline",
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """竞赛列表：默认排除 ignored；sort=deadline|new|title，默认 deadline（无截止排最后）。"""
    rows = session.scalars(select(Contest)).all()
    items = [contest_dict(session, r) for r in rows]

    if category:
        items = [it for it in items if it["category"] == category]
    if status:
        items = [it for it in items if it["status"] == status]
    if my_status:
        if my_status not in _MY_STATUS_VALUES:
            raise HTTPException(status_code=400, detail="my_status 只能是 joined/ignored/none")
        items = [it for it in items if it["my_status"] == my_status]
    elif hidden != 1:
        items = [it for it in items if it["my_status"] != "ignored"]
    if q:
        needle = q.strip().lower()
        items = [
            it for it in items
            if needle in (it["title"] or "").lower()
            or needle in (it["organizer"] or "").lower()
            or any(needle in str(t).lower() for t in it["tags"])
        ]
    if source_id:
        items = [it for it in items if it["source_id"] == source_id]

    if sort == "new":
        items.sort(key=lambda it: it["first_seen"] or "", reverse=True)
    elif sort == "title":
        items.sort(key=lambda it: it["title"] or "")
    else:  # 默认 deadline：reg_deadline 升序，无截止的排最后（内部按 first_seen 倒序）
        with_deadline = sorted(
            (it for it in items if it["reg_deadline"] is not None),
            key=lambda it: it["reg_deadline"] or "",
        )
        no_deadline = sorted(
            (it for it in items if it["reg_deadline"] is None),
            key=lambda it: it["first_seen"] or "",
            reverse=True,
        )
        items = with_deadline + no_deadline

    return {"items": items, "total": len(items)}


# ---- 我的日程标记 ----

@router.post("/contests/{contest_id}/my_status")
async def set_my_status(contest_id: int, request: Request, session: Session = Depends(get_db)) -> dict[str, Any]:
    """标记我要参加/忽略/取消；body: {"value": "joined"|"ignored"|"none"}。"""
    body = await _read_json_body(request)
    value = body.get("value")
    if value not in _MY_STATUS_VALUES:
        raise HTTPException(status_code=400, detail="my_status 只能是 joined/ignored/none")

    contest = _get_or_404(session, contest_id)
    contest.my_status = value
    session.commit()
    return contest_dict(session, contest)


# ---- 手动补录 ----

@router.post("/contests/manual")
async def add_manual_contest(request: Request, session: Session = Depends(get_db)) -> dict[str, Any]:
    """手动补录：title/url/category 必填；source_id 固定 "manual"。"""
    body = await _read_json_body(request)
    missing = [k for k in ("title", "url", "category") if not str(body.get(k) or "").strip()]
    if missing:
        raise HTTPException(status_code=400, detail=f"缺少必填字段：{'、'.join(missing)}")
    if body.get("category") not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category 必须是：{'、'.join(CATEGORIES)}")

    try:
        contest, _, _ = upsert_contest(session, body, source_id="manual", source_name="手动补录")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"补录失败：{exc}") from exc
    session.commit()
    return contest_dict(session, contest)


# ---- 刷新 ----

@router.post("/refresh")
async def trigger_refresh(request: Request) -> dict[str, Any]:
    """触发立即抓取（异步后台执行，强制全量）。已在执行中时直接返回 started=true（幂等）。"""
    import asyncio

    scheduler = _get_scheduler(request)
    if scheduler.running:
        return {"started": True}
    tasks = getattr(request.app.state, "_bg_tasks", None)
    if tasks is None:
        tasks = set()
        request.app.state._bg_tasks = tasks
    task = asyncio.get_running_loop().create_task(scheduler.refresh(force=True))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return {"started": True}


@router.get("/refresh/status")
def refresh_status(request: Request) -> dict[str, Any]:
    """刷新状态：running/last_run/last_ok/cache_hours。"""
    scheduler = getattr(request.app.state, "scheduler", None)
    with get_session() as session:
        last_run = meta_get(session, "last_run")
        last_ok = meta_get(session, "last_ok")
    return {
        "running": bool(scheduler.running) if scheduler is not None else False,
        "last_run": last_run,
        "last_ok": last_ok,
        "cache_hours": get_config().fetch.cache_hours,
    }


# ---- 源健康 ----

@router.get("/sources")
def list_sources(session: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """源健康面板数据（含 enabled=false 的候选源，以 sources.yaml 同步结果为准）。"""
    rows = session.scalars(select(SourceHealth).order_by(SourceHealth.id)).all()
    return [r.to_dict() for r in rows]


# ---- 仪表盘统计 ----

@router.get("/stats")
def stats(session: Session = Depends(get_db)) -> dict[str, Any]:
    """仪表盘：分类/状态分布、近 8 周新增、即将截止 top5（joined 优先）。"""
    rows = session.scalars(select(Contest)).all()
    items = [contest_dict(session, r) for r in rows]

    by_category: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for it in items:
        by_category[it["category"]] = by_category.get(it["category"], 0) + 1
        by_status[it["status"]] = by_status.get(it["status"], 0) + 1

    # 近 8 周（含本周）新增计数，按 first_seen 归入 ISO 周
    today: date = today_local()
    monday = today - timedelta(days=today.weekday())
    week_starts = [monday - timedelta(weeks=k) for k in range(7, -1, -1)]
    week_labels = [iso_week_label(d) for d in week_starts]
    counts = {label: 0 for label in week_labels}
    for it in items:
        first = parse_date((it["first_seen"] or "")[:10])
        if first is not None:
            label = iso_week_label(first)
            if label in counts:
                counts[label] += 1
    weekly_new = [{"week": label, "count": counts[label]} for label in week_labels]

    # 即将截止 top5：reg_deadline ≥ 今天，joined 优先，再按截止日升序
    today_str = today.isoformat()
    upcoming = [it for it in items if it["reg_deadline"] and it["reg_deadline"] >= today_str]
    upcoming.sort(key=lambda it: (0 if it["my_status"] == "joined" else 1, it["reg_deadline"]))
    upcoming_deadlines = upcoming[:5]

    with get_session() as s2:
        last_refresh = meta_get(s2, "last_run")
        sources = [r.to_dict() for r in s2.scalars(select(SourceHealth).order_by(SourceHealth.id)).all()]

    return {
        "by_category": by_category,
        "by_status": by_status,
        "weekly_new": weekly_new,
        "upcoming_deadlines": upcoming_deadlines,
        "joined_count": sum(1 for it in items if it["my_status"] == "joined"),
        "last_refresh": last_refresh,
        "sources": sources,
    }
