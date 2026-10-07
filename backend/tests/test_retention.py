"""保留清理测试（SPEC 第 3 节：joined 例外规则 + 其余规则）。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.db import get_session
from app.models import Contest
from app.services.retention import retention_cleanup, should_delete
from app.utils.timeutil import LOCAL_TZ, iso

TODAY = date(2026, 10, 7)
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=LOCAL_TZ)
TS_OLD = iso(NOW - timedelta(days=40))
TS_RECENT = iso(NOW - timedelta(days=2))


def _make(**kwargs: object) -> Contest:
    """构造测试行：默认 my_status=none、日期见参数。"""
    defaults: dict[str, object] = {
        "source_id": "t", "source_name": "t", "url": "https://t.example.com/x",
        "canonical_url": kwargs.pop("canonical_url", "https://t.example.com/x"),
        "title": "测试", "category": "算法竞赛", "tags": [],
        "my_status": "none", "first_seen": TS_OLD, "last_updated": TS_OLD,
    }
    defaults.update(kwargs)
    return Contest(**defaults)  # type: ignore[arg-type]


def _cleanup_rows(rows: list[Contest]) -> int:
    with get_session() as session:
        for r in rows:
            session.add(r)
        session.commit()
        deleted = retention_cleanup(session, now=NOW)
        session.commit()
    return deleted


def test_joined_deleted_after_end_plus_7() -> None:
    row = _make(my_status="joined", contest_end="2026-09-29", last_updated=TS_RECENT,
                canonical_url="https://t.example.com/j1")
    # end + 7 = 10-06 < today → 删
    assert should_delete(row, today=TODAY, now=NOW) is True
    assert _cleanup_rows([row]) == 1


def test_joined_kept_within_grace() -> None:
    row = _make(my_status="joined", contest_end="2026-10-03", last_updated=TS_RECENT,
                canonical_url="https://t.example.com/j2")
    # end + 7 = 10-10 ≥ today → 留
    assert should_delete(row, today=TODAY, now=NOW) is False


def test_joined_no_end_deleted_by_last_updated_30d() -> None:
    row = _make(my_status="joined", last_updated=TS_OLD, canonical_url="https://t.example.com/j3")
    assert should_delete(row, today=TODAY, now=NOW) is True
    assert _cleanup_rows([row]) == 1


def test_joined_no_end_recent_kept() -> None:
    row = _make(my_status="joined", last_updated=TS_RECENT, canonical_url="https://t.example.com/j4")
    assert should_delete(row, today=TODAY, now=NOW) is False


def test_registering_never_deleted() -> None:
    row = _make(reg_start="2026-09-01", reg_deadline="2099-01-01", last_updated=TS_OLD,
                canonical_url="https://t.example.com/r1")
    assert should_delete(row, today=TODAY, now=NOW) is False


def test_ongoing_never_deleted() -> None:
    row = _make(contest_start="2026-10-01", contest_end="2026-10-10", last_updated=TS_OLD,
                canonical_url="https://t.example.com/o1")
    assert should_delete(row, today=TODAY, now=NOW) is False


def test_ended_deleted_after_30d() -> None:
    dead = _make(contest_start="2026-08-01", contest_end="2026-09-01", last_updated=TS_RECENT,
                 canonical_url="https://t.example.com/e1")  # end+30 = 10-01 < today → 删
    alive = _make(contest_start="2026-09-01", contest_end="2026-09-15", last_updated=TS_RECENT,
                  canonical_url="https://t.example.com/e2")  # end+30 = 10-15 ≥ today → 留
    assert should_delete(dead, today=TODAY, now=NOW) is True
    assert should_delete(alive, today=TODAY, now=NOW) is False
    assert _cleanup_rows([dead, alive]) == 1


def test_unknown_deleted_after_30d_stale() -> None:
    stale = _make(last_updated=TS_OLD, canonical_url="https://t.example.com/u1")
    fresh = _make(last_updated=TS_RECENT, canonical_url="https://t.example.com/u2")
    assert should_delete(stale, today=TODAY, now=NOW) is True
    assert should_delete(fresh, today=TODAY, now=NOW) is False
    assert _cleanup_rows([stale, fresh]) == 1


def test_ignored_registering_kept_but_ended_rules_apply() -> None:
    ignored_reg = _make(my_status="ignored", reg_deadline="2099-01-01", last_updated=TS_OLD,
                        canonical_url="https://t.example.com/i1")
    ignored_old_ended = _make(my_status="ignored", contest_end="2026-01-01", last_updated=TS_RECENT,
                              canonical_url="https://t.example.com/i2")
    assert should_delete(ignored_reg, today=TODAY, now=NOW) is False
    assert should_delete(ignored_old_ended, today=TODAY, now=NOW) is True


def test_retention_cleanup_removes_from_db() -> None:
    with get_session() as session:
        session.add(_make(my_status="joined", contest_end="2026-09-01", last_updated=TS_RECENT,
                          canonical_url="https://t.example.com/g1"))
        session.add(_make(reg_deadline="2099-01-01", last_updated=TS_RECENT,
                          canonical_url="https://t.example.com/g2"))
        session.commit()
        deleted = retention_cleanup(session, now=NOW)
        session.commit()
        remain = session.scalars(select(Contest)).all()
    assert deleted == 1
    assert len(remain) == 1
    assert remain[0].canonical_url == "https://t.example.com/g2"
