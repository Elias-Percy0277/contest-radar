"""服务层：URL 规范化 / 状态推导 / 去重合并 / 保留清理。"""
from app.services.dedup import upsert_contest
from app.services.normalize import normalize_url
from app.services.retention import retention_cleanup, should_delete
from app.services.status import derive_is_new, derive_status, derive_status_of

__all__ = [
    "normalize_url",
    "derive_status",
    "derive_status_of",
    "derive_is_new",
    "upsert_contest",
    "retention_cleanup",
    "should_delete",
]
