"""种子数据：python -m app.seed（在 backend/ 目录下执行）。

写入 12 条假数据，覆盖：全部 6 个分类、4 种状态（registering/ongoing/ended/unknown）、
joined / ignored / none、有/无报名截止、无任何日期的条目。
日期相对"今天"生成，保证任何时间执行状态都正确；canonical_url 固定，可重复执行（幂等）。
"""
from __future__ import annotations

import sys
from datetime import timedelta

from sqlalchemy import select

from app.db import get_session, init_db
from app.models import Contest
from app.services.dedup import upsert_contest
from app.utils.timeutil import iso, now_local, today_local


def _d(offset_days: int) -> str:
    """相对今天的日期字符串。"""
    return (today_local() + timedelta(days=offset_days)).isoformat()


def _w(weeks_ago: int) -> str:
    """weeks_ago 周前的时间戳（用于把部分 first_seen 拉回过去，丰富周新增图）。"""
    return iso(now_local() - timedelta(weeks=weeks_ago))


SEEDS: list[tuple[dict, str]] = [
    # (ContestRaw, my_status)
    (
        {
            "title": "第十八届蓝桥杯全国软件和信息技术专业人才大赛",
            "url": "https://www.lanqiaobei.example.com/contest/18?utm_source=seed",
            "category": "算法竞赛",
            "reg_start": _d(-10), "reg_deadline": _d(14), "contest_start": _d(30), "contest_end": _d(32),
            "organizer": "工业和信息化部人才交流中心",
            "tags": ["个人赛", "国家级", "在校生"],
            "ai_policy": "forbidden",
            "prize": "省级及以上奖项证书，总决赛奖金最高 5 万元",
            "eligibility": "在校大学生及研究生",
            "requirements": "个人赛，按语言分组评奖",
            "summary": "蓝桥杯是国内规模最大的高校算法赛事之一，分省赛与国赛两级，支持 C/C++/Java/Python 多语言组别。",
        },
        "joined",
    ),
    (
        {
            "title": "Codeforces Round 999 (Div. 1)",
            "url": "https://codeforces.com/contests/1899",
            "category": "算法竞赛",
            "reg_start": _d(-3), "reg_deadline": _d(0), "contest_start": _d(-1), "contest_end": _d(1),
            "organizer": "Codeforces",
            "tags": ["个人赛", "国际级", "线上"],
            "ai_policy": "forbidden",
            "summary": "Codeforces 全球算法线上赛，Div.1 面向 1900 分以上选手，赛时 2.5 小时。",
        },
        "none",
    ),
    (
        {
            "title": "牛客周赛第 100 期",
            "url": "https://ac.nowcoder.com/contest/10086",
            "category": "算法竞赛",
            "contest_start": _d(-30), "contest_end": _d(-10),
            "organizer": "牛客网",
            "tags": ["个人赛", "线上"],
            "ai_policy": "allowed",
            "summary": "牛客每周举办的入门向算法竞赛，赛后又题解直播。",
        },
        "none",
    ),
    (
        {
            "title": "CCF CSP认证（第 35 次）",
            "url": "https://www.cspro.org/example/csp-35",
            "category": "认证考试",
            "reg_start": _d(-5), "reg_deadline": _d(20), "contest_start": _d(28), "contest_end": _d(28),
            "organizer": "中国计算机学会",
            "tags": ["认证", "国家级"],
            "ai_policy": "forbidden",
            "prize": "认证成绩证书（200/100/50 档）",
            "eligibility": "不限",
            "requirements": "个人认证考试，现场闭卷",
            "summary": "CCF 计算机软件能力认证，四次上机编程题，成绩被众多高校与企业认可。",
        },
        "joined",
    ),
    (
        {
            "title": "CCF GESP 编程能力等级认证（3 月场）",
            "url": "https://gesp.ccf.org.cn/example/2026-03",
            "category": "认证考试",
            "reg_start": _d(-60), "reg_deadline": _d(-40), "contest_start": _d(-35), "contest_end": _d(-35),
            "organizer": "中国计算机学会",
            "tags": ["认证", "青少年"],
            "ai_policy": "unknown",
            "summary": "面向青少年编程能力分级的官方认证考试。",
        },
        "none",
    ),
    (
        {
            "title": "华为云 AI 大赛·大模型应用创新赛",
            "url": "https://competition.huaweicloud.com/example/llm2026",
            "category": "AI与数据科学",
            "reg_start": _d(-7), "reg_deadline": _d(7), "contest_start": _d(21), "contest_end": _d(60),
            "organizer": "华为云",
            "tags": ["团队赛", "企业级", "线上"],
            "ai_policy": "allowed",
            "prize": "奖金池 50 万元 + 华为云资源",
            "eligibility": "高校学生与企业开发者均可",
            "requirements": "1-3 人组队，使用华为云 ModelArts 平台",
            "summary": "围绕盘古大模型与昇腾算力的应用创新赛事，分初赛复赛决赛三轮。",
        },
        "ignored",
    ),
    (
        {
            "title": "Kaggle 社区赛：房价预测入门",
            "url": "https://www.kaggle.com/example/house-prices",
            "category": "AI与数据科学",
            "organizer": "Kaggle",
            "tags": ["个人赛", "国际级", "线上", "入门"],
            "ai_policy": "allowed",
            "summary": "经典机器学习入门赛事，长期开放提交，无固定赛程。",
        },
        "none",
    ),
    (
        {
            "title": "全国大学生软件创新大赛（第十二届）",
            "url": "https://software-contest.example.edu.cn/12th",
            "category": "应用与开发",
            "reg_start": _d(-14), "reg_deadline": _d(3), "contest_start": _d(45), "contest_end": _d(60),
            "organizer": "教育部高等学校软件工程专业教学指导委员会",
            "tags": ["团队赛", "国家级", "在校生"],
            "ai_policy": "unknown",
            "prize": "一等奖奖金 2 万元",
            "eligibility": "全日制在校生",
            "requirements": "3-5 人组队，需指导教师",
            "summary": "面向全国高校的软件作品赛，分区域赛与全国总决赛。",
        },
        "none",
    ),
    (
        {
            "title": "「强网杯」全国网络安全挑战赛",
            "url": "https://www.qiangwangbei.org/example/2026",
            "category": "网络安全",
            "reg_start": _d(-9), "reg_deadline": _d(2), "contest_start": _d(25), "contest_end": _d(27),
            "organizer": "国家网络与信息安全信息通报中心",
            "tags": ["团队赛", "国家级", "线上+线下"],
            "ai_policy": "allowed",
            "prize": "线下决赛奖金 + 实习绿色通道",
            "eligibility": "不限",
            "requirements": "1-4 人组队（线上初赛）",
            "summary": "国内最高水平的 CTF 赛事之一，线上初赛选拔线下决赛。",
        },
        "joined",
    ),
    (
        {
            "title": "全国大学生数学建模竞赛（2026）",
            "url": "https://www.mcm.edu.cn/example/2026",
            "category": "综合学科",
            "reg_start": _d(-20), "reg_deadline": _d(-3), "contest_start": _d(-2), "contest_end": _d(1),
            "organizer": "中国工业与应用数学学会",
            "tags": ["团队赛", "国家级", "在校生"],
            "ai_policy": "unknown",
            "prize": "国家级一二等奖证书",
            "eligibility": "在校本科生与专科生",
            "requirements": "3 人一队，72 小时连续作答",
            "summary": "全国高校规模最大的基础学科竞赛之一，每年 9 月举行。",
        },
        "none",
    ),
    (
        {
            "title": "「挑战杯」全国大学生课外学术科技作品竞赛",
            "url": "https://www.tiaozhanbei.net/example/2025",
            "category": "综合学科",
            "reg_start": _d(-90), "reg_deadline": _d(-70), "contest_start": _d(-50), "contest_end": _d(-40),
            "organizer": "共青团中央 / 中国科协",
            "tags": ["团队赛", "国家级", "在校生"],
            "ai_policy": "unknown",
            "summary": "大学生课外学术科技的最高荣誉赛事，两年一届。",
        },
        "none",
    ),
    (
        {
            "title": "开源之夏 2026·社区自由贡献月",
            "url": "https://summer-ospp.example.org/2026",
            "category": "应用与开发",
            "organizer": "开源软件供应链点亮计划",
            "tags": ["个人赛", "线上", "开源"],
            "ai_policy": "allowed",
            "summary": "面向全球学生的开源项目贡献活动，中选者可获奖金与社区导师指导。",
        },
        "none",
    ),
]

