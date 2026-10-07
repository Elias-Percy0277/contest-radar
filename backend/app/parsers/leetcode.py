"""力扣 LeetCode 周赛（leetcode.cn/contest/）解析器 —— method=http。

实测（2026-10）：竞赛列表页为 Next.js 客户端渲染（SSR HTML 无竞赛数据），
数据来自官方 GraphQL：POST https://leetcode.cn/graphql/ operationName=contestV2UpcomingContests
（httpx 直连可复放，无需登录/签名）。返回 titleSlug/title/startTime(Unix秒)/duration(秒)。
只取 upcoming（未开始）；该接口不含虚拟赛（虚拟赛在个人"虚拟竞赛"页，天然被过滤）。
周赛/双周赛按标题区分进 tags；时间按 Asia/Shanghai 换算 YYYY-MM-DD。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import SH_TZ, fetch_json

DEFAULT_URL = "https://leetcode.cn/graphql/"
QUERY = """
    query contestV2UpcomingContests {
  contestV2UpcomingContests {
    titleSlug
    title
    titleCn
    startTime
    duration
    cardImg
    cardImgApp
  }
}
    """


class LeetcodeSource(BaseSource):
    source_id = "leetcode"
    name = "LeetCode周赛"
    method = "http"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        payload = await fetch_json(
            url,
            json_body={"query": QUERY, "variables": {}, "operationName": "contestV2UpcomingContests"},
        )
        contests = ((payload or {}).get("data") or {}).get("contestV2UpcomingContests") or []
        items = self.parse(contests)
        if not items:
            raise SourceError("LeetCode 未解析到即将开始的竞赛，GraphQL 接口可能变更")
        return items

    @staticmethod
    def _ts_to_date(ts: int) -> str:
        return datetime.fromtimestamp(ts, tz=SH_TZ).date().isoformat()

    def parse(self, contests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for c in contests:
            title = str(c.get("titleCn") or c.get("title") or "").strip()
            slug = str(c.get("titleSlug") or "").strip()
            start_ts = c.get("startTime")
            duration = c.get("duration") or 0
            if not title or not slug or not start_ts:
                continue
            tags = ["周赛", "LeetCode"]
            if "双周赛" in title:
                tags[0] = "双周赛"
            out.append(
                {
                    "title": f"LeetCode {title}",
                    "url": f"https://leetcode.cn/contest/{slug}/",
                    "category": "算法竞赛",
                    "reg_start": None,
                    "reg_deadline": None,  # 开赛前随时可报名，无截止概念
                    "contest_start": self._ts_to_date(int(start_ts)),
                    "contest_end": self._ts_to_date(int(start_ts) + int(duration)),
                    "organizer": "LeetCode",
                    "tags": tags,
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": None,
                    "requirements": None,
                    "summary": None,
                }
            )
        return out


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.leetcode
    import asyncio

    async def _main() -> None:
        for it in await LeetcodeSource().fetch():
            print(it["title"], "|", it["contest_start"], "~", it["contest_end"], "|", it["url"])

    asyncio.run(_main())
