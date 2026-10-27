"""FEN 解析与序列化。

中国象棋 FEN（TCHESS / Pikafish 兼容）形如：
    3nka3/4a4/3cb2Cn/6pC1/1N2R3p/4P1P2/5r2c/8N/4Ar3/2BAK1BR1 b - - 0 1

- 棋盘 10 行 × 9 列。第 0 行为黑方底线（将 k），第 9 行为红方底线（帅 K）。
- 大写字母 = 红方，小写字母 = 黑方。
- 子力符号：
    红：K帅 A士 B象 R车 N马 C炮 P兵
    黑：k将 a士 b象 r车 n马 c炮 p卒
- 行棋方：b = 黑走，w = 红走。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

ROWS = 10
COLS = 9

# 列字母 a..i 与列下标 0..8 互转
COL_CHARS = "abcdefghi"
COL_INDEX = {c: i for i, c in enumerate(COL_CHARS)}

# 红/黑子力字符集合
RED_CHARS = "KABRNCP"
BLACK_CHARS = "kabrncp"


@dataclass(frozen=True)
class FEN:
    """解析后的盘面。board[r][c] 取值：大写红 / 小写黑 / 空格。"""

    board: List[List[str]]
    side_to_move: str  # "w" 红走 / "b" 黑走

    def clone_board(self) -> List[List[str]]:
        return [row[:] for row in self.board]

    def serialize(self) -> str:
        """序列化回 FEN 字符串（保留布局，行棋方与计数简化处理）。"""
        ranks = []
        for row in self.board:
            empty = 0
            part = []
            for cell in row:
                if cell == " ":
                    empty += 1
                else:
                    if empty:
                        part.append(str(empty))
                        empty = 0
                    part.append(cell)
            if empty:
                part.append(str(empty))
            ranks.append("".join(part))
        # 行棋方之外的字段（- - 0 1）对引擎无所谓，保留行棋方即可
        return "/".join(ranks) + " " + self.side_to_move


def parse_fen(fen: str) -> FEN:
    """解析 FEN 字符串为 FEN 对象。"""
    parts = fen.strip().split()
    if not parts:
        raise ValueError("空 FEN")
    board_str = parts[0]
    side = parts[1] if len(parts) > 1 else "w"
    if side not in ("w", "b"):
        side = "w"

    board = []
    for rank_str in board_str.split("/"):
        row = []
        for ch in rank_str:
            if ch.isdigit():
                row.extend([" "] * int(ch))
            else:
                row.append(ch)
        if len(row) != COLS:
            raise ValueError(f"行宽度异常: {rank_str!r} -> {len(row)} 列")
        board.append(row)
    if len(board) != ROWS:
        raise ValueError(f"行数异常: {len(board)}")
    return FEN(board=board, side_to_move=side)


def empty_board() -> List[List[str]]:
    return [[" "] * COLS for _ in range(ROWS)]


def char_to_name(ch: str) -> str:
    """子力字符 -> 中文名。"""
    return {
        "K": "帅", "k": "将",
        "A": "士", "a": "士",
        "B": "相", "b": "象",
        "R": "车", "r": "车",
        "N": "马", "n": "马",
        "C": "炮", "c": "炮",
        "P": "兵", "p": "卒",
    }.get(ch, ch)


def is_red(ch: str) -> bool:
    return ch in RED_CHARS


def is_black(ch: str) -> bool:
    return ch in BLACK_CHARS


def side_of(ch: str) -> str:
    """子力字符 -> 阵营 'w'/'b'，空返回 None。"""
    if ch == " ":
        return None
    return "w" if is_red(ch) else "b"
