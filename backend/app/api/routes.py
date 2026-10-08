"""REST API 路由（SPEC 第 4 节，前缀 /api）。

- 错误统一 {"detail":"中文原因"}（请求体解析失败亦转中文）
- Contest 序列化时动态重算 status / is_new（与存储快照不一致则回写）
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_config
from app.db import get_db, get_session, meta_get, meta_set
from app.llm.rules import CATEGORIES
from app.models import Contest, SourceHealth
from app.fetcher.base import SourceError
from app.llm.client import DeepDiveError, LLMClient
from app.services.dedup import upsert_contest
from app.services.deepdive import fetch_detail_text
from app.services.status import derive_is_new, derive_status_of
from app.utils.timeutil import iso, iso_week_label, now_local, parse_date, today_local

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

def _query_contests(
    session: Session,
    *,
    category: str | None = None,
    status: str | None = None,
    my_status: str | None = None,
    q: str | None = None,
    source_id: str | None = None,
    ai_policy: str | None = None,
    hidden: int = 0,
    sort: str = "deadline",
) -> list[dict[str, Any]]:
    """列表公共查询：过滤 + 排序（列表端点与 CSV 导出共用）。"""
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
    if ai_policy:
        items = [it for it in items if it["ai_policy"] == ai_policy]
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
    return items


@router.get("/contests")
def list_contests(
    category: str | None = None,
    status: str | None = None,
    my_status: str | None = None,
    q: str | None = None,
    source_id: str | None = None,
    ai_policy: str | None = None,
    hidden: int = 0,
    sort: str = "deadline",
    page: int = 1,
    page_size: int = 0,
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """竞赛列表：默认排除 ignored；ai_policy=allowed|forbidden|unknown；
    sort=deadline|new|title；page_size>0 时后端分页（默认 0 全量，兼容旧调用）。"""
    items = _query_contests(
        session, category=category, status=status, my_status=my_status, q=q,
        source_id=source_id, ai_policy=ai_policy, hidden=hidden, sort=sort,
    )
    total = len(items)
    page = max(1, page)
    if page_size and page_size > 0:
        start = (page - 1) * page_size
        items = items[start : start + page_size]
    return {"items": items, "total": total, "page": page, "page_size": page_size or total}


@router.get("/contests.csv")
def contests_csv(
    category: str | None = None,
    status: str | None = None,
    my_status: str | None = None,
    q: str | None = None,
    source_id: str | None = None,
    ai_policy: str | None = None,
    hidden: int = 0,
    sort: str = "deadline",
    session: Session = Depends(get_db),
) -> Any:
    """CSV 导出：与列表同参数（不分页），UTF-8-BOM，Excel 可直接打开。"""
    import csv
    import io

    from fastapi.responses import Response

    items = _query_contests(
        session, category=category, status=status, my_status=my_status, q=q,
        source_id=source_id, ai_policy=ai_policy, hidden=hidden, sort=sort,
    )
    ai_text = {"allowed": "允许", "forbidden": "禁止", "unknown": "未知"}
    my_text = {"joined": "我要参加", "ignored": "已忽略", "none": ""}
    st_text = {"registering": "报名中", "ongoing": "进行中", "ended": "已结束", "unknown": "未知"}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["标题", "分类", "状态", "主办方", "报名截止", "比赛开始", "比赛结束", "AI政策", "我的状态", "链接", "摘要"])
    for it in items:
        w.writerow([
            it["title"], it["category"], st_text.get(it["status"], it["status"]),
            it["organizer"] or "", it["reg_deadline"] or "", it["contest_start"] or "",
            it["contest_end"] or "", ai_text.get(it["ai_policy"], ""),
            my_text.get(it["my_status"], ""), it["url"], (it["summary"] or "").replace("\\n", " "),
        ])
    return Response(
        content="﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=contests.csv"},
    )


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
    if value == "joined":
        # 标记参加即自动深挖（后台静默执行，补 AI 政策/赛程日期）
        import asyncio

        tasks = getattr(request.app.state, "_bg_tasks", None)
        if tasks is None:
            tasks = set()
            request.app.state._bg_tasks = tasks
        task = asyncio.get_running_loop().create_task(_auto_deepdive(contest_id))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
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


# ---- 手动深挖 ----


async def _deepdive_core(contest_id: int) -> tuple[dict[str, Any], list[str]]:
    """深挖核心流程（路由与"标记参加自动深挖"共用）。抛 ValueError（中文原因）。"""
    with get_session() as session:
        contest = session.get(Contest, contest_id)
        if contest is None:
            raise ValueError("竞赛不存在")
        try:
            detail = await fetch_detail_text(contest.url)
        except SourceError as exc:
            raise ValueError(f"详情页抓取失败：{exc}") from exc
        if not detail.strip():
            raise ValueError("详情页正文为空，无法深挖")

        client = LLMClient()
        try:
            patch = await client.deep_dive(contest.to_dict(), detail)
        except DeepDiveError as exc:
            raise ValueError(str(exc)) from exc
        finally:
            await client.aclose()

        changed: list[str] = []
        for key in ("ai_policy", "requirements", "prize", "eligibility",
                    "reg_deadline", "contest_start", "contest_end"):
            value = patch.get(key)
            if value and value != "unknown" and getattr(contest, key) != value:
                setattr(contest, key, value)
                changed.append(key)
        tags = list(contest.tags or [])
        if "已深挖" not in tags:
            tags.append("已深挖")
            contest.tags = tags
        session.commit()
        return contest_dict(session, contest), changed


@router.post("/contests/{contest_id}/deepdive")
async def deepdive_contest(contest_id: int) -> dict[str, Any]:
    """深挖：抓详情页 → LLM 抽取 AI政策/参赛要求/奖金/赛程日期 → 更新并打"已深挖"标签。"""
    try:
        data, changed = await _deepdive_core(contest_id)
    except ValueError as exc:
        msg = str(exc)
        code = 404 if msg == "竞赛不存在" else (503 if ("Key" in msg or "LLM" in msg) else 502)
        raise HTTPException(status_code=code, detail=msg) from exc
    return {**data, "deepdive_changed": changed}


async def _auto_deepdive(contest_id: int) -> None:
    """标记"我要参加"后的自动深挖（后台任务）：失败只打日志，不打扰用户。"""
    try:
        _, changed = await _deepdive_core(contest_id)
        print(f"[深挖] 自动深挖完成 id={contest_id} 更新字段: {changed or '无'}")
    except Exception as exc:  # noqa: BLE001
        print(f"[深挖] 自动深挖失败 id={contest_id}: {exc}")


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


# ---- 周报 ----

_LLM_REPORT_SYSTEM = (
    "你是竞赛信息助理。根据给出的近7天新增赛事与未来14天报名截止清单，写一份给中国大学生的中文周报："
    "第一行一句总览；然后本周新赛要点（最多5条，突出算法/AI/大厂赛事）；再截止提醒（按紧迫排序，标注剩余天数）；"
    "最后一行一句行动建议。全文不超过350字，纯文本短行，不要 markdown 标记。"
)


@router.get("/weekly-report")
async def weekly_report(force: int = 0, session: Session = Depends(get_db)) -> dict[str, Any]:
    """周报：近7天新增 + 未来14天截止（我要参加的优先）→ LLM 总结；当日结果缓存。"""
    import json as _json

    cached = meta_get(session, "weekly_report")
    if cached and not force:
        try:
            data = _json.loads(cached)
            gen = datetime.fromisoformat(str(data.get("generated_at")))
            if gen.date() == today_local():
                return data
        except Exception:
            pass  # 缓存损坏则重新生成

    rows = session.scalars(select(Contest)).all()
    items = [contest_dict(session, r) for r in rows]
    today = today_local()
    new7 = [
        it for it in items
        if it["first_seen"] and (today - (parse_date(str(it["first_seen"])[:10]) or today)).days <= 7
    ]
    soon = [
        it for it in items
        if it["reg_deadline"] and 0 <= (parse_date(it["reg_deadline"]) - today).days <= 14
    ]
    soon.sort(key=lambda it: (it["my_status"] != "joined", it["reg_deadline"] or ""))

    def _line(it: dict[str, Any]) -> str:
        d = (parse_date(it["reg_deadline"]) - today).days if it["reg_deadline"] else None
        tail = f"（截止还剩{d}天）" if d is not None else ""
        star = "★" if it["my_status"] == "joined" else ""
        return f"- {star}{it['title']}［{it['source_name']}］{tail}"

    nl = "\n"
    context = (
        "近7天新增：" + nl + nl.join(_line(i) for i in new7[:20])
        + nl + nl + "未来14天截止：" + nl + nl.join(_line(i) for i in soon[:20])
    )
    text = f"近7天新增 {len(new7)} 条赛事；未来14天有 {len(soon)} 项报名截止。" + nl + nl + context

    client = LLMClient()
    if client.available:
        out = await client.chat_text(_LLM_REPORT_SYSTEM, context)
        if out:
            text = out
        await client.aclose()

    data = {
        "text": text,
        "generated_at": iso(now_local()),
        "new_count": len(new7),
        "deadline_count": len(soon),
    }
    meta_set(session, "weekly_report", _json.dumps(data, ensure_ascii=False))
    session.commit()
    return data


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
