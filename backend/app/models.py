"""SQLAlchemy 2.0 数据模型（SPEC 第 3 节）。

- Contest：竞赛条目主表；canonical_url 唯一键去重；my_status / first_seen 由框架维护
- SourceHealth：信息源健康状态（源健康面板数据）
- AppMeta：全局键值元数据（最近一次刷新时间等），SPEC 未禁止的内部辅助表

时间戳列统一存 ISO8601 带时区字符串（Asia/Shanghai）。
status / is_new 属于派生字段：列值在刷新时写入便于调试统计，API 读取时动态重算为准。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """全局 ORM Base。"""


class Contest(Base):
    """竞赛条目 = ContestRaw（SPEC 第 3 节）+ 框架补齐字段。"""

    __tablename__ = "contest"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # --- 框架补齐：来源标识 ---
    source_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    source_name: Mapped[str] = mapped_column(String(128), default="")
    # 详情页原始 URL（保留展示）；canonical_url 为去重唯一键
    url: Mapped[str] = mapped_column(Text, default="")
    canonical_url: Mapped[str] = mapped_column(Text, unique=True, index=True)

    # --- ContestRaw 业务字段 ---
    title: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(32), default="", index=True)
    # "YYYY-MM-DD" 或 None
    reg_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    reg_deadline: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    contest_start: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    contest_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    organizer: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    # allowed / forbidden / unknown
    ai_policy: Mapped[str] = mapped_column(String(16), default="unknown")
    prize: Mapped[str | None] = mapped_column(Text, nullable=True)
    eligibility: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # llm / rule（summary 由谁生成）
    summary_by: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # --- 框架补齐：用户与生命周期 ---
    # none / joined / ignored —— 用户手动标记，任何抓取流程绝不覆盖
    my_status: Mapped[str] = mapped_column(String(16), default="none", index=True)
    first_seen: Mapped[str] = mapped_column(String(40), default="")
    last_updated: Mapped[str] = mapped_column(String(40), default="")
    # 派生字段快照（ended/ongoing/registering/unknown；读取时以动态计算为准）
    status: Mapped[str] = mapped_column(String(16), default="unknown", index=True)
    is_new: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("ix_contest_title", "title"),
    )

    def to_dict(self, status: str | None = None, is_new: bool | None = None) -> dict[str, Any]:
        """序列化为 API JSON（SPEC 第 3/4 节字段全集）。

        status / is_new 允许调用方传入动态计算值；缺省时用列内快照。
        """
        return {
            "id": self.id,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "url": self.url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "category": self.category,
            "reg_start": self.reg_start,
            "reg_deadline": self.reg_deadline,
            "contest_start": self.contest_start,
            "contest_end": self.contest_end,
            "organizer": self.organizer,
            "tags": list(self.tags or []),
            "ai_policy": self.ai_policy or "unknown",
            "prize": self.prize,
            "eligibility": self.eligibility,
            "requirements": self.requirements,
            "summary": self.summary,
            "summary_by": self.summary_by,
            "status": status or self.status,
            "my_status": self.my_status,
            "first_seen": self.first_seen,
            "last_updated": self.last_updated,
            "is_new": bool(self.is_new) if is_new is None else bool(is_new),
        }


class SourceHealth(Base):
    """信息源健康状态（/api/sources 与源缓存判断依据）。"""

    __tablename__ = "source_health"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    # http / api / playwright
    method: Mapped[str] = mapped_column(String(16), default="http")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_ok: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "method": self.method,
            "enabled": bool(self.enabled),
            "last_run": self.last_run,
            "last_ok": self.last_ok,
            "last_error": self.last_error,
        }


class AppMeta(Base):
    """全局键值元数据（last_run / last_ok 等刷新状态）。"""

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
