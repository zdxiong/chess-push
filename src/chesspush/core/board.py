"""棋盘模型：走子应用、将军检测、子力攻击判定。

实现中国象棋各子力的攻击范围（吃子判定），用于「走子后是否将军 / 是否能吃回」
等确定性分析。棋盘为 10×9：row 0 为黑底线（将 k），row 9 为红底线（帅 K）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .fen import (
    COLS,
    ROWS,
    is_black,
    is_red,
    side_of,
)
from .move import Move


def _opposite(side: str) -> str:
    return "b" if side == "w" else "w"


def _red_palace(r: int, c: int) -> bool:
    return 7 <= r <= 9 and 3 <= c <= 5


def _black_palace(r: int, c: int) -> bool:
    return 0 <= r <= 2 and 3 <= c <= 5


def _in_board(r: int, c: int) -> bool:
    return 0 <= r < ROWS and 0 <= c < COLS


def find_king(board: List[List[str]], side: str) -> Optional[Tuple[int, int]]:
    """返回 side 方将/帅位置 (r, c)，找不到返回 None。"""
    target = "k" if side == "b" else "K"
    for r in range(ROWS):
        for c in range(COLS):
            if board[r][c] == target:
                return (r, c)
    return None


def _count_between(board, r, c, tr, tc) -> int:
    """统计 (r,c) 到 (tr,tc) 直线之间（不含两端）的棋子数。要求同一直线。"""
    dr = (tr > r) - (tr < r)
    dc = (tc > c) - (tc < c)
    count = 0
    rr, cc = r + dr, c + dc
    while (rr, cc) != (tr, tc):
        if board[rr][cc] != " ":
            count += 1
        rr += dr
        cc += dc
    return count


def can_attack(board: List[List[str]], fr: int, fc: int, tr: int, tc: int) -> bool:
    """判断 (fr,fc) 处的子能否一步吃到 (tr,tc)。不检查目标是否己方子。"""
    if not _in_board(tr, tc):
        return False
    ch = board[fr][fc]
    if ch == " ":
        return False
    dr, dc = tr - fr, tc - fc
    r, c = fr, fc

    if ch in ("R", "r"):  # 车：直线，中间无障碍
        return (dr == 0 or dc == 0) and _count_between(board, r, c, tr, tc) == 0

    if ch in ("C", "c"):  # 炮：直线，中间恰好一个炮架
        return (dr == 0 or dc == 0) and _count_between(board, r, c, tr, tc) == 1

    if ch in ("N", "n"):  # 马：日字，不蹩马腿
        if (abs(dr), abs(dc)) not in ((2, 1), (1, 2)):
            return False
        # 马腿格
        if abs(dr) == 2:
            leg_r, leg_c = r + dr // 2, c
        else:
            leg_r, leg_c = r, c + dc // 2
        return board[leg_r][leg_c] == " "

    if ch in ("P", "p"):  # 兵/卒
        return _pawn_attack(r, c, tr, tc, ch)

    if ch in ("A", "a"):  # 士：斜一格，限九宫
        palace = _red_palace if ch == "A" else _black_palace
        return abs(dr) == 1 and abs(dc) == 1 and palace(tr, tc)

    if ch in ("B", "b"):  # 象：斜两格（田字），象眼空，不过河
        if abs(dr) != 2 or abs(dc) != 2:
            return False
        # 不过河：红相留己方半场(row>=5)，黑象留己方半场(row<=4)
        if ch == "B" and tr < 5:
            return False
        if ch == "b" and tr > 4:
            return False
        eye_r, eye_c = r + dr // 2, c + dc // 2
        return board[eye_r][eye_c] == " "

    if ch in ("K", "k"):  # 将/帅
        palace = _red_palace if ch == "K" else _black_palace
        if abs(dr) <= 1 and abs(dc) <= 1 and palace(tr, tc):
            return True
        # 照面：同列且中间无子，直接"将"到对方将
        opp_king = "k" if ch == "K" else "K"
        if dc == 0 and board[tr][tc] == opp_king:
            return _count_between(board, r, c, tr, tc) == 0
        return False
    return False


def _pawn_attack(r: int, c: int, tr: int, tc: int, ch: str) -> bool:
    """兵/卒的攻击范围。红兵向前=row减小；黑卒向前=row增大。"""
    dr, dc = tr - r, tc - c
    if ch == "P":  # 红兵
        forward = -1
        crossed = r <= 5  # 到达/越过河界行(5)后可横
    else:  # 黑卒
        forward = 1
        crossed = r >= 4
    # 直进一格
    if dc == 0 and dr == forward:
        return True
    # 过河后横移一格
    if crossed and dr == 0 and abs(dc) == 1:
        return True
    return False


def is_in_check(board: List[List[str]], side: str) -> bool:
    """判断 side 方是否处于被将军状态。"""
    king = find_king(board, side)
    if king is None:
        return False
    kr, kc = king
    opp = _opposite(side)
    for r in range(ROWS):
        for c in range(COLS):
            ch = board[r][c]
            if ch != " " and side_of(ch) == opp:
                if can_attack(board, r, c, kr, kc):
                    return True
    return False


@dataclass
class ApplyResult:
    """走子应用结果。"""

    new_board: List[List[str]]
    captured: Optional[str]  # 被吃掉的对方子，None 表示无


def apply_move(board: List[List[str]], move: Move, side: str) -> ApplyResult:
    """应用走法，返回新棋盘与被吃子。目标若是己方子则视为非法并抛错。"""
    (fr, fc), (tr, tc) = move.fr, move.to
    if not _in_board(fr, fc) or not _in_board(tr, tc):
        raise ValueError(f"越界走法: {move.coord}")
    ch = board[fr][fc]
    if ch == " ":
        raise ValueError(f"起点无子: {move.coord}")
    target = board[tr][tc]
    if target != " " and side_of(target) == side:
        raise ValueError(f"吃到己方子: {move.coord}")

    new_board = [row[:] for row in board]
    new_board[tr][tc] = ch
    new_board[fr][fc] = " "
    captured = target if target != " " else None
    return ApplyResult(new_board=new_board, captured=captured)
