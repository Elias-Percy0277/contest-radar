"""华为云大赛（Playwright）解析器测试。

- 纯函数部分（日期规范化 / 分类规则 / XHR JSON 挖掘）离线可测。
- 渲染抓取依赖 chromium 内核：设 CR_HUAWEI_LIVE=1 才跑真实渲染测试（CI/无内核环境自动跳过）。
- 内核缺失时 fetch 必须抛带安装提示的 SourceError（契约要求）。
"""
from __future__ import annotations

import os

import pytest

from app.fetcher.base import SourceError
from app.parsers import huawei


def test_date_part() -> None:
    """ISO/斜杠/点分隔时间 → YYYY-MM-DD。"""
    assert huawei._date_part("2026-09-01T18:00:00+0800") == "2026-09-01"
    assert huawei._date_part("2026/04/15") == "2026-04-15"
    assert huawei._date_part("2025.12.1 09:00") == "2025-12-01"
    assert huawei._date_part(None) is None
    assert huawei._date_part("") is None
    assert huawei._date_part("没有日期") is None
    assert huawei._date_part("2026-13-99") is None  # 非法月日不崩、返回 None


def test_category_rules() -> None:
    assert huawei._category_for("2026 华为云 AI 大赛") == "AI与数据科学"
    assert huawei._category_for("盘古大模型创新应用赛") == "AI与数据科学"
    assert huawei._category_for("CodeCraft 算法精英挑战赛") == "算法竞赛"
    assert huawei._category_for("云原生应用创新大赛") == "应用与开发"
    assert huawei._category_for("网络安全攻防赛") == "网络安全"


def test_import_error_gives_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    """未安装 playwright 库 → 明确的安装提示 SourceError。"""
    import builtins

    real_import = builtins.__import__

    def no_playwright(name: str, *args: object, **kwargs: object):
        if name.startswith("playwright"):
            raise ImportError("No module named 'playwright'")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", no_playwright)
    with pytest.raises(SourceError) as ei:
        import asyncio

        asyncio.run(huawei.HuaweiSource().fetch())
    assert "playwright install chromium" in str(ei.value)


def test_build_items_from_captured_api_fixture() -> None:
    """fixture（真实捕获的华为云 XHR JSON）→ build_items ≥1 条合法 ContestRaw。"""
    import json

    from conftest import FIXTURES_DIR, assert_contest_raw

    path = FIXTURES_DIR / "huawei_api.json"
    if not path.exists():
        pytest.skip("huawei_api.json 未生成（生成 fixture 的机器未装 chromium）")
    captured = json.loads(path.read_text(encoding="utf-8"))
    items = huawei.HuaweiSource.build_items(captured)
    assert len(items) >= 1, "从捕获的接口 JSON 至少构建出 1 条赛事"
    for it in items:
        assert_contest_raw(it)
        assert it["organizer"] == "华为云"
    # list 接口条目应带详情链接与分类
    assert all(i["url"].startswith("http") for i in items)


@pytest.mark.skipif(not os.environ.get("CR_HUAWEI_LIVE"), reason="需要 chromium 内核，设 CR_HUAWEI_LIVE=1 启用")
def test_live_render() -> None:
    """真实渲染（已实测）：渲染后提取赛事卡片 ≥1 条合法 ContestRaw。"""
    import asyncio

    from conftest import assert_contest_raw

    items = asyncio.run(huawei.HuaweiSource().fetch())
    assert len(items) >= 1
    for it in items:
        assert_contest_raw(it)