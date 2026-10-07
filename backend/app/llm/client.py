"""DeepSeek LLM 客户端（openai SDK，base_url=https://api.deepseek.com，model=deepseek-chat）。

职责（仅对新增/变更条目）：
- 生成 ≤120 字中文摘要
- 校正 category（六枚举内）
- 尽力抽取 ai_policy（allowed/forbidden/unknown）与 requirements

降级规则：api_key 为空、llm.enabled=false 或调用/解析失败 → rules.rule_enrich。
**任何异常都在本层吞掉并走规则降级，绝不影响抓取主流程。**
"""
from __future__ import annotations

import json
from typing import Any

from app.config import LLMConfig, get_config
from app.llm.rules import CATEGORIES, rule_enrich, truncate_summary

# 单条 LLM 请求超时（秒）：加工失败不应拖垮刷新流程
_LLM_TIMEOUT_SECONDS = 30.0

_SYSTEM_PROMPT = (
    "你是竞赛信息编辑助手。给定一条竞赛/认证考试的原始信息（JSON），"
    "请完成以下工作并只输出一个 JSON 对象，不要输出任何解释或 markdown 代码块：\n"
    '1. "summary"：不超过 120 字的中文摘要，概括赛项性质、主办方、时间与奖励亮点；\n'
    '2. "category"：从 ["算法竞赛","AI与数据科学","应用与开发","网络安全","综合学科","认证考试"] 中选一个；\n'
    '3. "ai_policy"：判断是否允许使用 AI，只能是 "allowed"/"forbidden"/"unknown"，拿不准一律 "unknown"；\n'
    '4. "requirements"：一句话概括参赛要求（学历/队伍人数/报名条件等），没有则输出 null。'
)


def _build_user_prompt(contest: dict[str, Any]) -> str:
    payload = {
        "title": contest.get("title"),
        "organizer": contest.get("organizer"),
        "category": contest.get("category"),
        "tags": contest.get("tags"),
        "summary": contest.get("summary"),
        "prize": contest.get("prize"),
        "eligibility": contest.get("eligibility"),
        "requirements": contest.get("requirements"),
        "reg_start": contest.get("reg_start"),
        "reg_deadline": contest.get("reg_deadline"),
        "contest_start": contest.get("contest_start"),
        "contest_end": contest.get("contest_end"),
    }
    return json.dumps(payload, ensure_ascii=False)


def _parse_llm_json(text: str) -> dict[str, Any] | None:
    """解析模型输出：容忍 markdown 代码块包裹。"""
    text = text.strip()
    fence = "```"
    if text.startswith(fence):
        # 去掉开头的代码块标记（可能带语言名）与结尾标记
        inner = text[len(fence):]
        if inner.startswith("json") or inner.startswith("JSON"):
            inner = inner[4:]
        if inner.rstrip().endswith(fence):
            inner = inner.rstrip()[: -len(fence)]
        text = inner.strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class DeepDiveError(RuntimeError):
    """深挖失败（用户主动触发的操作，不做静默降级，直接上抛中文原因）。"""


_DEEP_SYSTEM_PROMPT = (
    "你是竞赛信息抽取助手。根据给出的竞赛基本信息与详情页正文，抽取并只输出一个 JSON 对象："
    '{"ai_policy":"allowed|forbidden|unknown","policy_evidence":"判定依据的原文片段或null",'
    '"requirements":"参赛要求（学历/队伍/报名条件）或null","prize":"奖金奖品描述或null",'
    '"eligibility":"参赛资格或null"}。'
    "正文中没有的信息一律填 null，禁止编造；只输出 JSON，不要任何解释。"
)


