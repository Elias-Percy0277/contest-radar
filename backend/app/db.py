"""数据库连接与会话管理（SQLite，SQLAlchemy 2.0）。

- 默认库文件：backend/data/contests.db（相对本文件定位，不依赖 CWD）
- 环境变量 CONTEST_RADAR_DB 可覆盖路径（测试用临时库）
- 时间戳列以 ISO8601 字符串存储，无 SQLite 时区陷阱
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

# backend/ 目录
BACKEND_DIR = Path(__file__).resolve().parent.parent

_engine: Engine | None = None
_SessionFactory: sessionmaker | None = None


def database_url(path: str | Path | None = None) -> str:
    """SQLite 连接串；优先环境变量 CONTEST_RADAR_DB，其次默认 data/contests.db。"""
    db_path = str(path or os.environ.get("CONTEST_RADAR_DB") or (BACKEND_DIR / "data" / "contests.db"))
    return f"sqlite:///{db_path}"


def get_engine() -> Engine:
    """惰性创建全局 engine（首次调用时读取环境变量）。"""
    global _engine, _SessionFactory
    if _engine is None:
        url = database_url()
        # 确保目录存在
        if url.startswith("sqlite:///") and url != "sqlite://":
            Path(url[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 15},
            echo=False,
        )
        # SQLite 开 WAL，减少并发读写锁冲突
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False, autoflush=False)
    return _engine


def reset_engine() -> None:
    """重置全局 engine（测试切换临时库时用）。"""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None


def get_session() -> Session:
    """创建新会话（调用方负责关闭）。"""
    get_engine()
    assert _SessionFactory is not None
    return _SessionFactory()


def session_scope() -> Iterator[Session]:
    """with 语法糖：自动提交/回滚/关闭。"""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """建表（幂等）。"""
    Base.metadata.create_all(get_engine())


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每请求一个会话。"""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---- AppMeta 读写工具 ----

def meta_get(session: Session, key: str) -> str | None:
    """读全局元数据。"""
    from app.models import AppMeta
    row = session.get(AppMeta, key)
    return row.value if row is not None else None


def meta_set(session: Session, key: str, value: str) -> None:
    """写全局元数据（upsert）。"""
    from app.models import AppMeta
    row = session.get(AppMeta, key)
    if row is None:
        session.add(AppMeta(key=key, value=value))
    else:
        row.value = value