# 把部分条目的 first_seen 拉回过去，制造周新增分布（其余保持 now → is_new=true）
_FIRST_SEEN_OFFSET_WEEKS = {1: 5, 4: 4, 5: 3, 10: 2, 11: 1}


def run() -> int:
    """写入种子数据（幂等），返回条目数。"""
    init_db()
    now = iso(now_local())
    count = 0
    with get_session() as session:
        for raw, my_status in SEEDS:
            contest, _, _ = upsert_contest(session, raw, source_id="seed", source_name="种子数据", now=now)
            if my_status != contest.my_status:
                contest.my_status = my_status  # 种子数据允许重置标记（真实抓取绝不覆盖）
            count += 1
        session.commit()

        # 制造 first_seen 分布
        for idx, weeks in _FIRST_SEEN_OFFSET_WEEKS.items():
            row = session.scalars(
                select(Contest).where(Contest.canonical_url == normalize_seed_url(idx))
            ).first()
            if row is not None:
                row.first_seen = _w(weeks)
                row.last_updated = _w(weeks)
        session.commit()
    return count


def normalize_seed_url(idx: int) -> str:
    """种子条目的 canonical_url（与 normalize_url 保持一致地计算）。"""
    from app.services.normalize import normalize_url
    return normalize_url(SEEDS[idx][0]["url"])


def main() -> None:
    n = run()
    print(f"[seed] 已写入/更新 {n} 条种子数据（覆盖各分类/状态/joined/ignored/无日期）")
    print("[seed] 提示：真实抓取不会改动这些条目的 my_status；如需重来可删除 backend/data/contests.db")


if __name__ == "__main__":
    sys.exit(main())
