"""第二轮扩源测试：DataFountain（SSR 列表）+ 赛氪（渲染后聚合，含过滤）。"""
from __future__ import annotations

from app.parsers import datafountain, saikr


def test_datafountain_list() -> None:
    from conftest import assert_contest_raw, load_fixture

    items = datafountain.DataFountainSource().parse(load_fixture("datafountain.html"))
    assert len(items) >= 3, "DataFountain 至少解析出 3 条"
    for it in items:
        assert_contest_raw(it)
        assert it["category"] == "AI与数据科学"
        assert "/competitions/" in it["url"]
        assert "DataFountain" in it["tags"]
    assert any(i["contest_start"] and i["contest_end"] for i in items), "应解析出赛程区间"
    assert any(i["prize"] for i in items), "应解析出奖金"


def test_saikr_filters_ads_and_news() -> None:
    from conftest import assert_contest_raw, load_fixture

    items = saikr.SaikrSource().parse(load_fixture("saikr.html"))
    assert len(items) >= 1, "赛氪至少解析出 1 条 CS 相关赛事"
    for it in items:
        assert_contest_raw(it)
        assert "/active" in it["url"]
        assert "/course" not in it["url"] and "wewinfuture" not in it["url"] and "/news/" not in it["url"]
        keep = saikr.DEFAULT_KEEP
        assert any(k in it["title"] for k in keep), it["title"]
