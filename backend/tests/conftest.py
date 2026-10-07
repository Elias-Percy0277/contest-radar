"""pytest 公共夹具：每个测试独立临时 SQLite 库 + 安全环境变量。"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

# 保证能 import app 包（backend/ 为根）
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class StubScheduler:
    """API 冒烟用的调度器桩：记录调用、不真抓取。"""

    def __init__(self) -> None:
        self.running = False
        self.calls: list[bool] = []

    async def refresh(self, force: bool = False) -> dict[str, Any]:
        self.calls.append(force)
        return {"started": True, "stub": True}


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """每个测试一个临时库；禁用自动开浏览器与启动刷新。"""
    monkeypatch.setenv("CONTEST_RADAR_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("DISABLE_AUTO_OPEN", "1")
    monkeypatch.setenv("CONTEST_RADAR_DISABLE_STARTUP_REFRESH", "1")

    from app import db as db_mod

    db_mod.reset_engine()
    db_mod.init_db()
    yield db_mod
    db_mod.reset_engine()


@pytest.fixture()
def client(isolated_db: Any) -> Iterator[Any]:
    """带 lifespan 的 TestClient（scheduler 替换为桩，避免真实网络抓取）。"""
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    stub = StubScheduler()
    with TestClient(app) as c:
        c.app.state.scheduler = stub
        c.stub_scheduler = stub  # type: ignore[attr-defined]
        yield c
