"""FEN 解析 / 序列化测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chesspush.core.fen import parse_fen, FEN, COL_INDEX


FEN_STR = "3nka3/4a4/3cb2Cn/6pC1/1N2R3p/4P1P2/5r2c/8N/4Ar3/2BAK1BR1 b - - 0 1"


def test_parse_fen_board():
    fen = parse_fen(FEN_STR)
    assert len(fen.board) == 10
    assert all(len(row) == 9 for row in fen.board)
    # 行0 黑方底线：k 应在第4列
    assert fen.board[0][4] == "k"
    # 行9 红方底线：K 应在第4列
    assert fen.board[9][4] == "K"
    assert fen.side_to_move == "b"


def test_serialize_roundtrip():
    fen = parse_fen(FEN_STR)
    out = fen.serialize()
    assert out.split()[0] == FEN_STR.split()[0]
    assert " b" in out or out.endswith(" b")


def test_col_index():
    assert COL_INDEX["a"] == 0
    assert COL_INDEX["i"] == 8
    assert COL_INDEX["e"] == 4


def test_side_of():
    from chesspush.core.fen import side_of
    assert side_of("K") == "w"
    assert side_of("r") == "b"
    assert side_of(" ") is None
