"""走子效果与目的分析（确定性规则 + 中文术语标签）。

对「我方」（当前行棋方）走出的着法，应用走法得到新局面，分层判定走子意图：

【通用意图】（所有棋子，确定性最高，优先级从高到低）
  将死(绝杀) > 将军(+抽将) > 吃X占优 / 兑X > 抓X(威胁对方子) > 压马

【棋子特定意图】（按棋子类型，在通用意图后追加，且与抓子等去重）
  车：开出直车、回车守家
  马：连环马、出马
  炮：镇中炮、平炮打车、重炮
  兵/卒：过河兵、过河卒、进兵活马
  士：补士固中
  象/相：飞相、飞象、补相固中
  将/帅：出将

注意：意图类标签均为启发式判定（见各函数注释），可能不精确，作为本地 LLM
生成「走子目的解说」的结构化输入；LLM 不可用时由这些事实拼出规则解说。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .fen import COLS, ROWS, char_to_name, side_of
from .board import apply_move, can_attack, find_king, is_in_check
from .move import Move, describe_direction

# 子力价值（红黑同值）
PIECE_VALUE = {
    "R": 9.0, "r": 9.0,
    "N": 4.0, "n": 4.0,
    "C": 4.5, "c": 4.5,
    "P": 1.0, "p": 1.0,
    "A": 2.0, "a": 2.0,
    "B": 2.0, "b": 2.0,
    "K": 100.0, "k": 100.0,
}


@dataclass
class EffectAnalysis:
    """一次走子的结构化效果分析。"""

    side: str                    # 行棋方 w/b
    side_cn: str                 # 行棋方中文（我方视角）
    move: Move
    move_cn: Optional[str]       # 引擎中文谱
    piece: str                   # 走子中文名，如 车/马/炮/兵/士/象
    direction: str               # 进/退/平
    is_check: bool
    is_mate: bool
    is_capture: bool
    captured: Optional[str]      # 被吃子中文名
    captured_value: float        # 被吃子价值
    piece_value: float           # 走子价值
    tags: List[str] = field(default_factory=list)  # 中文术语标签
    new_fen: Optional[str] = None
    new_board: Optional[List[List[str]]] = None
    score: Optional[int] = None  # 引擎对当前局面的评分（参考）

    def to_facts(self) -> dict:
        """转成可直接投喂 LLM 的字典。"""
        return {
            "side_to_move": self.side_cn,
            "move_cn": self.move_cn or self.move.coord,
            "piece": self.piece,
            "direction": self.direction,
            "is_check": self.is_check,
            "is_mate": self.is_mate,
            "is_capture": self.is_capture,
            "captured": self.captured,
            "tags": self.tags,
            "engine_score": self.score,
        }

    def to_rules_text(self) -> str:
        """生成降级用的规则解说文本（无 LLM 时）。"""
        parts = [f"我方（{self.side_cn}）走 {self.move_cn or self.move.coord}"]
        if self.is_capture:
            parts.append(f"吃对方{self.captured}")
        if self.is_mate:
            parts.append("构成将死（绝杀）")
        elif self.is_check:
            parts.append("形成将军")
        if self.tags:
            parts.append("；".join(self.tags))
        if self.score is not None:
            parts.append(f"（引擎评分 {self.score}）")
        return "，".join(parts) + "。"


def analyze_move(
    board,
    side: str,
    move: Move,
    move_cn: Optional[str] = None,
    score: Optional[int] = None,
    mate: Optional[int] = None,
) -> EffectAnalysis:
    """对给定走法做效果分析。board 为走子前棋盘。"""
    res = apply_move(board, move, side)
    new_board = res.new_board
    captured = res.captured

    ch = board[move.fr[0]][move.fr[1]]
    piece = char_to_name(ch)
    direction = describe_direction(board, move, side)

    opp = "b" if side == "w" else "w"
    is_check = is_in_check(new_board, opp)
    is_mate = bool(mate is not None) or _mate_if_check(new_board, opp, is_check)

    captured_cn = char_to_name(captured) if captured else None
    captured_value = PIECE_VALUE.get(captured, 0.0)
    piece_value = PIECE_VALUE.get(ch, 0.0)

    tags: List[str] = []
    # ---- 通用意图（优先级从高到低）----
    if is_mate:
        tags.append("将死（绝杀）")
    if is_check:
        tags.append("将军")
        if captured is not None:
            tags.append("抽将")
    if captured is not None:
        # 被吃子是否有根（走前被同方保护）决定是「占优」还是「兑子」
        protected = _is_protected(board, move.to[0], move.to[1], opp)
        if protected or abs(captured_value - piece_value) <= 1.0:
            tags.append(f"兑{piece}")
        else:
            tags.append(f"吃{captured_cn}占优")

    # ---- 棋子特定意图（去重）----
    _apply_piece_intents(new_board, board, move, side, ch, captured, is_check, tags)

    return EffectAnalysis(
        side=side,
        side_cn="红方" if side == "w" else "黑方",
        move=move,
        move_cn=move_cn,
        piece=piece,
        direction=direction,
        is_check=is_check,
        is_mate=is_mate,
        is_capture=captured is not None,
        captured=captured_cn,
        captured_value=captured_value,
        piece_value=piece_value,
        tags=list(dict.fromkeys(tags)),  # 去重保序
        new_fen=_board_to_fen(new_board, opp),
        new_board=new_board,
        score=score,
    )


# ============================================================
# 基础辅助
# ============================================================
def _mate_if_check(new_board, opp_side, is_check: bool) -> bool:
    """粗略将死判定：仅当对方将/帅已被吃掉时视为结束。真正的将死以引擎 mate 为准。"""
    if not is_check:
        return False
    return find_king(new_board, opp_side) is None


def _is_protected(board, tr, tc, side) -> bool:
    """判断 (tr,tc) 处的 side 方棋子是否被同方另一子保护（有根）。

    将/帅也算保护者（贴身护卫）。用于区分「抓子/占优」与「兑子」。
    """
    for r in range(ROWS):
        for c in range(COLS):
            p = board[r][c]
            if p == " " or (r, c) == (tr, tc):
                continue
            if side_of(p) == side and can_attack(board, r, c, tr, tc):
                return True
    return False


def _threatened_target(new_board, tr, tc, side) -> Optional[str]:
    """走后 (tr,tc) 威胁到的第一个『无根』对方非将子。

    无根（无保护）才叫抓子；有根的目标不算抓子。返回其中文名或 None。
    """
    opp = "b" if side == "w" else "w"
    opp_king = "k" if opp == "b" else "K"
    for r in range(ROWS):
        for c in range(COLS):
            target = new_board[r][c]
            if target == " " or target == opp_king:
                continue
            if side_of(target) == opp and can_attack(new_board, tr, tc, r, c):
                if not _is_protected(new_board, r, c, opp):
                    return char_to_name(target)
    return None


def _is_linked_horse(new_board, pos, side) -> bool:
    """判断 (r,c) 处的马是否与另一同方马形成连环马（日字相邻互相保护）。"""
    r, c = pos
    horse = "N" if side == "w" else "n"
    for dr, dc in ((2, 1), (2, -1), (-2, 1), (-2, -1),
                   (1, 2), (1, -2), (-1, 2), (-1, -2)):
        rr, cc = r + dr, c + dc
        if 0 <= rr < ROWS and 0 <= cc < COLS and new_board[rr][cc] == horse:
            return True
    return False


def _is_double_cannon(new_board, pos, side) -> bool:
    """判断 (r,c) 处是否与另一同方炮同列（重炮阵型）。"""
    r, c = pos
    cannon = "C" if side == "w" else "c"
    for rr in range(ROWS):
        if rr == r:
            continue
        if new_board[rr][c] == cannon:
            return True
    return False


# ============================================================
# 各棋子特定意图
# ============================================================
def _rook_intents(new_board, move, side, ch, captured, tags):
    """车：开出直车 / 回车守家（不吃子、不抓子时）。"""
    forward = -1 if side == "w" else 1
    dr = move.to[0] - move.fr[0]
    if dr != 0 and (dr > 0) != (forward > 0):
        tags.append("回车守家")
        return
    if captured is not None:
        return
    if _threatened_target(new_board, move.to[0], move.to[1], side):
        return  # 已在抓子，不再标开出直车
    if side == "w" and move.fr[0] >= 7 and move.to[0] < 7:
        tags.append("开出直车")
    elif side == "b" and move.fr[0] <= 2 and move.to[0] > 2:
        tags.append("开出直车")


def _horse_intents(new_board, move, side, ch, captured, tags):
    """马：连环马 / 出马。"""
    fr, to = move.fr, move.to
    if _is_linked_horse(new_board, to, side):
        tags.append("连环马")
    if (side == "w" and fr[0] == 9 and fr[1] in (1, 7)) or \
       (side == "b" and fr[0] == 0 and fr[1] in (1, 7)):
        tags.append("出马")


def _cannon_intents(new_board, move, side, ch, captured, tags):
    """炮：平炮打车 / 镇中炮 / 重炮。"""
    to = move.to
    if to[1] != move.fr[1]:  # 横移
        if _threatened_target(new_board, to[0], to[1], side) == "车":
            tags.append("平炮打车")
            return
    if to[1] == 4:
        tags.append("镇中炮")
    elif _is_double_cannon(new_board, to, side):
        tags.append("重炮")


def _pawn_intents(new_board, move, side, ch, captured, tags):
    """兵/卒：过河兵/卒、进兵活马。"""
    _detect_activate_horse(new_board, move, side, ch, tags)
    fr, to = move.fr, move.to
    if ch == "P" and fr[0] >= 5 and to[0] < 5:
        tags.append("过河兵")
    elif ch == "p" and fr[0] <= 4 and to[0] > 4:
        tags.append("过河卒")


def _advisor_intents(new_board, move, side, ch, captured, tags):
    """士：补士固中。"""
    _detect_fortify_defense(move, side, ch, tags)


def _elephant_intents(new_board, move, side, ch, captured, tags):
    """象/相：飞相/飞象、补相固中。"""
    tags.append("飞相" if ch == "B" else "飞象")
    if 3 <= move.to[1] <= 5:
        tags.append("补相固中")


def _king_intents(new_board, move, side, ch, captured, tags):
    """将/帅：出将。"""
    tags.append("出将")


# ============================================================
# 跨棋子 / 分发
# ============================================================
def _detect_press_horse(new_board, move, side, tags):
    """压马：走后 to 处的子压制对方马（若已在抓子则不再标，避免重复）。"""
    if any(t.startswith("抓") for t in tags):
        return
    ch = new_board[move.to[0]][move.to[1]]
    opp_horse = "n" if side == "w" else "N"
    tr, tc = move.to
    for r in range(ROWS):
        for c in range(COLS):
            if new_board[r][c] == opp_horse:
                if can_attack(new_board, tr, tc, r, c):
                    tags.append("压马")
                    return


def _detect_activate_horse(new_board, move, side, ch, tags):
    """进兵活马：走兵/卒后原位置让出，成为某同方马一跳位的蹩马腿，使马可出动。"""
    if ch not in ("P", "p"):
        return
    fr, fc = move.fr
    tr, tc = move.to
    if tr == fr:
        return
    horse_ch = "N" if ch == "P" else "n"
    for r in range(ROWS):
        for c in range(COLS):
            if new_board[r][c] != horse_ch:
                continue
            for dr, dc in ((2, 1), (2, -1), (-2, 1), (-2, -1),
                           (1, 2), (1, -2), (-1, 2), (-1, -2)):
                sr, sc = r + dr, c + dc
                if not (0 <= sr < ROWS and 0 <= sc < COLS):
                    continue
                leg_r, leg_c = (r + dr // 2, c) if abs(dr) == 2 else (r, c + dc // 2)
                if (leg_r, leg_c) == (fr, fc) and new_board[sr][sc] == " ":
                    tags.append("进兵活马")
                    return


def _detect_fortify_defense(move, side, ch, tags):
    """补士固中：走士且落子在己方九宫，增强将帅中路防守。"""
    if ch not in ("A", "a"):
        return
    tr, tc = move.to
    palace = (7 <= tr <= 9 and 3 <= tc <= 5) if ch == "A" else (0 <= tr <= 2 and 3 <= tc <= 5)
    if palace:
        tags.append("补士固中")


_HANDLERS: Dict[str, object] = {
    "R": _rook_intents, "r": _rook_intents,
    "N": _horse_intents, "n": _horse_intents,
    "C": _cannon_intents, "c": _cannon_intents,
    "P": _pawn_intents, "p": _pawn_intents,
    "A": _advisor_intents, "a": _advisor_intents,
    "B": _elephant_intents, "b": _elephant_intents,
    "K": _king_intents, "k": _king_intents,
}


def _apply_piece_intents(new_board, board, move, side, ch, captured, is_check, tags):
    """通用跨棋子意图（抓子、压马）+ 按棋子类型分发特定意图。"""
    # 抓子：走后威胁对方非将子（未吃、非将军时）
    if captured is None and not is_check:
        t = _threatened_target(new_board, move.to[0], move.to[1], side)
        if t:
            tags.append(f"抓{t}")
    # 压马（跨棋子）
    _detect_press_horse(new_board, move, side, tags)
    # 按棋子分发
    handler = _HANDLERS.get(ch)
    if handler is not None:
        handler(new_board, move, side, ch, captured, tags)


def _board_to_fen(board, side: str) -> str:
    from .fen import FEN

    return FEN(board=board, side_to_move=side).serialize()
