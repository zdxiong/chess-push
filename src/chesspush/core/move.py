"""走法模型。

TCHESS 引擎坐标走法形如 "d7d3"（UCCI 风格）：
- 字母 a..i：列，a=col0 … i=col8
- 数字：排（rank），**排 1 = 红方兵线(row8)，排 9 = 黑底线(row0)**，
  即内部棋盘坐标 row = 9 - 数字。
  例如 "炮4进4" 的 d7d3 = 黑炮 (row2,col3) 前进4格到 (row6,col3)，完全吻合。

中文谱（moveCn）由引擎直接给出，例如 "炮４进４"，本模块仅把坐标走法换算成
「进/退/平 + 中文子力名」便于展示。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .fen import COL_CHARS, COL_INDEX, char_to_name, side_of


def _decode(letter: str, digit: str) -> Tuple[int, int]:
    """TCHESS 排数字 -> 内部棋盘行。排 1 = row8，排 9 = row0。"""
    if letter not in COL_INDEX:
        raise ValueError(f"非法列字母: {letter}")
    if not digit.isdigit() or not (0 <= int(digit) <= 9):
        raise ValueError(f"非法排数字: {digit}")
    col = COL_INDEX[letter]
    row = 9 - int(digit)
    return row, col


@dataclass(frozen=True)
class Move:
    fr: Tuple[int, int]  # (row, col)
    to: Tuple[int, int]

    @property
    def coord(self) -> str:
        """坐标走法字符串（TCHESS 编码），如 'd7d3'。"""
        (r1, c1), (r2, c2) = self.fr, self.to
        return f"{COL_CHARS[c1]}{9 - r1}{COL_CHARS[c2]}{9 - r2}"


def parse_coord_move(coord: str) -> Move:
    """解析 'd7d3' 形式坐标走法（TCHESS 排编码）。"""
    s = coord.strip()
    if len(s) != 4:
        raise ValueError(f"非法坐标走法: {coord!r}")
    c1, r1, c2, r2 = s[0], s[1], s[2], s[3]
    fr = _decode(c1, r1)
    to = _decode(c2, r2)
    return Move(fr=fr, to=to)


def describe_direction(board, move: Move, side: str) -> str:
    """按行棋方判断走子方向：进 / 退 / 平。

    side='w'（红走）时，行号减小 = 前进；side='b'（黑走）时，行号增大 = 前进。
    行号不变 = 平。
    """
    dr = move.to[0] - move.fr[0]
    if dr == 0:
        return "平"
    # side='w'（红走）时行号减小为前进；side='b'（黑走）时行号增大为前进
    forward = -1 if side == "w" else 1
    return "进" if (dr > 0) == (forward > 0) else "退"


def describe_move(board, move: Move, side: str, move_cn: str | None = None) -> str:
    """人类可读的走子描述。优先用引擎给的中文谱，否则自生成。"""
    if move_cn:
        return move_cn
    ch = board[move.fr[0]][move.fr[1]]
    name = char_to_name(ch)
    direction = describe_direction(board, move, side)
    return f"{name}{direction}"
