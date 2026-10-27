"""配置加载。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import yaml

# 项目根目录（config/ 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "config.yaml"


def _merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(path: str | Path | None = None) -> Dict[str, Any]:
    """加载 YAML 配置，支持用环境变量覆盖关键项（便于部署）。"""
    p = Path(path) if path else DEFAULT_CONFIG
    if not p.exists():
        raise FileNotFoundError(f"配置文件不存在: {p}")
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # 环境变量覆盖（可选）
    if os.getenv("CHESS_ENGINE_URL"):
        cfg.setdefault("engine", {})["base_url"] = os.getenv("CHESS_ENGINE_URL")
    if os.getenv("CHESS_LLM_URL"):
        cfg.setdefault("llm", {})["base_url"] = os.getenv("CHESS_LLM_URL")
    if os.getenv("CHESS_LLM_MODEL"):
        cfg.setdefault("llm", {})["model"] = os.getenv("CHESS_LLM_MODEL")
    return cfg
