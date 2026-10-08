"""抓取调度器（SPEC 第 5 节）。

流程：读 sources.yaml → importlib 按 parser 字段实例化 → asyncio 并发（上限 fetch.concurrency）
→ 单源超时 http/api 30s、playwright 60s，失败重试 fetch.retries 次 → 成功入库（canonical_url
去重合并，绝不动 my_status）→ 更新源健康 → 全部结束后对新增/变更条目跑 LLM 加工 + 保留清理。

缓存：距该源 last_ok < cache_hours 则本次跳过（force=True 强制全量）。
"""
from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import AppConfig, get_config
from app.db import BACKEND_DIR, get_session, meta_set
from app.llm.client import LLMClient
from app.models import Contest, SourceHealth
from app.services.dedup import upsert_contest
from app.services.retention import retention_cleanup
from app.services.status import derive_is_new, derive_status_of
from app.utils.timeutil import iso, now_local, parse_iso

# 重试之间的等待秒数
_RETRY_BACKOFF_SECONDS = 1.5


async def _wait_for(coro: Any, timeout: float) -> Any:
    """asyncio.wait_for 的模块内间接层（便于测试打桩）。"""
    return await asyncio.wait_for(coro, timeout=timeout)


# playwright 源的并发上限：chromium 实例内存占用高（每个数百 MB），
# 与 HTTP 源的 concurrency 分开计数，避免一次刷新同时拉起多个无头浏览器。
_PLAYWRIGHT_CONCURRENCY = 2


@dataclass(slots=True)
class SourceSpec:
    """sources.yaml 中单个源的配置。"""

    id: str
    name: str
    method: str = "http"
    parser: str = ""
    enabled: bool = True
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SourceResult:
    """单源一次刷新的结果（日志/调试用）。"""

    source_id: str
    skipped_cache: bool = False
    ok: bool = False
    inserted: int = 0
    changed: int = 0
    error: str | None = None


def load_sources(path: Path | str | None = None) -> list[SourceSpec]:
    """读取 sources.yaml；文件不存在时打印中文告警并返回空列表。"""
    src = Path(path) if path else (BACKEND_DIR / "sources.yaml")
    if not src.is_file():
        print(f"[调度器] 未找到信息源配置 {src}，本次没有可抓取的源（等待 sources.yaml 就位）")
        return []
    try:
        data = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        print(f"[调度器] sources.yaml 解析失败：{exc}")
        return []
    specs: list[SourceSpec] = []
    for item in data.get("sources") or []:
        if not isinstance(item, dict) or not item.get("id") or not item.get("parser"):
            print(f"[调度器] 跳过非法源条目：{item!r}")
            continue
        specs.append(
            SourceSpec(
                id=str(item["id"]),
                name=str(item.get("name") or item["id"]),
                method=str(item.get("method") or "http"),
                parser=str(item["parser"]),
                enabled=bool(item.get("enabled", True)),
                params=dict(item.get("params") or {}),
            )
        )
    return specs


def instantiate_parser(parser_path: str, params: dict[str, Any]) -> Any:
    """按 "app.parsers.cspro.CsproSource" 形式的路径导入并实例化解析器。

    模块/类缺失时抛 RuntimeError（中文原因），由调度层计为源失败。
    """
    module_path, _, class_name = parser_path.rpartition(".")
    if not module_path or not class_name:
        raise RuntimeError(f"解析器路径非法：{parser_path}")
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise RuntimeError(f"解析器模块加载失败：{module_path}（{exc}）") from exc
    cls = getattr(module, class_name, None)
    if cls is None:
        raise RuntimeError(f"解析器类不存在：{parser_path}")
    return cls(params)


