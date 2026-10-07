"""解析器契约 —— 由 Team Lead 维护，如需修改请先在群里协商。详见 contest-radar/SPEC.md 第 5 节。

所有信息源解析器（app/parsers/*）必须继承 BaseSource：
- 类属性 source_id / name / method 与 sources.yaml 中该源条目一致
- __init__(params) 接收该源在 sources.yaml 里的 params 段
- fetch() 负责抓取 + 解析，返回 ContestRaw dict 列表（字段见 SPEC 第 3 节）
  * 网络失败 / 页面改版解析失败：抛 SourceError（由调度器记录源健康，不影响其他源）
  * 单个条目某字段拿不到：用 None / [] 兜底，不要抛错
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

# 信息源抓取方式：http=纯HTTP请求 / api=公开JSON接口 / playwright=无头浏览器
Method = Literal["http", "api", "playwright"]


class SourceError(RuntimeError):
    """源抓取或解析失败。message 会展示在前端"源健康面板"，请写清楚原因。"""


class BaseSource(ABC):
    source_id: str = ""   # 如 "ccf_csp"
    name: str = ""        # 如 "CCF CSP认证"
    method: Method = "http"

    def __init__(self, params: dict[str, Any] | None = None) -> None:
        self.params: dict[str, Any] = params or {}

    @abstractmethod
    async def fetch(self) -> list[dict[str, Any]]:
        """抓取并解析，返回 ContestRaw dict 列表。"""
        raise NotImplementedError
