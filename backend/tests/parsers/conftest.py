"""解析器测试公共配置：把 backend/ 加进 sys.path，提供 ContestRaw 合法性断言。

fixture 由 tests/fixtures/refresh_fixtures.py 用 httpx（带 UA）抓取真实页面生成；
本目录测试全部离线运行（网络调用通过 monkeypatch 替换为读 fixture），保证确定性。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

def _bootstrap_contract() -> None:
    """绕开 app/fetcher/__init__.py（其中 scheduler 依赖 backend-core 的 sqlalchemy 等重依赖），
    按文件路径直接加载契约 base.py，保证解析器测试独立于后端框架可运行（SPEC 第 5 节）。"""
    import importlib.util
    import sys
    import types

    if "app.fetcher.base" in sys.modules:
        return
    backend = Path(__file__).resolve().parents[2]
    pkg = types.ModuleType("app.fetcher")
    pkg.__path__ = [str(backend / "app" / "fetcher")]
    sys.modules["app.fetcher"] = pkg
    spec = importlib.util.spec_from_file_location(
        "app.fetcher.base", backend / "app" / "fetcher" / "base.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["app.fetcher.base"] = module
    spec.loader.exec_module(module)


_bootstrap_contract()

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch: pytest.MonkeyPatch) -> "object":
    """覆盖 tests/conftest.py 的同名 autouse fixture。

    解析器测试完全不碰数据库；父级版本会 import app.db（sqlalchemy 2.0 +
    Python 3.10+ 语法），在 3.9 或未装后端依赖的环境会炸。这里换成纯环境变量桩，
    使 tests/parsers 子树可独立运行（SPEC：解析器是可独立测试模块）。
    """
    monkeypatch.setenv("CONTEST_RADAR_DB", ":memory:")
    monkeypatch.setenv("DISABLE_AUTO_OPEN", "1")
    monkeypatch.setenv("CONTEST_RADAR_DISABLE_STARTUP_REFRESH", "1")
    yield None

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"

CATEGORIES = {"算法竞赛", "AI与数据科学", "应用与开发", "网络安全", "综合学科", "认证考试"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def assert_contest_raw(item: Any) -> None:
    """断言一条 ContestRaw 合法（SPEC 第 3 节）：必填有值、日期格式或 null、不因空值崩溃。"""
    assert isinstance(item, dict), f"ContestRaw 应为 dict，得到 {type(item)}"
    for key in ("title", "url", "category"):
        v = item.get(key)
        assert isinstance(v, str) and v.strip(), f"字段 {key} 必填且非空：{item!r:.200}"
    assert item["category"] in CATEGORIES, f"category 非法：{item['category']}"
    assert item["url"].startswith("http"), f"url 必须是绝对地址：{item['url']}"
    for key in ("reg_start", "reg_deadline", "contest_start", "contest_end"):
        v = item.get(key)
        assert v is None or DATE_RE.match(v), f"{key} 应为 YYYY-MM-DD 或 null，得到 {v!r}"
    assert isinstance(item.get("tags", []), list), "tags 应为 list"
    assert item.get("ai_policy", "unknown") in {"allowed", "forbidden", "unknown"}, "ai_policy 非法"
    for key in ("prize", "eligibility", "requirements", "summary", "organizer"):
        assert item.get(key) is None or isinstance(item.get(key), str), f"{key} 应为 str 或 null"


def load_fixture(name: str) -> str:
    path = FIXTURES_DIR / name
    assert path.exists(), f"fixture 缺失：{path}（先运行 refresh_fixtures.py）"
    return path.read_text(encoding="utf-8")