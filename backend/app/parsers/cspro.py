"""CCF CSP 认证官网（cspro.org）通知公告解析器 —— method=http。

实测（2026-10）：www.cspro.org 首页是 frameset 壳，真实内容在
cms/show.action?code=publish_... 服务端渲染页；"通知公告"栏目条目形如：
  <li><a href="/cms/show.action?code=jumpnewstemplate&siteid=...&channelid=0000000103&newsid=..." title="第43次...通知">...</a> <time>2026-09-16</time></li>
本解析器抓 channelid=0000000103（通知公告）的条目转 ContestRaw。
"""
from __future__ import annotations

import re
from typing import Any

from app.fetcher.base import BaseSource, SourceError
from app.parsers._util import (
    base_join,
    clean_text,
    fetch_text,
    find_dates,
    make_soup,
    to_iso,
)

# 通知公告栏目 id（页面改版可通过 sources.yaml params.channel_id 覆盖）
DEFAULT_CHANNEL_ID = "0000000103"
DEFAULT_URL = (
    "https://www.cspro.org/cms/show.action"
    "?code=publish_8ac21fad9d27f22a019f5944f2eb00e1&siteid=100000"
)


class CsproSource(BaseSource):
    source_id = "ccf_csp"
    name = "CCF CSP认证"
    method = "http"

    async def fetch(self) -> list[dict[str, Any]]:
        url = self.params.get("url") or DEFAULT_URL
        html = await fetch_text(url)
        items = self.parse(html, base_url=url)
        if not items:
            raise SourceError("CSP 认证通知公告解析到 0 条，页面可能改版，请检查 cspro.org")
        return items

    def parse(self, html: str, *, base_url: str = DEFAULT_URL) -> list[dict[str, Any]]:
        soup = make_soup(html)
        channel = str(self.params.get("channel_id") or DEFAULT_CHANNEL_ID)

        out: list[dict[str, Any]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "newsid=" not in href or f"channelid={channel}" not in href:
                continue
            title = clean_text(a.get("title") or a.get_text())
            if not title:
                continue
            li = a.find_parent("li") or a
            time_tag = li.find("time")
            publish = clean_text(time_tag.get_text()) if time_tag else ""
            publish_date = find_dates(publish or title)
            raw = {
                "title": title,
                "url": base_join(base_url, href),
                "category": "认证考试",
                "reg_start": None,
                "reg_deadline": None,
                "contest_start": None,
                "contest_end": None,
                "organizer": "CCF",
                "tags": ["CSP认证"],
                "ai_policy": "unknown",
                "prize": None,
                "eligibility": None,
                "requirements": None,
                "summary": None,
            }
            # 认证批次（"第43次"）
            m = re.search(r"第\s*(\d+)\s*次", title)
            if m:
                raw["tags"] = [f"第{m.group(1)}次", "CSP认证"]
            # 尽力提取时间：报名通知里通常带认证日期；发布日期仅作兜底参考不写死字段
            dates = find_dates(title)
            if dates:
                if "报名" in title and "开始" not in title:
                    raw["contest_start"] = to_iso(dates[0])
                elif "认证" in title and len(dates) == 1:
                    raw["contest_start"] = to_iso(dates[0])
            # 部分通知正文链接列表里能同时看到发布日期，仅当标题无日期且是报名通知时兜底
            if raw["contest_start"] is None and "报名" in title and publish_date:
                raw["reg_start"] = to_iso(publish_date[0])
            out.append(raw)
        # 同一 newsid 去重（页面有时同一通知出现两次）
        seen: set[str] = set()
        deduped = [x for x in out if not (x["url"] in seen or seen.add(x["url"]))]
        return deduped


if __name__ == "__main__":  # 独立冒烟：python -m app.parsers.cspro
    import asyncio

    async def _main() -> None:
        for it in await CsproSource().fetch():
            print(it["title"], "|", it["contest_start"], "|", it["url"][:80])

    asyncio.run(_main())
