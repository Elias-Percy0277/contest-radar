"""第五轮扩源测试：AtCoder（Upcoming 表格）+ 数学建模国赛（通知列表）。"""
from __future__ import annotations

from app.parsers import atcoder, mcm


def test_atcoder_upcoming() -> None:
    from conftest import assert_contest_raw, load_fixture

    items = atcoder.AtCoderSource().parse(load_fixture("atcoder.html"))
    assert len(items) >= 3, "AtCoder 至少解析出 3 场即将开始的比赛"
    for it in items:
        assert_contest_raw(it)
        assert it["category"] == "算法竞赛"
        assert it["contest_start"], "应有开赛日期（JST→上海换算）"
        assert "atcoder.jp/contests/" in it["url"]
    assert any("AtCoder" in t for i in items for t in i["tags"])


def test_mcm_notices() -> None:
    from conftest import assert_contest_raw, load_fixture

    items = mcm.McmSource().parse(load_fixture("mcm.html"))
    assert len(items) >= 3, "数模官网至少解析出 3 条相关通知"
    for it in items:
        assert_contest_raw(it)
        assert it["category"] == "综合学科"
        assert "/html_cn/node/" in it["url"]
        # 已办活动新闻必须被过滤
        assert not any(k in it["title"] for k in mcm.EXCLUDE)
