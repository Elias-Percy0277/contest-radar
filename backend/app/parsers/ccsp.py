"""CCF CCSP 竞赛频道（www.ccf.org.cn/ccsp/）解析器 —— method=http（候选源，enabled=false）。

实测（2026-10）：服务端渲染，公告列表条目形如：
  <a href="/ccsp/Bulletin/2026-09-09/931089.shtml">2026 CCF CCSP竞赛将于10月21~22日举办，9月9日开启报名</a>
日期可从 URL 段 /Bulletin/YYYY-MM-DD/ 取；标题里尽力提取举办/报名日期。
简单实现：只抓 Bulletin 公告，转 ContestRaw。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import base_join, clean_text, fetch_text, make_soup, to_iso

DEFAULT_URL = "https://www.ccf.org.cn/ccsp/"
RE_URL_DATE = re.compile(r"/Bulletin/(20\d{2})-(\d{1,2})-(\d{1,2})/")
# 标题里"10月21~22日举办"这类日期（年份常省略，用公告发布年份补）
RE_MONTH_DAY = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})")
# 只保留与赛事强相关的公告，过滤"金奖说/经验分享"等软文
KEEP_KEYWORDS = ("CCSP", "竞赛", "报名", "决赛", "通知", "手册", "举办")
EXCLUDE_KEYWORDS = ("金奖说", "冠军说", "经验分享", "代言人", "备考资料", "揭秘")


class CcspSource(BaseSource):
    source_id = "ccf_ccsp"
    name = "CCF CCSP竞赛"
    method = "http"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        html = await fetch_text(url)
        items = self.parse(html, base_url=url)
        if not items:
            raise SourceError("CCSP 频道未解析到竞赛相关公告，页面可能改版")
        return items

    def parse(self, html: str, *, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
        soup = make_soup(html)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = RE_URL_DATE.search(href)
            if not m:
                continue
            title = clean_text(a.get_text())
            if not title or any(k in title for k in EXCLUDE_KEYWORDS):
                continue
            if not any(k in title for k in KEEP_KEYWORDS):
                continue
            url = base_join(base_url, href)
            if url in seen:
                continue
            seen.add(url)
            publish_year = int(m.group(1))
            publish = date(publish_year, int(m.group(2)), int(m.group(3)))

            # 尽力提取比赛日期：标题中"X月X日"且带"举办/比赛"字样时，视为 contest_start
            contest_start: date | None = None
            if any(k in title for k in ("举办", "比赛", "开赛")):
                md = RE_MONTH_DAY.search(title)
                if md:
                    try:
                        contest_start = date(publish_year, int(md.group(1)), int(md.group(2)))
                    except ValueError:
                        contest_start = None

            out.append(
                {
                    "title": title,
                    "url": url,
                    "category": "算法竞赛",
                    "reg_start": None,
                    "reg_deadline": None,
                    "contest_start": to_iso(contest_start),
                    "contest_end": None,
                    "organizer": "CCF",
                    "tags": ["CCSP", "国家级"],
                    "ai_policy": "unknown",
                    "prize": None,
                    "eligibility": None,
                    "requirements": None,
                    "summary": f"发布于 {publish.isoformat()}",
                }
            )
        return out


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.ccsp
    import asyncio

    async def _main() -> None:
        for it in await CcspSource().fetch():
            print(it["title"], "|", it["contest_start"], "|", it["url"])

    asyncio.run(_main())