class LLMClient:
    """DeepSeek 客户端（惰性创建，可复用）。任何失败自动降级为规则模式。"""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or get_config().llm
        self._async_client: Any | None = None

    @property
    def available(self) -> bool:
        """LLM 是否可用（启用且配置了 Key）。"""
        return bool(self.config.enabled and self.config.api_key.strip())

    def _get_async_client(self) -> Any:
        if self._async_client is None:
            from openai import AsyncOpenAI  # 延迟导入，未配置 Key 时不需要该依赖路径
            self._async_client = AsyncOpenAI(
                api_key=self.config.api_key.strip(),
                base_url=self.config.base_url or "https://api.deepseek.com",
                timeout=_LLM_TIMEOUT_SECONDS,
                max_retries=0,
            )
        return self._async_client

    async def enrich(self, contest: dict[str, Any]) -> dict[str, Any]:
        """加工单条竞赛信息：成功返回 LLM 字段，失败/未配置返回规则降级字段。永不抛异常。"""
        if not self.available:
            return rule_enrich(contest)
        try:
            client = self._get_async_client()
            completion = await client.chat.completions.create(
                model=self.config.model or "deepseek-chat",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": _build_user_prompt(contest)},
                ],
                temperature=0.3,
                max_tokens=512,
            )
            content = completion.choices[0].message.content or ""
            data = _parse_llm_json(content)
            if data is None:
                print("[LLM] 模型输出无法解析为 JSON，已按规则降级")
                return rule_enrich(contest)

            summary = truncate_summary(str(data.get("summary") or ""), limit=120) or None
            category = data.get("category")
            if category not in CATEGORIES:
                category = None  # 非法分类 → 不覆盖原值
            ai_policy = data.get("ai_policy")
            if ai_policy not in ("allowed", "forbidden", "unknown"):
                ai_policy = None
            requirements = data.get("requirements")
            if isinstance(requirements, str) and requirements.strip():
                requirements = requirements.strip()
            else:
                requirements = None

            result: dict[str, Any] = {
                "summary": summary or truncate_summary(contest.get("summary") or contest.get("title") or ""),
                "summary_by": "llm",
            }
            if category:
                result["category"] = category
            if ai_policy and ai_policy != "unknown":
                result["ai_policy"] = ai_policy
            if requirements and not contest.get("requirements"):
                result["requirements"] = requirements  # 仅在原值为空时补抽取结果
            return result
        except Exception as exc:  # noqa: BLE001 —— LLM 任何异常不得影响主流程
            print(f"[LLM] 调用失败，已按规则降级：{type(exc).__name__}: {exc}")
            return rule_enrich(contest)

    async def deep_dive(self, contest: dict[str, Any], detail_text: str) -> dict[str, Any]:
        """手动深挖：从详情页正文抽取 AI政策/参赛要求/奖金。

        与 enrich 不同：这是用户主动触发的操作，失败上抛 DeepDiveError（路由转中文
        错误提示），不做静默降级——点了按钮就该看到真实结果。
        """
        if not self.available:
            raise DeepDiveError("未配置 LLM API Key，深挖功能不可用（backend/config.yaml）")
        user_prompt = (
            f"竞赛：{contest.get('title')}\n"
            f"主办方：{contest.get('organizer') or '未知'}\n\n"
            f"详情页正文（截断）：\n{detail_text[:8000]}"
        )
        try:
            client = self._get_async_client()
            completion = await client.chat.completions.create(
                model=self.config.model or "deepseek-chat",
                messages=[
                    {"role": "system", "content": _DEEP_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=512,
            )
            data = _parse_llm_json(completion.choices[0].message.content or "")
            if data is None:
                raise DeepDiveError("模型输出无法解析为 JSON，请稍后重试")
            out: dict[str, Any] = {}
            ai = data.get("ai_policy")
            if ai in ("allowed", "forbidden", "unknown"):
                out["ai_policy"] = ai
            for key in ("requirements", "prize", "eligibility"):
                v = data.get(key)
                if isinstance(v, str) and v.strip():
                    out[key] = v.strip()[:500]
            ev = data.get("policy_evidence")
            if isinstance(ev, str) and ev.strip():
                out["policy_evidence"] = ev.strip()[:200]
            return out
        except DeepDiveError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DeepDiveError(f"LLM 调用失败：{type(exc).__name__}: {exc}") from exc

    async def aclose(self) -> None:
        """释放底层客户端。"""
        if self._async_client is not None:
            try:
                await self._async_client.close()
            except Exception:  # noqa: BLE001
                pass
            self._async_client = None
