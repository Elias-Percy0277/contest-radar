"""保留清理（SPEC 第 3 节，每次刷新后执行）。

- joined：contest_end + joined_grace_days(7) 后删；end 为 null 则 last_updated + 30 天删
- 其余（含 ignored）：
  * status ∈ {registering, ongoing} 永不删
  * ended 在 contest_end + unmarked_ended_days(30) 后删
  * status unknown 在 last_updated + stale_unknown_days(30) 后删
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_config
from app.models import Contest
from app.services.status import derive_status_of
from app.utils.timeutil import add_days, now_local, parse_date, parse_iso, today_local


def _to_date(value: str | None) -> date | None:
    return parse_date(value)


def _to_dt(value: str | None) -> datetime | None:
    return parse_iso(value)


def should_delete(contest: Contest, today: date | None = None, now: datetime | None = None) -> bool:
    """判定单条是否应删除（便于单测）。"""
    cfg = get_config().retention
    if today is None:
        today = today_local()
    if now is None:
        now = now_local()

    status = derive_status_of(contest, today)

    if contest.my_status == "joined":
        end = _to_date(contest.contest_end)
        if end is not None:
            boundary = add_days(end, cfg.joined_grace_days)
            return boundary is not None and boundary < today
        # end 为 null → last_updated + 30 天（沿用未标注的天数口径）
        lu = _to_dt(contest.last_updated)
        if lu is None:
            return False
        return (now - lu).days >= cfg.stale_unknown_days

    if status in ("registering", "ongoing"):
        return False
    if status == "ended":
        end = _to_date(contest.contest_end)
        if end is None:
            # 判为 ended 却没有 end 日期（理论不可能）：按 unknown 口径兜底
            lu = _to_dt(contest.last_updated)
            return lu is not None and (now - lu).days >= cfg.stale_unknown_days
        boundary = add_days(end, cfg.unmarked_ended_days)
        return boundary is not None and boundary < today
    # unknown
    lu = _to_dt(contest.last_updated)
    if lu is None:
        return False
    return (now - lu).days >= cfg.stale_unknown_days


def retention_cleanup(session: Session, now: datetime | None = None) -> int:
    """执行保留清理，返回删除条数（调用方负责 commit）。"""
    if now is None:
        now = now_local()
    today = now.date()

    deleted = 0
    for contest in session.scalars(select(Contest)).all():
        if should_delete(contest, today=today, now=now):
            session.delete(contest)
            deleted += 1
    return deleted
