"""抓取层：调度器（backend-core）+ 解析器契约 base.py（Lead 维护，勿改）。"""
from app.fetcher.scheduler import Scheduler, SourceSpec, load_sources

__all__ = ["Scheduler", "SourceSpec", "load_sources"]
