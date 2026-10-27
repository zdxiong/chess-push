"""实时监听循环：轮询 8787，盘面 FEN 变化时触发走子推演并推送。

- 启动时可先推一次当前局面（emit_on_startup）。
- 之后每轮对比 FEN，发生变化才推演。
- 引擎分析尚未就绪（best_move 为空）时不重复刷屏，只首次提示。
"""
from __future__ import annotations

import time
from typing import List, Optional

from .pipeline.narration import NarrationResult, narrate
from .pushers.console import ConsolePusher
from .pushers.filelog import FilePusher
from .services.engine_client import EngineClient
from .services.llm_client import LLMClient


class Listener:
    def __init__(
        self,
        engine: EngineClient,
        llm: Optional[LLMClient],
        pushers: List,
        poll_interval: float = 1.0,
        emit_on_startup: bool = True,
        trigger_on_fen_change: bool = True,
        trigger_on_best_change: bool = True,
    ):
        self.engine = engine
        self.llm = llm
        self.pushers = pushers
        self.poll_interval = poll_interval
        self.emit_on_startup = emit_on_startup
        self.trigger_on_fen_change = trigger_on_fen_change
        self.trigger_on_best_change = trigger_on_best_change
        self._last_fen: Optional[str] = None
        self._last_best: Optional[str] = None
        self._started = False
        self._no_move_notified = False

    def _deliver(self, result: NarrationResult) -> None:
        for p in self.pushers:
            p.push(result)

    def _narrate_safe(self, snap):
        """推演；当引擎 fen 与 bestMove 短暂不同步（如起点无子）时跳过该帧，
        避免崩溃，等引擎分析同步后再正常输出。返回 (ok, result)。"""
        try:
            return True, narrate(snap, self.llm)
        except Exception as e:
            print(f"[监听] 推演跳过：{e}（引擎分析可能未与盘面同步）")
            return False, None

    def run(self, max_iters: Optional[int] = None) -> None:
        """实时监听主循环。max_iters 仅在测试/调试时用于限制轮询次数。"""
        print(f"开始实时监听 {self.engine.base_url}（轮询 {self.poll_interval}s，"
              f"Ctrl+C 退出）")
        it = 0
        while max_iters is None or it < max_iters:
            it += 1
            try:
                snap = self.engine.snapshot()
            except Exception as e:
                print(f"[监听] 拉取失败：{e}")
                time.sleep(self.poll_interval * 2)
                continue

            fen_changed = snap.fen != self._last_fen
            best_changed = snap.best_move != self._last_best

            if not self._started:
                self._started = True
                if self.emit_on_startup and snap.fen:
                    self._last_fen = snap.fen
                    self._last_best = snap.best_move
                    self._no_move_notified = bool(snap.best_move)
                    if snap.is_my_turn:
                        ok, result = self._narrate_safe(snap)
                        if ok:
                            self._deliver(result)
                continue

            changed = (
                (self.trigger_on_fen_change and fen_changed)
                or (self.trigger_on_best_change and best_changed)
            )
            if changed and snap.fen:
                # 记录本次快照，避免反复刷屏
                self._last_fen = snap.fen
                self._last_best = snap.best_move
                self._no_move_notified = bool(snap.best_move)
                # 只在轮到我方走棋时才推演并输出
                if snap.is_my_turn:
                    ok, result = self._narrate_safe(snap)
                    if ok:
                        self._deliver(result)
            elif snap.fen and not snap.best_move and not self._no_move_notified:
                # 引擎无分析，仅提示一次
                print("[监听] 引擎暂未给出推荐走法，请确认已开启分析模式。")
                self._no_move_notified = True

            time.sleep(self.poll_interval)


def build_listener(cfg: dict) -> Listener:
    """按配置组装各层并返回 Listener。"""
    engine_cfg = cfg.get("engine", {})
    llm_cfg = cfg.get("llm", {})
    listener_cfg = cfg.get("listener", {})
    pusher_cfg = cfg.get("pushers", {})

    engine = EngineClient(
        base_url=engine_cfg.get("base_url", "http://localhost:8787"),
        timeout=engine_cfg.get("timeout", 10.0),
    )
    llm = LLMClient(
        base_url=llm_cfg.get("base_url", "http://localhost:8000/v1"),
        model=llm_cfg.get("model", ""),
        temperature=llm_cfg.get("temperature", 0.7),
        max_tokens=llm_cfg.get("max_tokens", 256),
        timeout=llm_cfg.get("timeout", 60.0),
        on_unavailable=llm_cfg.get("on_unavailable", "fallback"),
    )

    pushers: List = []
    if pusher_cfg.get("console", True):
        pushers.append(ConsolePusher())
    if pusher_cfg.get("file", True):
        pushers.append(FilePusher(
            json_path=pusher_cfg.get("file_json", "logs/narration.jsonl"),
            text_path=pusher_cfg.get("file_text", "logs/narration.txt"),
        ))

    return Listener(
        engine=engine,
        llm=llm,
        pushers=pushers,
        poll_interval=float(listener_cfg.get("poll_interval", 1.0)),
        emit_on_startup=bool(listener_cfg.get("emit_on_startup", True)),
        trigger_on_fen_change=bool(listener_cfg.get("trigger_on_fen_change", True)),
        trigger_on_best_change=bool(listener_cfg.get("trigger_on_best_change", True)),
    )
