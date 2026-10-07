"""status / is_new 派生（SPEC 第 3 节，按 Asia/Shanghai 本地时区计算）。

status 优先级（从上到下）：
1. contest_end < 今天 → ended
2. contest_start ≤ 今天 ≤ contest_end → ongoing
3. contest_start ≤ 今天 且 contest_end 为 null → ongoing
4. reg_deadline ≥ 今天 且（reg_start 为 null 或 ≤ 今天）且（contest_start 为 null 或 > 今天）→ registering
5. 其余（无任何日期）→ unknown
"""
from __future__ import annotations

from datetime import date, datetime

from app.utils.timeutil import LOCAL_TZ, now_local, parse_date

# 合法状态枚举
STATUSES = ("registering", "ongoing", "ended", "unknown")


def derive_status(
    reg_start: str | None = None,
    reg_deadline: str | None = None,
    contest_start: str | None = None,
    contest_end: str | None = None,
    today: date | None = None,
) -> str:
    """按 SPEC 优先级推导状态；today 缺省取 Asia/Shanghai 当前日期（便于测试注入）。"""
    if today is None:
        today = now_local().date()

    rs = parse_date(reg_start)
    rd = parse_date(reg_deadline)
    cs = parse_date(contest_start)
    ce = parse_date(contest_end)

    if ce is not None and ce < today:
        return "ended"
    if cs is not None and cs <= today and (ce is None or ce >= today):
        return "ongoing"
    if cs is not None and cs <= today and ce is None:
        return "ongoing"  # 与上一条合并的等价形式（保留显式分支以便对照 SPEC）
    if (
        rd is not None
        and rd >= today
        and (rs is None or rs <= today)
        and (cs is None or cs > today)
    ):
        return "registering"
    return "unknown"


def derive_status_of(row, today: date | None = None) -> str:
    """从 ORM 行/字典推导状态。"""
    if isinstance(row, dict):
        return derive_status(row.get("reg_start"), row.get("reg_deadline"),
                             row.get("contest_start"), row.get("contest_end"), today)
    return derive_status(row.reg_start, row.reg_deadline, row.contest_start, row.contest_end, today)


def derive_is_new(first_seen: str | datetime | None, now: datetime | None = None) -> bool:
    """is_new：first_seen 距今 < 48 小时。解析失败一律视为不新。"""
    if now is None:
        now = now_local()
    if isinstance(first_seen, str):
        dt = None
        if first_seen:
            try:
                dt = datetime.fromisoformat(first_seen)
            except ValueError:
                dt = None
    else:
        dt = first_seen
    if dt is None:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return (now - dt).total_seconds() < 48 * 3600
