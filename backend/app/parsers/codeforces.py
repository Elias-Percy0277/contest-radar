"""Codeforces 官方 API 解析器 —— method=api。

接口：GET https://codeforces.com/api/contest.list → {"status":"OK","result":[
  {"id":2273,"name":"Codeforces Round (Div. 1)","type":"CF","phase":"BEFORE",
   "frozen":false,"durationSeconds":9000,"startTimeSeconds":1791743700,...}]}
只取 phase=BEFORE（未开始）；startTimeSeconds/durationSeconds 为 Unix 秒（UTC），
按 Asia/Shanghai 换算成 YYYY-MM-DD 写入 contest_start / contest_end。
type=CF 时从名称抓 "Div. N" 进 tags。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.parsers._util import SH_TZ, fetch_text
from app.fetcher.base import BaseSource, SourceError

DEFAULT_URL = "https://codeforces.com/api/contest.list"
RE_DIV = re.compile(r"Div\.?\s*([1-4])", re.I)


class CodeforcesSource(BaseSource):
    source_id = "codeforces"
    name = "Codeforces"
    method = "api"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        try:
            payload = await fetch_text(url)
            import json

            data = json.loads(payload)
        except ValueError as exc:
            raise SourceError(f"Codeforces API 返回的不是合法 JSON：{exc}") from exc
        if data.get("status") != "OK":
            comment = data.get("comment", "无原因")
            raise SourceError(f"Codeforces API 返回失败：{comment}")
        items = self.parse(data.get("result") or [])
        if not items:
            raise SourceError("Codeforces 未解析到任何未开始（phase=BEFORE）的比赛，接口可能异常")
        return items

    @staticmethod
    def _ts_to_date(ts: int) -> str:
        return datetime.fromtimestamp(ts, tz=SH_TZ).date().isoformat()

    def parse(self, result: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for c in result:
            if c.get("phase") != "BEFORE":
                continue
            cid = c.get("id")
            name = str(c.get("name") or "").strip()
            start_ts = c.get("startTimeSeconds")
            duration = c.get("durationSeconds") or 0
            if cid is None or not name or not start_ts:
                continue
            tags = ["Codeforces"]
            if c.get("type") == "CF":
                tags.append("Rated")
                m = RE_DIV.search(name)
                if m:
                    tags.append(f"Div. {m.group(1)}")
            elif c.get("type") == "ICPC":
                tags.append("ACM/ICPC 赛制")
            out.append(
                {
                    "title": name,
                    "url": f"https://codeforces.com/contest/{cid}",
                    "category": "算法竞赛",
                    "reg_start": None,
                    "reg_deadline": None,  # CF 赛前随时可报名，无截止概念
                    "contest_start": self._ts_to_date(int(start_ts)),
                    "contest_end": self._ts_to_date(int(start_ts) + int(duration)),
                    "organizer": "Codeforces",
                    "tags": tags,
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": None,
                    "requirements": None,
                    "summary": None,
                }
            )
        return out


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.codeforces
    import asyncio

    async def _main() -> None:
        for it in await CodeforcesSource().fetch():
            print(it["title"], "|", it["contest_start"], "~", it["contest_end"], "|", it["url"])

    asyncio.run(_main())
