"""时间工具：全项目统一使用 Asia/Shanghai 时区（SPEC 第 3 节）。

所有时间戳以 ISO8601 带时区字符串存库，保证 API 输出直接可用、字典序与时间序一致。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# 本地时区（固定 Asia/Shanghai）
LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def now_local() -> datetime:
    """当前时间（Asia/Shanghai，带时区）。"""
    return datetime.now(LOCAL_TZ)


def today_local() -> date:
    """当前日期（Asia/Shanghai）。"""
    return now_local().date()


def iso(dt: datetime) -> str:
    """datetime → ISO8601 带时区字符串（秒级）。"""
    return dt.astimezone(LOCAL_TZ).replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    """ISO8601 字符串 → datetime（带时区；无时区信息按本地时区补齐）。失败返回 None。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt


def parse_date(value: str | None) -> date | None:
    """"YYYY-MM-DD" → date；非法/空返回 None。"""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def add_days(d: date | None, days: int) -> date | None:
    """日期加天数（None 透传）。"""
    if d is None:
        return None
    return d + timedelta(days=days)


def iso_week_label(d: date) -> str:
    """ISO 周标签，如 "2026-W40"。"""
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"
