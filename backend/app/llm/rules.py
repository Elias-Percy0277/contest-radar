"""规则降级：无 API Key / LLM 调用失败时的关键词分类与摘要截取（SPEC 第 1 节）。

- 分类：按关键词表匹配标题+摘要+主办方，命中即归类；未命中默认"综合学科"
- 摘要：原文（summary）前 120 字；无原文时用标题
- summary_by = "rule"，ai_policy / requirements 保持原值（不臆造）
"""
from __future__ import annotations

from typing import Any

# 合法分类（SPEC 第 3 节）
CATEGORIES = ("算法竞赛", "AI与数据科学", "应用与开发", "网络安全", "综合学科", "认证考试")

# 关键词表：顺序即优先级（越靠前越特异）
_KEYWORD_TABLE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("认证考试", ("认证", "csp认证", "ccf", "软考", "资格考试", "等级考试", "gesp")),
    ("网络安全", ("安全", "ctf", "攻防", "漏洞", "密码技术", "hack")),
    ("AI与数据科学", ("人工智能", "大模型", "机器学习", "深度学习", "数据挖掘",
                  "大数据", "数据科学", "kaggle", "aigc", "llm", "智能创新")),
    ("算法竞赛", ("算法", "程序设计", "icpc", "acm", "蓝桥", "codeforces", "leetcode",
              "牛客", "周赛", "noi", "csp-j", "csp-s", "数据结构")),
    ("应用与开发", ("开发", "应用", "软件", "小程序", "全栈", "云计算", "鸿蒙", "嵌入式",
                "devops", "开源", "创新创业", "互联网+", "软件创新")),
    ("综合学科", ("数学", "物理", "化学", "建模", "综合", "学科", "挑战杯", "设计大赛",
              "英语", "翻译")),
)


def classify_by_keywords(*texts: str | None) -> str:
    """关键词分类：把若干文本拼起来按优先级匹配关键词表。"""
    blob = " ".join(t for t in texts if t).lower()
    if not blob:
        return "综合学科"
    for category, keywords in _KEYWORD_TABLE:
        for kw in keywords:
            if kw.lower() in blob:
                return category
    return "综合学科"


def truncate_summary(text: str | None, limit: int = 120) -> str:
    """截取前 limit 字（按字符计，符合中文习惯）。"""
    if not text:
        return ""
    text = text.strip().replace("\n", " ")
    return text[:limit]


def rule_enrich(contest: dict[str, Any]) -> dict[str, Any]:
    """规则降级加工：返回需要写回的字段。永不抛异常。"""
    raw_summary = contest.get("summary") or ""
    title = contest.get("title") or ""
    category = contest.get("category")
    if category not in CATEGORIES:
        category = classify_by_keywords(title, raw_summary, contest.get("organizer"))

    summary = truncate_summary(raw_summary) or truncate_summary(title) or title
    return {
        "summary": summary or None,
        "summary_by": "rule",
        "category": category,
    }
