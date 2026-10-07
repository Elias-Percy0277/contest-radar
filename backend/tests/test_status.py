"""derive_status / derive_is_new 测试（SPEC 第 3 节优先级）。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.services.status import derive_is_new, derive_status
from app.utils.timeutil import LOCAL_TZ

TODAY = date(2026, 10, 7)


def test_ended_when_end_before_today() -> None:
    assert derive_status(contest_end="2026-10-06", today=TODAY) == "ended"


def test_ongoing_when_today_between_start_and_end() -> None:
    assert derive_status(contest_start="2026-10-01", contest_end="2026-10-10", today=TODAY) == "ongoing"


def test_ongoing_when_start_passed_and_end_null() -> None:
    assert derive_status(contest_start="2026-10-01", today=TODAY) == "ongoing"


def test_registering() -> None:
    assert derive_status(reg_start="2026-09-01", reg_deadline="2026-10-20",
                         contest_start="2026-11-01", today=TODAY) == "registering"
    # reg_start 为 null 也可报名中
    assert derive_status(reg_deadline="2026-10-20", today=TODAY) == "registering"
    # contest_start 为 null 也可报名中
    assert derive_status(reg_start="2026-09-01", reg_deadline="2026-10-20", today=TODAY) == "registering"


def test_registering_not_when_reg_not_open() -> None:
    # 报名还没开始
    assert derive_status(reg_start="2026-10-10", reg_deadline="2026-10-30", today=TODAY) == "unknown"


def test_registering_not_when_contest_started() -> None:
    # 比赛已开始但没填 contest_end：优先 ongoing 而非 registering
    assert derive_status(reg_deadline="2026-10-30", contest_start="2026-10-01", today=TODAY) == "ongoing"


def test_unknown_when_no_dates() -> None:
    assert derive_status(today=TODAY) == "unknown"


def test_ended_priority_over_ongoing_rules() -> None:
    # 结束日期早于今天：即使看起来"报名未截止"也判 ended
    assert derive_status(reg_deadline="2026-10-30", contest_start="2026-09-01",
                         contest_end="2026-10-02", today=TODAY) == "ended"


def test_is_new_within_48h() -> None:
    now = datetime(2026, 10, 7, 12, 0, tzinfo=LOCAL_TZ)
    fresh = "2026-10-06T13:00:00+08:00"
    old = "2026-10-05T12:00:00+08:00"
    assert derive_is_new(fresh, now) is True
    assert derive_is_new(old, now) is False
    assert derive_is_new(None, now) is False


def test_is_new_naive_string() -> None:
    now = datetime(2026, 10, 7, 12, 0, tzinfo=LOCAL_TZ)
    assert derive_is_new("2026-10-07T11:00:00", now) is True
    assert derive_is_new("garbage", now) is False
