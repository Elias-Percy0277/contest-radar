"""去重合并测试：canonical_url 唯一键、可变字段更新、my_status/first_seen 绝不覆盖。"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db import get_session
from app.models import Contest
from app.services.dedup import upsert_contest
from app.utils.timeutil import iso, now_local


def _raw(**overrides: object) -> dict:
    base = {
        "title": "第 1 届示例算法大赛",
        "url": "https://race.example.com/csp1?utm_source=mp",
        "category": "算法竞赛",
        "reg_start": "2026-09-01",
        "reg_deadline": "2026-11-01",
        "contest_start": "2026-11-20",
        "contest_end": "2026-11-21",
        "organizer": "示例学会",
        "tags": ["个人赛", "国家级"],
        "ai_policy": "forbidden",
        "prize": "奖金 10 万",
        "eligibility": "在校生",
        "requirements": "个人赛",
        "summary": "示例大赛是测试用的比赛。",
    }
    base.update(overrides)
    return base


def _all_rows() -> list[Contest]:
    with get_session() as session:
        return list(session.scalars(select(Contest)).all())


def test_insert_new_sets_first_seen() -> None:
    with get_session() as session:
        contest, is_new, is_changed = upsert_contest(session, _raw(), "ccf_csp", "CCF CSP认证")
        session.commit()
    assert is_new is True
    assert contest.first_seen
    assert contest.my_status == "none"
    assert contest.source_id == "ccf_csp"


def test_reupsert_same_canonical_updates_not_inserts() -> None:
    with get_session() as session:
        upsert_contest(session, _raw(), "ccf_csp", "CCF CSP认证")
        session.commit()
    with get_session() as session:
        _, is_new, _ = upsert_contest(session, _raw(), "ccf_csp", "CCF CSP认证")
        session.commit()
    assert is_new is False
    assert len(_all_rows()) == 1


def test_tracking_param_variant_dedups_to_same_row() -> None:
    with get_session() as session:
        upsert_contest(session, _raw(), "ccf_csp", "CCF CSP认证")
        session.commit()
    variant = _raw(url="https://race.example.com/csp1?from=timeline&spm=99")  # 同页不同跟踪参数
    with get_session() as session:
        _, is_new, _ = upsert_contest(session, variant, "ccf_csp", "CCF CSP认证")
        session.commit()
    assert is_new is False
    assert len(_all_rows()) == 1


def test_my_status_and_first_seen_never_touched() -> None:
    with get_session() as session:
        contest, _, _ = upsert_contest(session, _raw(), "ccf_csp", "CCF CSP认证")
        contest.my_status = "joined"
        first_seen_before = contest.first_seen
        session.commit()

    changed_raw = _raw(title="第 1 届示例算法大赛（已延期）", reg_deadline="2026-11-15")
    with get_session() as session:
        contest2, is_new, is_changed = upsert_contest(session, changed_raw, "ccf_csp", "CCF CSP认证")
        session.commit()

    assert is_new is False
    assert is_changed is True
    assert contest2.my_status == "joined"  # 绝不动 my_status
    assert contest2.first_seen == first_seen_before  # 绝不动 first_seen
    assert contest2.title.endswith("（已延期）")
    assert contest2.reg_deadline == "2026-11-15"


def test_none_fields_do_not_wipe_existing_values() -> None:
    with get_session() as session:
        upsert_contest(session, _raw(), "ccf_csp", "CCF CSP认证")
        session.commit()
    stripped = _raw(organizer=None, prize=None, tags=[])  # 源这次没抓到
    with get_session() as session:
        contest, _, _ = upsert_contest(session, stripped, "ccf_csp", "CCF CSP认证")
        session.commit()
    assert contest.organizer == "示例学会"
    assert contest.prize == "奖金 10 万"
    assert contest.tags == ["个人赛", "国家级"]


def test_changed_flag_false_when_identical() -> None:
    with get_session() as session:
        upsert_contest(session, _raw(), "ccf_csp", "CCF CSP认证")
        session.commit()
    with get_session() as session:
        _, _, is_changed = upsert_contest(session, _raw(), "ccf_csp", "CCF CSP认证")
        session.commit()
    assert is_changed is False


def test_new_summary_marks_changed_and_resets_summary_by() -> None:
    with get_session() as session:
        contest, _, _ = upsert_contest(session, _raw(), "ccf_csp", "CCF CSP认证")
        contest.summary_by = "llm"  # 模拟已加工
        session.commit()
    with get_session() as session:
        contest2, _, is_changed = upsert_contest(
            session, _raw(summary="主办方更新了全新的赛事介绍，规模翻倍。"), "ccf_csp", "CCF CSP认证"
        )
        session.commit()
    assert is_changed is True
    assert contest2.summary_by is None  # 待重新加工


def test_missing_title_or_url_raises() -> None:
    with get_session() as session:
        with pytest.raises(ValueError):
            upsert_contest(session, {"url": "https://a.com"}, "s", "s")
        with pytest.raises(ValueError):
            upsert_contest(session, {"title": "无链接"}, "s", "s")


def test_different_canonical_inserts_second_row() -> None:
    # 标题不同（不同赛事）→ 独立两行
    with get_session() as session:
        upsert_contest(session, _raw(), "ccf_csp", "CCF CSP认证")
        session.commit()
    with get_session() as session:
        _, is_new, _ = upsert_contest(
            session,
            _raw(url="https://race.example.com/csp2", title="另一个毫不相干的比赛"),
            "nowcoder",
            "牛客",
        )
        session.commit()
    assert is_new is True
    assert len(_all_rows()) == 2


def test_cross_source_merge_same_title() -> None:
    # 跨源合并：不同源 + 标题归一化后一致 → 并入已有条目，打"多源:"标签
    with get_session() as session:
        upsert_contest(session, _raw(), "ccf_csp", "CCF CSP认证")
        session.commit()
    with get_session() as session:
        row, is_new, changed = upsert_contest(
            session, _raw(url="https://race.example.com/csp2"), "nowcoder", "牛客"
        )
        session.commit()
    assert is_new is False and changed is False
    assert len(_all_rows()) == 1
    assert any(str(t).startswith("多源:牛客") for t in (row.tags or []))


def test_normalize_title_strips_noise() -> None:
    from app.services.dedup import normalize_title

    assert normalize_title("第18届 蓝桥杯大赛（2026）") == normalize_title("第十八届蓝桥杯大赛")
    assert normalize_title("2026年高教社杯全国大学生数学建模竞赛") != normalize_title("2026年全国大学生电工数学建模竞赛")
