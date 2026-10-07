"""应用入口：uvicorn app.main:app --port 8300（backend/ 目录下启动）。

lifespan 顺序：
1. 建表（幂等）
2. 距上次成功抓取超过 cache_hours → 后台任务刷新（测试可用
   CONTEST_RADAR_DISABLE_STARTUP_REFRESH=1 关闭）
3. 挂载 frontend/dist（存在时）到 /
4. 启动 1.5s 后自动打开浏览器（DISABLE_AUTO_OPEN=1 关闭）
"""
from __future__ import annotations

import asyncio
import os
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.config import get_config
from app.db import get_session, init_db, meta_get
from app.fetcher.scheduler import Scheduler
from app.utils.timeutil import parse_iso, now_local

# contest-radar 项目根（backend/app/main.py → 上两级）
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _spawn(app: FastAPI, coro) -> None:
    """创建后台任务并持有引用（防止被垃圾回收）。"""
    tasks = getattr(app.state, "_bg_tasks", None)
    if tasks is None:
        tasks = set()
        app.state._bg_tasks = tasks
    task = asyncio.get_running_loop().create_task(coro)
    tasks.add(task)
    task.add_done_callback(tasks.discard)


def _maybe_schedule_startup_refresh(app: FastAPI) -> None:
    """首次启动且距上次成功抓取超 cache_hours 时，后台静默刷新。"""
    cfg = get_config()
    with get_session() as session:
        last_ok = parse_iso(meta_get(session, "last_ok"))
    if last_ok is not None and (now_local() - last_ok).total_seconds() < cfg.fetch.cache_hours * 3600:
        return
    scheduler: Scheduler = app.state.scheduler
    _spawn(app, _quiet_refresh(scheduler))


async def _quiet_refresh(scheduler: Scheduler) -> None:
    """后台刷新；异常只打印，不影响服务。"""
    try:
        await scheduler.refresh(force=False)
    except Exception as exc:  # noqa: BLE001
        print(f"[启动刷新] 后台刷新失败（不影响服务）：{exc}")


async def _auto_open_browser(url: str) -> None:
    """启动 1.5s 后打开浏览器；DISABLE_AUTO_OPEN=1 关闭。"""
    if os.environ.get("DISABLE_AUTO_OPEN") == "1":
        return
    await asyncio.sleep(1.5)
    try:
        webbrowser.open(url)
    except Exception as exc:  # noqa: BLE001
        print(f"[启动] 自动打开浏览器失败：{exc}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # 1) 建表
    init_db()

    # 2) 调度器 + 启动刷新
    app.state.scheduler = Scheduler()
    if os.environ.get("CONTEST_RADAR_DISABLE_STARTUP_REFRESH") != "1":
        _maybe_schedule_startup_refresh(app)

    # 3) 自动打开浏览器
    cfg = get_config()
    _spawn(app, _auto_open_browser(f"http://{cfg.server.host}:{cfg.server.port}"))

    yield


def create_app() -> FastAPI:
    """构建 FastAPI 应用（CORS / 中文错误 / API 路由 / 前端静态挂载）。"""
    app = FastAPI(
        title="竞赛雷达 ContestRadar",
        version="1.0.0",
        description="单用户本地竞赛信息聚合（SPEC v1）",
        lifespan=lifespan,
    )

    # CORS：仅放行 Vite 开发服务器两个来源
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 错误统一 {"detail":"中文原因"}
    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": f"请求参数错误：{exc.errors()[:3]}"})

    @app.exception_handler(Exception)
    async def _unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": f"服务器内部错误：{type(exc).__name__}"})

    # API 路由（先注册，优先于静态挂载）
    app.include_router(api_router)

    # 前端静态挂载（frontend/dist 存在时）
    dist = PROJECT_ROOT / "frontend" / "dist"
    if dist.is_dir() and (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:
        @app.get("/", include_in_schema=False)
        async def _root() -> dict[str, str]:
            return {
                "app": "竞赛雷达 ContestRadar",
                "提示": "前端尚未构建（frontend/dist 不存在）；API 文档见 /docs",
            }

    return app


app = create_app()
