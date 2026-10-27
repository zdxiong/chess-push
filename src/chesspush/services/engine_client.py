"""TCHESS 引擎数据服务客户端（默认 http://localhost:8787）。

提供 /api/state（FEN + 分析合并快照）、/api/fen、/api/analysis 的读取，
并抽取「行棋方 + 最佳着法 + 主变」等下游所需的字段。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


@dataclass
class EngineSnapshot:
    """从 /api/state 抽取的核心数据。"""

    fen: str
    side_to_move: str              # w=红走, b=黑走
    side_cn: str                   # 红方 / 黑方
    red_to_move: bool
    engine_loaded: bool
    engine_name: Optional[str]
    best_move: Optional[str]       # 坐标走法，如 d7d3
    best_move_cn: Optional[str]    # 中文谱
    score: Optional[int]           # 主变评分
    depth: Optional[int]
    mate: Optional[int]            # 将死剩余步数，None=未将死
    pv_moves: list                 # 主变坐标序列
    pv_cn: list                    # 主变中文序列
    is_reverse: bool               # 盘面视角反转：False=我执红，True=我执黑
    my_side: str                   # 我方阵营：w=红方 / b=黑方
    my_side_cn: str                # 我方中文：红方 / 黑方
    is_my_turn: bool               # 是否轮到本解说视角的「我方」走棋
    raw: Dict[str, Any]


class EngineClient:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, endpoint: str) -> dict:
        url = f"{self.base_url}{endpoint}"
        r = requests.get(url, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def get_fen(self) -> dict:
        return self._get("/api/fen")

    def get_analysis(self) -> dict:
        return self._get("/api/analysis")

    def get_state(self) -> dict:
        return self._get("/api/state")

    def snapshot(self) -> EngineSnapshot:
        """拉取并抽取当前快照。"""
        data = self.get_state()
        fen = data.get("fen", "")
        side = data.get("sideToMove", "black")
        side_wb = "b" if side == "black" else "w"
        side_cn = "黑方" if side == "black" else "红方"
        red_to_move = bool(data.get("redToMove", False))

        analysis = data.get("analysis") or {}
        lines = analysis.get("lines") or []
        best_move = best_cn = score = depth = mate = None
        pv_moves, pv_cn = [], []
        if lines:
            # 主变优先取第 1 条；否则取深度最大的一条
            first = lines[0]
            best_move = first.get("bestMove")
            score = first.get("score")
            depth = first.get("depth")
            mate = first.get("mate")
            pv_moves = first.get("moves", [])
            pv_cn = (first.get("moveCn") or "").split()
            # 单步中文谱 = 主变第 1 步
            best_cn = pv_cn[0] if pv_cn else None

        # 我方身份由 isReverse 决定：False=我执红，True=我执黑
        is_reverse = bool(data.get("isReverse", False))
        my_side = "b" if is_reverse else "w"
        my_side_cn = "黑方" if is_reverse else "红方"

        return EngineSnapshot(
            fen=fen,
            side_to_move=side_wb,
            side_cn=side_cn,
            red_to_move=red_to_move,
            engine_loaded=bool(data.get("engineLoaded", False)),
            engine_name=data.get("engineName"),
            best_move=best_move,
            best_move_cn=best_cn,
            score=score,
            depth=depth,
            mate=mate,
            pv_moves=pv_moves,
            pv_cn=pv_cn,
            is_reverse=is_reverse,
            my_side=my_side,
            my_side_cn=my_side_cn,
            is_my_turn=(side_wb == my_side),
            raw=data,
        )
