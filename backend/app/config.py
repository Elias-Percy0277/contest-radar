"""配置加载：优先 backend/config.yaml，缺失时回退 backend/config.example.yaml 并打印中文告警。

配置结构见 SPEC 第 6 节；config.yaml 只需覆盖想改的字段，其余沿用示例默认值。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# backend/ 目录（app/config.py 的上一级）
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent


@dataclass(slots=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8300


@dataclass(slots=True)
class FetchConfig:
    cache_hours: int = 6
    concurrency: int = 3
    timeout_seconds: int = 30
    playwright_timeout_seconds: int = 60
    retries: int = 2


@dataclass(slots=True)
class LLMConfig:
    enabled: bool = True
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"


@dataclass(slots=True)
class RetentionConfig:
    joined_grace_days: int = 7
    unmarked_ended_days: int = 30
    stale_unknown_days: int = 30


@dataclass(slots=True)
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    fetch: FetchConfig = field(default_factory=FetchConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    retention: RetentionConfig = field(default_factory=RetentionConfig)
    # 实际生效来源：example / user
    loaded_from: str = "example"


# 顶层配置段 → dataclass 字段的映射
_SECTION_FIELDS: dict[str, dict[str, Any]] = {
    "server": {
        "host": str,
        "port": int,
    },
    "fetch": {
        "cache_hours": int,
        "concurrency": int,
        "timeout_seconds": int,
        "playwright_timeout_seconds": int,
        "retries": int,
    },
    "llm": {
        "enabled": bool,
        "api_key": str,
        "base_url": str,
        "model": str,
    },
    "retention": {
        "joined_grace_days": int,
        "unmarked_ended_days": int,
        "stale_unknown_days": int,
    },
}


def _coerce(value: Any, typ: type) -> Any:
    """把 YAML 值温和地转成目标类型（bool 需特殊处理，int(True)==1）。"""
    if typ is bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if typ is int and not isinstance(value, bool):
        return int(value)
    if typ is str:
        return str(value)
    return value


def _apply(cfg: AppConfig, data: dict[str, Any]) -> None:
    """把 YAML 字典按段应用到 AppConfig；忽略未知键。"""
    for section, keys in _SECTION_FIELDS.items():
        part = data.get(section)
        if not isinstance(part, dict):
            continue
        target = getattr(cfg, section)
        for key, typ in keys.items():
            if key in part and part[key] is not None:
                try:
                    setattr(target, key, _coerce(part[key], typ))
                except (TypeError, ValueError):
                    print(f"[配置告警] {section}.{key} 的值 {part[key]!r} 无法解析为 {typ.__name__}，已沿用默认值")


def load_config(backend_dir: Path | str | None = None) -> AppConfig:
    """加载配置：config.yaml 优先（字段级覆盖示例默认值），否则用 config.example.yaml。"""
    base = Path(backend_dir) if backend_dir else BACKEND_DIR
    cfg = AppConfig()
    user_yaml = base / "config.yaml"
    example_yaml = base / "config.example.yaml"

    if example_yaml.is_file():
        try:
            _apply(cfg, yaml.safe_load(example_yaml.read_text(encoding="utf-8")) or {})
        except yaml.YAMLError as exc:
            print(f"[配置告警] config.example.yaml 解析失败（{exc}），使用内置默认值")

    if user_yaml.is_file():
        cfg.loaded_from = "user"
        try:
            _apply(cfg, yaml.safe_load(user_yaml.read_text(encoding="utf-8")) or {})
        except yaml.YAMLError as exc:
            print(f"[配置告警] config.yaml 解析失败（{exc}），忽略用户配置文件")
    else:
        print("[配置告警] 未找到 backend/config.yaml，已回退使用 config.example.yaml 默认配置；"
              "如需自定义请复制一份并改名为 config.yaml")

    return cfg


# 模块级单例（测试可用 reset_config() 后重新加载）
_config: AppConfig | None = None


def get_config(reload: bool = False) -> AppConfig:
    """获取全局配置单例。"""
    global _config
    if _config is None or reload:
        _config = load_config()
    return _config


def reset_config() -> None:
    """重置配置单例（主要用于测试）。"""
    global _config
    _config = None
