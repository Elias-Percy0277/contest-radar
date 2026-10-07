"""用 httpx（带浏览器 UA）抓取各信息源真实页面，生成/刷新 tests/fixtures/ 下的测试夹具。

用法（在 backend/ 下）：
    ../../.venv-sources/bin/python tests/fixtures/refresh_fixtures.py

- HTML 通过 app/parsers/_util.fetch_text 抓取（httpx 带 UA；遇阿里云 WAF 挑战页自动 curl 重试，
  ccf.org.cn 会按 TLS 指纹拦 httpx，curl 可过），原样保存。
- codeforces.json 只保留前 100 条（去重真实数据、控制仓库体积），全部 BEFORE 场次都在其中。
- huawei 站是 SPA，另用 Playwright 渲染后保存（huawei_rendered.html），需已安装 chromium；
  未安装时跳过并在结尾打印提示（退出码仍为 0，主流程 fixture 已生成）。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/ 进 path

def _bootstrap_contract() -> None:
    """绕开 app/fetcher/__init__.py（其中 scheduler 依赖 backend-core 的 sqlalchemy 等重依赖），
    按文件路径直接加载契约 base.py，保证解析器测试独立于后端框架可运行（SPEC 第 5 节）。"""
    import importlib.util
    import sys
    import types

    if "app.fetcher.base" in sys.modules:
        return
    backend = Path(__file__).resolve().parents[2]  # backend/
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
from app.fetcher.base import SourceError  # noqa: E402
from app.parsers._util import fetch_text  # noqa: E402

FIXTURES = Path(__file__).resolve().parent
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

PAGES: dict[str, str] = {
    "cspro.html": (
        "https://www.cspro.org/cms/show.action"
        "?code=publish_8ac21fad9d27f22a019f5944f2eb00e1&siteid=100000"
    ),
    "nowcoder.html": "https://ac.nowcoder.com/acm/home",
    "ccsp.html": "https://www.ccf.org.cn/ccsp/",
    "ccf_cert.html": "https://www.ccf.org.cn/Activities/Certification/",
    "cacc.html": "https://cacc.ccf.org.cn/",
    "huawei_shell.html": "https://competition.huaweicloud.com/",
}
CF_API = "https://codeforces.com/api/contest.list"


def save_text(name: str, text: str) -> None:
    (FIXTURES / name).write_text(text, encoding="utf-8")
    print(f"[ok] {name}: {len(text):,} chars")


async def fetch_pages(client: httpx.AsyncClient) -> None:
    for name, url in PAGES.items():
        try:
            text = await fetch_text(url)
            print(f"[fetch] {url} -> {len(text):,} chars")
            save_text(name, text)
        except SourceError as exc:
            print(f"[FAIL] {name}: {exc}")


async def fetch_codeforces(client: httpx.AsyncClient) -> None:
    resp = await client.get(CF_API)
    resp.raise_for_status()
    data = resp.json()
    trimmed = {"status": data.get("status"), "result": data.get("result", [])[:100]}
    save_text("codeforces.json", json.dumps(trimmed, ensure_ascii=False, indent=1))
    before = sum(1 for c in trimmed["result"] if c.get("phase") == "BEFORE")
    print(f"[info] codeforces BEFORE in fixture: {before}")


async def fetch_huawei_rendered() -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[skip] playwright 未安装，跳过华为云渲染 fixture")
        return
    try:
        from app.parsers.huawei import HuaweiSource

        src = HuaweiSource()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page(user_agent=UA)
                captured = await src._render_and_capture(page, PAGES["huawei_shell.html"])
                html = await page.content()
            finally:
                await browser.close()
        save_text("huawei_rendered.html", html)
        # 捕获的 XHR 原始 JSON（list + hot）作为解析 fixture
        import json as _json

        payload = {"list": captured.get("list", []), "hot": captured.get("hot", [])}
        save_text("huawei_api.json", _json.dumps(payload, ensure_ascii=False, indent=1))
        print(f"[info] huawei_api.json: list={len(payload['list'])} hot={len(payload['hot'])}")
    except Exception as exc:
        print(f"[skip] 华为云渲染失败（chromium 未装或网络问题）：{exc.__class__.__name__}: {exc}")


async def main() -> int:
    failed = False
    async with httpx.AsyncClient(
        headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
        follow_redirects=True,
        timeout=30.0,
    ) as client:
        await fetch_pages(client)
        try:
            await fetch_codeforces(client)
        except (httpx.HTTPError, ValueError) as exc:
            failed = True
            print(f"[FAIL] codeforces.json: {exc}")
    await fetch_huawei_rendered()
    print("done" + ("（部分失败，见 [FAIL]）" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))