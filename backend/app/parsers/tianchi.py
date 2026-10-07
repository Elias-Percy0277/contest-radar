"""阿里天池大赛（tianchi.aliyun.com/competition/）解析器 —— method=http。

实测（2026-10）：列表页为客户端渲染，但数据接口公开可直连（无需签名/登录）：
  GET https://tianchi.aliyun.com/v3/proxy/competition/api/race/page?visualTab=&raceName=&pageNum=1&isActive=
返回 data.list[]：raceId/name/raceStartTime/raceEndTime/signupStartTime/signupEndTime/
bonus/currency/tagsList/teamCount/introduction…（total=600，首页 10 条为当前进行/最新的赛事）。
详情页 URL 模式：/competition/entrance/{raceId}/introduction。
时间字段 "2026-09-11 00:00:00" → 取日期部分。过滤长期沉淀的历史赛（结束超 45 天）。
"""
from __future__ import annotations

import re
from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import clean_text, fetch_json, today_sh

DEFAULT_URL = "https://tianchi.aliyun.com/v3/proxy/competition/api/race/page"


def _d(v: Any) -> str | None:
    """"2026-09-11 00:00:00" → "2026-09-11"。"""
    if not v or not isinstance(v, str):
        return None
    m = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", v)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


class TianchiSource(BaseSource):
    source_id = "tianchi"
    name = "阿里天池"
    method = "http"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        pages = int(self.params.get("pages") or 2)  # 抓前 2 页（约 20 条，够当前赛事）
        raw: list[dict[str, Any]] = []
        for page in range(1, pages + 1):
            payload = await fetch_json(url, params={"visualTab": "", "raceName": "", "pageNum": page, "isActive": ""})
            data = (payload or {}).get("data") or {}
            batch = data.get("list") or []
            raw.extend(batch)
            if not batch or page >= int(data.get("pages") or 0):
                break
        items = self.parse(raw)
        if not items:
            raise SourceError("天池列表接口未解析到赛事，接口可能变更或被风控")
        return items

    def parse(self, raw_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        from datetime import timedelta

        floor_date = (today_sh() - timedelta(days=45)).isoformat()
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for x in raw_list:
            title = clean_text(x.get("name"))
            race_id = x.get("raceId")
            if not title or race_id is None:
                continue
            url = f"https://tianchi.aliyun.com/competition/entrance/{race_id}/introduction"
            if url in seen:
                continue
            seen.add(url)
            contest_end = _d(x.get("raceEndTime"))
            reg_deadline = _d(x.get("signupEndTime"))
            # 过滤早已结束的历史赛（保留进行中/长期赛/可报名）
            if contest_end and contest_end < floor_date and (not reg_deadline or reg_deadline < floor_date):
                continue
            tags = ["天池", "企业级"]
            for t in x.get("tagsList") or []:
                t = clean_text(t.get("name") if isinstance(t, dict) else t)
                if t:
                    tags.append(t)
            bonus = x.get("bonus")
            prize = f"{clean_text(x.get('currency')) or '￥'}{int(bonus)}" if bonus else None
            brief = clean_text(x.get("introduction"))[:120]
            out.append(
                {
                    "title": title,
                    "url": url,
                    "category": "AI与数据科学",
                    "reg_start": _d(x.get("signupStartTime")),
                    "reg_deadline": reg_deadline,
                    "contest_start": _d(x.get("raceStartTime")),
                    "contest_end": contest_end,
                    "organizer": "阿里云天池",
                    "tags": tags,
                    "ai_policy": "unknown",
                    "prize": prize,
                    "eligibility": None,
                    "requirements": None,
                    "summary": brief or None,
                }
            )
        return out


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.tianchi
    import asyncio

    async def _main() -> None:
        for it in await TianchiSource().fetch():
            print(it["title"][:36], "| reg:", it["reg_deadline"], "| cst:", it["contest_start"], "~", it["contest_end"], "|", it["url"][:70])

    asyncio.run(_main())
