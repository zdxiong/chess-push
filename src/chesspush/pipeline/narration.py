"""走子推演编排：拉取快照 → 规则分析 → LLM 解说 → 组装结果。

一次推演（single step）产出：
1. 确定性效果（规则引擎）：将军/吃子/术语标签/新局面
2. 走子目的解说（本地 LLM 生成，我方视角）
LLM 不可用时自动降级为规则解说。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..core.evaluator import EffectAnalysis, analyze_move
from ..core.fen import parse_fen
from ..core.move import parse_coord_move
from ..services.engine_client import EngineSnapshot
from ..services.llm_client import LLMClient

_SYSTEM_PROMPT = (
    "你是一位中国象棋直播解说助手。你只基于给出的局面事实进行解说，不要编造事实。"
    "以『行棋方（我方）』的第一人称视角，用一两句简短、自然、专业、面向直播观众的中文，"
    "说明这一步走法的【目的】和【能达成的效果】。可参考标签（将军/对子/压马/进兵活马/"
    "补士固中等），但要自然融入语句。输出仅解说内容本身，不要额外解释。"
)


@dataclass
class NarrationResult:
    fen: str
    side_cn: str                 # 我方（行棋方）
    coord: str
    effect: EffectAnalysis
    text: str
    source: str                  # "llm" / "rules"
    ts: str
    engine_score: Optional[int] = None
    depth: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "time": self.ts,
            "fen": self.fen,
            "side": self.side_cn,
            "best_move": self.coord,
            "source": self.source,
            "engine_score": self.engine_score,
            "depth": self.depth,
            "effect": self.effect.to_facts(),
            "narration": self.text,
        }


def narrate(snapshot: EngineSnapshot, llm: Optional[LLMClient]) -> NarrationResult:
    """对给定快照做一次走子推演与解说（仅在我方行棋时解说走法）。

    我方由 isReverse 决定：False=执红，True=执黑。轮到对手走棋时不做走法
    解说，仅提示待轮到我方。
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not snapshot.is_my_turn:
        # 轮到对手走，非我方行棋：仅提示
        eff = _no_move_effect(snapshot)
        return NarrationResult(
            fen=snapshot.fen,
            side_cn=snapshot.my_side_cn,
            coord="",
            effect=eff,
            text=(f"当前轮到对手走棋（{snapshot.side_cn}），非我方行棋。"
                  f"我方执{snapshot.my_side_cn}，待轮到我方再解说。"),
            source="rules",
            ts=ts,
        )

    if not snapshot.best_move:
        # 引擎没有分析（未开分析模式等）：给出可读说明
        eff = _no_move_effect(snapshot)
        return NarrationResult(
            fen=snapshot.fen,
            side_cn=snapshot.my_side_cn,
            coord="",
            effect=eff,
            text=f"当前轮到{snapshot.my_side_cn}，但引擎暂未给出推荐走法（请确认已开启分析模式）。",
            source="rules",
            ts=ts,
        )

    fen = parse_fen(snapshot.fen)
    move = parse_coord_move(snapshot.best_move)
    effect = analyze_move(
        fen.board,
        snapshot.my_side,          # 我方行棋
        move,
        move_cn=snapshot.best_move_cn,
        score=snapshot.score,
        mate=snapshot.mate,
    )

    text, source = _generate_text(effect, llm)
    return NarrationResult(
        fen=snapshot.fen,
        side_cn=snapshot.my_side_cn,
        coord=snapshot.best_move,
        effect=effect,
        text=text,
        source=source,
        ts=ts,
        engine_score=snapshot.score,
        depth=snapshot.depth,
    )


def _generate_text(effect: EffectAnalysis, llm: Optional[LLMClient]):
    """先生成规则兜底解说，再尝试用 LLM 生成更自然的解说。"""
    rules_text = effect.to_rules_text()
    if llm is None:
        return rules_text, "rules"
    user = (
        "局面事实：\n"
        f"{json.dumps(effect.to_facts(), ensure_ascii=False)}\n"
        "请以上述事实为准，以我方（行棋方）视角解说这一步的走子目的与效果。"
    )
    text = llm.chat([{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": user}])
    if text:
        return text.strip(), "llm"
    return rules_text, "rules"


def _no_move_effect(snapshot: EngineSnapshot) -> EffectAnalysis:
    """无推荐走法时的占位分析（用我方视角）。"""
    return EffectAnalysis(
        side=snapshot.my_side,
        side_cn=snapshot.my_side_cn,
        move=_dummy_move(),
        move_cn=None,
        piece="",
        direction="",
        is_check=False,
        is_mate=False,
        is_capture=False,
        captured=None,
        captured_value=0.0,
        piece_value=0.0,
        tags=[],
        score=snapshot.score,
    )


def _dummy_move():
    from ..core.move import Move

    return Move(fr=(0, 0), to=(0, 0))
