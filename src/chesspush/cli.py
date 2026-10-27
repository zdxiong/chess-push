"""命令行入口。

用法：
    python -m chesspush.cli --once          # 单次推演当前局面
    python -m chesspush.cli --listen        # 实时监听（默认）
    python -m chesspush.cli --config path   # 指定配置
    python -m chesspush.cli --interval 0.5  # 轮询间隔
"""
from __future__ import annotations

import argparse
import sys

from .config import load_config
from .listener import build_listener
from .pipeline.narration import narrate
from .services.engine_client import EngineClient
from .services.llm_client import LLMClient
from .pushers.console import ConsolePusher
from .pushers.filelog import FilePusher


def _parse_args(argv=None):
    p = argparse.ArgumentParser(prog="chess-push",
                                description="中国象棋实时走子推演解说")
    p.add_argument("--config", default=None, help="配置文件路径")
    p.add_argument("--once", action="store_true", help="只推演一次当前局面")
    p.add_argument("--listen", action="store_true", help="实时监听盘面变化（默认）")
    p.add_argument("--interval", type=float, default=None,
                   help="监听轮询间隔（秒）")
    p.add_argument("--no-llm", action="store_true",
                   help="禁用 LLM，强制使用规则解说")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    cfg = load_config(args.config)

    if args.interval is not None:
        cfg.setdefault("listener", {})["poll_interval"] = args.interval
    if args.no_llm:
        cfg.setdefault("llm", {})["on_unavailable"] = "fallback"

    listener = build_listener(cfg)
    llm = listener.llm
    if args.no_llm:
        llm = None

    if args.once:
        _run_once(listener.engine, llm, cfg)
        return 0

    listener.llm = llm
    listener.run()
    return 0


def _run_once(engine: EngineClient, llm, cfg):
    pushers = []
    pc = cfg.get("pushers", {})
    if pc.get("console", True):
        pushers.append(ConsolePusher())
    if pc.get("file", True):
        pushers.append(FilePusher(
            json_path=pc.get("file_json", "logs/narration.jsonl"),
            text_path=pc.get("file_text", "logs/narration.txt"),
        ))
    try:
        snap = engine.snapshot()
    except Exception as e:
        print(f"无法连接引擎 {engine.base_url}：{e}")
        return
    result = narrate(snap, llm)
    for p in pushers:
        p.push(result)
    if result.source == "rules" and llm is not None:
        print("[提示] LLM 未连接，已使用规则兜底解说。")
    if not snap.best_move:
        print("[提示] 引擎暂未给出推荐走法，请确认已开启分析模式。")


if __name__ == "__main__":
    sys.exit(main())
