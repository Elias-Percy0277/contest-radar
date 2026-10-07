"""normalize_url 规范化测试（SPEC 第 3 节）。"""
from __future__ import annotations

from app.services.normalize import normalize_url


def test_scheme_host_lowercase() -> None:
    assert normalize_url("HTTPS://WWW.Example.COM/Contest/Show") == "https://www.example.com/Contest/Show"


def test_strip_fragment() -> None:
    assert normalize_url("https://a.com/x?k=1#detail") == "https://a.com/x?k=1"


def test_strip_trailing_slash() -> None:
    assert normalize_url("https://a.com/path/") == "https://a.com/path"
    # 多个尾斜杠也去掉
    assert normalize_url("https://a.com/path///") == "https://a.com/path"


def test_drop_tracking_params() -> None:
    url = "https://a.com/p?b=2&utm_source=x&utm_medium=y&from=home&spm=1001.1&a=1"
    assert normalize_url(url) == "https://a.com/p?a=1&b=2"


def test_query_params_sorted() -> None:
    assert normalize_url("https://a.com/p?z=1&a=2&m=3") == "https://a.com/p?a=2&m=3&z=1"


def test_same_page_dedup_case() -> None:
    """仅跟踪参数/大小写/尾斜杠不同的 URL 应规范化为同一 canonical。"""
    a = normalize_url("https://Race.Example.org/csp/")
    b = normalize_url("https://race.example.org/csp?utm_campaign=seed")
    assert a == b == "https://race.example.org/csp"


def test_empty_url() -> None:
    assert normalize_url("") == ""
    assert normalize_url("   ") == ""


def test_no_query() -> None:
    assert normalize_url("https://a.com") == "https://a.com"
