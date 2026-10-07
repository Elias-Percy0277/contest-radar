"""去重合并（SPEC 第 3/5 节）：以 canonical_url 为唯一键 upsert。

- 已存在：更新可变字段 + last_updated；**绝不动 my_status / first_seen**
- 不存在：插入并置 first_seen = last_updated = now，my_status = "none"
- 返回 (contest, is_new, is_changed)：is_changed 表示业务字段实质变化（供 LLM 层判断是否重新加工）

覆盖策略：raw 中为 None/[]/"" 的字段不覆盖已有非空值（抓不到 ≠ 信息消失），避免抖动。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Contest
from app.services.normalize import normalize_url
from app.services.status import derive_is_new, derive_status_of
from app.utils.timeutil import iso, now_local

# 可变字段：raw 值非空时与现值比较，不同则覆盖并计为 changed
_MUTABLE_FIELDS = (
    "title", "category", "reg_start", "reg_deadline", "contest_start", "contest_end",
    "organizer", "prize", "eligibility", "requirements", "ai_policy", "tags",
)


def _norm_value(field: str, value: Any) -> Any:
    """字段间统一比较口径。"""
    if field == "tags":
        return sorted(str(t) for t in (value or []))
    if value is None:
        return None
    return value


def _is_empty(field: str, value: Any) -> bool:
    if field == "tags":
        return not value
    return value is None or (isinstance(value, str) and value.strip() == "")


def sanitize_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """把 ContestRaw 清洗为可入库形态（未知字段忽略、日期字符串规范截断）。"""
    allowed = {
        "title", "url", "category", "reg_start", "reg_deadline", "contest_start",
        "contest_end", "organizer", "tags", "ai_policy", "prize", "eligibility",
        "requirements", "summary",
    }
    out: dict[str, Any] = {}
    for key in allowed:
        if key in raw and raw[key] is not None:
            out[key] = raw[key]
    # tags 统一为字符串列表
    tags = out.get("tags")
    if not isinstance(tags, (list, tuple)):
        tags = []
    out["tags"] = [str(t) for t in tags]
    # ai_policy 白名单（缺省/非法一律归一为 unknown）
    raw_policy = str(out.get("ai_policy") or "unknown").strip().lower()
    out["ai_policy"] = raw_policy if raw_policy in ("allowed", "forbidden", "unknown") else "unknown"
    # 日期字段只保留 YYYY-MM-DD（容忍 "2026-10-07 00:00:00" 之类输入）
    for key in ("reg_start", "reg_deadline", "contest_start", "contest_end"):
        val = out.get(key)
        if isinstance(val, str) and val:
            out[key] = val[:10]
    return out


def upsert_contest(
    session: Session,
    raw: dict[str, Any],
    source_id: str,
    source_name: str,
    now: str | None = None,
) -> tuple[Contest, bool, bool]:
    """按 canonical_url 去重入库。返回 (行, 是否新增, 是否实质变更)。调用方负责 commit。"""
    ts = now or iso(now_local())
    clean = sanitize_raw(raw)

    title = str(clean.get("title") or "").strip()
    url = str(clean.get("url") or "").strip()
    canonical = normalize_url(url)
    if not title or not canonical:
        raise ValueError("ContestRaw 缺少必填字段 title 或 url")

    existing = session.scalars(
        select(Contest).where(Contest.canonical_url == canonical)
    ).first()

    if existing is None:
        contest = Contest(
            source_id=source_id,
            source_name=source_name,
            url=url,
            canonical_url=canonical,
            title=title,
            category=str(clean.get("category") or "综合学科"),
            reg_start=clean.get("reg_start"),
            reg_deadline=clean.get("reg_deadline"),
            contest_start=clean.get("contest_start"),
            contest_end=clean.get("contest_end"),
            organizer=clean.get("organizer"),
            tags=clean.get("tags") or [],
            ai_policy=clean.get("ai_policy") or "unknown",
            prize=clean.get("prize"),
            eligibility=clean.get("eligibility"),
            requirements=clean.get("requirements"),
            summary=clean.get("summary"),
            summary_by=None,
            my_status="none",
            first_seen=ts,
            last_updated=ts,
            status=derive_status_of(clean),
            is_new=True,
        )
        session.add(contest)
        session.flush()
        return contest, True, True

    # --- 已存在：更新可变字段 ---
    changed = False
    for field in _MUTABLE_FIELDS:
        new_val = clean.get(field)
        if _is_empty(field, new_val):
            continue
        old_val = getattr(existing, field)
        if _norm_value(field, old_val) != _norm_value(field, new_val):
            setattr(existing, field, new_val)
            changed = True

    # 原始 URL 变化（canonical 相同）也覆盖
    if url and url != existing.url:
        existing.url = url
        changed = True
    if source_name and source_name != existing.source_name:
        existing.source_name = source_name

    # 摘要：raw 带了新原文 → 覆盖并标记待重新加工（summary_by=None）
    raw_summary = clean.get("summary")
    if raw_summary and raw_summary != existing.summary:
        existing.summary = raw_summary
        existing.summary_by = None
        changed = True

    existing.last_updated = ts
    existing.status = derive_status_of(existing)
    existing.is_new = derive_is_new(existing.first_seen)
    return existing, False, changed