class Scheduler:
    """刷新调度器：并发抓取 + 去重入库 + 源健康 + LLM 加工 + 保留清理。"""

    def __init__(self, config: AppConfig | None = None, sources_path: Path | str | None = None) -> None:
        self.config = config or get_config()
        self.sources_path = sources_path
        self.running: bool = False
        self._llm: LLMClient | None = None

    # ---- 对外入口 ----

    async def refresh(self, force: bool = False) -> dict[str, Any]:
        """执行一轮刷新；running 标志防重入。返回摘要（中文日志友好）。"""
        if self.running:
            return {"started": False, "reason": "已有刷新任务在执行"}

        self.running = True
        started_at = iso(now_local())
        try:
            specs = [s for s in load_sources(self.sources_path) if s.enabled]
            semaphore = asyncio.Semaphore(max(1, self.config.fetch.concurrency))
            pw_semaphore = asyncio.Semaphore(_PLAYWRIGHT_CONCURRENCY)

            tasks = [
                self._fetch_one(spec, force, pw_semaphore if spec.method == "playwright" else semaphore)
                for spec in specs
            ]
            results = list(await asyncio.gather(*tasks))

            # 全部源结束后：LLM 加工新增/变更条目 + 保留清理
            pending_ids: list[int] = [cid for r in results for cid in r.get("enrich_ids", [])]
            enriched = await self._enrich_pending(pending_ids)
            cleanup_deleted = self._finalize()

            any_ok = any(r["ok"] for r in results)
            with get_session() as session:
                meta_set(session, "last_run", started_at)
                if any_ok:
                    meta_set(session, "last_ok", started_at)
                session.commit()

            summary = {
                "started": True,
                "started_at": started_at,
                "sources": len(specs),
                "ok": sum(1 for r in results if r["ok"]),
                "skipped_cache": sum(1 for r in results if r["skipped_cache"]),
                "failed": sum(1 for r in results if not r["ok"] and not r["skipped_cache"]),
                "enriched": enriched,
                "deleted_by_retention": cleanup_deleted,
            }
            print(f"[调度器] 刷新完成：{summary}")
            return summary
        finally:
            self.running = False

    # ---- 单源抓取 ----

    async def _fetch_one(
        self, spec: SourceSpec, force: bool, semaphore: asyncio.Semaphore
    ) -> dict[str, Any]:
        """并发单元：缓存判断 → 限流 → 超时+重试 → 入库 → 更新源健康。"""
        now = iso(now_local())
        result: dict[str, Any] = {"source_id": spec.id, "ok": False, "skipped_cache": False}

        with get_session() as session:
            self._sync_health_row(session, spec, now_run=now)
            session.commit()

        # 缓存判断：距 last_ok < cache_hours 且非强制 → 跳过
        if not force:
            with get_session() as session:
                health = session.get(SourceHealth, spec.id)
                last_ok = parse_iso(health.last_ok) if health else None
            if last_ok is not None and (now_local() - last_ok).total_seconds() < self.config.fetch.cache_hours * 3600:
                result["skipped_cache"] = True
                result["ok"] = True  # 缓存命中视为"无需抓取"，不算失败
                result["enrich_ids"] = []
                print(f"[调度器] 源 {spec.id} 距上次成功不足 {self.config.fetch.cache_hours}h，命中缓存跳过")
                return result

        timeout = (
            self.config.fetch.playwright_timeout_seconds
            if spec.method == "playwright"
            else self.config.fetch.timeout_seconds
        )
        attempts = max(1, self.config.fetch.retries + 1)
        last_error = "未知错误"

        async with semaphore:
            for attempt in range(1, attempts + 1):
                try:
                    parser = instantiate_parser(spec.parser, spec.params)
                    raw_items = await _wait_for(parser.fetch(), timeout)
                    inserted, changed, enrich_ids = self._ingest(spec, raw_items)
                    with get_session() as session:
                        health = self._sync_health_row(session, spec)
                        health.last_ok = iso(now_local())
                        health.last_error = None
                        session.commit()
                    result.update(ok=True, inserted=inserted, changed=changed, enrich_ids=enrich_ids)
                    print(f"[调度器] 源 {spec.id} 抓取成功：新增 {inserted} 条、更新 {changed} 条")
                    return result
                except Exception as exc:  # noqa: BLE001 —— 任何源失败都不能影响其他源
                    if isinstance(exc, TimeoutError):  # 3.11+：asyncio.TimeoutError 即内建 TimeoutError
                        last_error = f"抓取超时（>{timeout}s）"
                    else:
                        last_error = str(exc) or type(exc).__name__
                    print(f"[调度器] 源 {spec.id} 第 {attempt}/{attempts} 次尝试失败：{last_error}")
                    if attempt < attempts:
                        await asyncio.sleep(_RETRY_BACKOFF_SECONDS)

        with get_session() as session:
            health = self._sync_health_row(session, spec)
            health.last_error = last_error[:500]
            session.commit()
        result["error"] = last_error
        return result

    def _ingest(self, spec: SourceSpec, raw_items: list[dict[str, Any]]) -> tuple[int, int, list[int]]:
        """把单源的 ContestRaw 列表去重入库；返回 (新增数, 变更数, 待 LLM 加工的 id)。"""
        inserted = changed = 0
        enrich_ids: list[int] = []
        now = iso(now_local())
        with get_session() as session:
            for raw in raw_items or []:
                if not isinstance(raw, dict):
                    continue
                try:
                    contest, is_new, is_changed = upsert_contest(session, raw, spec.id, spec.name, now=now)
                except ValueError as exc:
                    print(f"[调度器] 源 {spec.id} 条目非法，已跳过：{exc}")
                    continue
                if is_new:
                    inserted += 1
                elif is_changed:
                    changed += 1
                if is_new or is_changed:
                    enrich_ids.append(contest.id)
            session.commit()
        return inserted, changed, enrich_ids

    # ---- 收尾：LLM 加工 + 保留清理 ----

    async def _enrich_pending(self, contest_ids: list[int]) -> int:
        """对新增/变更条目逐条 LLM 加工（失败自动规则降级，绝不抛出）。"""
        if not contest_ids:
            return 0
        if self._llm is None:
            self._llm = LLMClient(self.config.llm)
        enriched = 0
        try:
            with get_session() as session:
                for cid in contest_ids:
                    contest = session.get(Contest, cid)
                    if contest is None:
                        continue
                    patch = await self._llm.enrich(contest.to_dict())
                    if patch.get("summary"):
                        contest.summary = patch["summary"]
                    contest.summary_by = str(patch.get("summary_by") or "rule")
                    if patch.get("category"):
                        contest.category = patch["category"]
                    if patch.get("ai_policy"):
                        contest.ai_policy = patch["ai_policy"]
                    if patch.get("requirements") and not contest.requirements:
                        contest.requirements = patch["requirements"]
                    enriched += 1
                session.commit()
        except Exception as exc:  # noqa: BLE001 —— LLM 环节任何异常不影响主流程
            print(f"[LLM] 批量加工异常（已跳过剩余条目）：{exc}")
        finally:
            await self._llm.aclose()
        return enriched

    def _finalize(self) -> int:
        """刷新收尾：保留清理 + 派生字段快照刷新。返回删除条数。"""
        with get_session() as session:
            deleted = retention_cleanup(session)
            for contest in session.scalars(select(Contest)).all():
                contest.status = derive_status_of(contest)
                contest.is_new = derive_is_new(contest.first_seen)
            session.commit()
        return deleted

    # ---- 源健康 ----

    @staticmethod
    def _sync_health_row(session: Session, spec: SourceSpec, now_run: str | None = None) -> SourceHealth:
        """upsert 源健康行（保持 name/method/enabled 与 sources.yaml 一致）。"""
        health = session.get(SourceHealth, spec.id)
        if health is None:
            health = SourceHealth(id=spec.id, name=spec.name, method=spec.method, enabled=spec.enabled)
            if now_run:
                health.last_run = now_run
            session.add(health)
        else:
            health.name = spec.name
            health.method = spec.method
            health.enabled = spec.enabled
            if now_run:
                health.last_run = now_run
        return health

