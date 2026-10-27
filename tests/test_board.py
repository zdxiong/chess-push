"""棋盘 / 走法 / 将军检测测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chesspush.core.fen import empty_board, parse_fen
from chesspush.core.move import Move, parse_coord_move
from chesspush.core.board import apply_move, can_attack, is_in_check, find_king


def _simple_board():
    """构造一个简单局面：黑将 e0，红车 e9，红帅 e8。"""
    b = empty_board()
    b[0][4] = "k"      # 黑将
    b[9][4] = "K"      # 红帅
    b[9][4] = "K"
    b[5][4] = "R"      # 红车在 e5
    return b


def test_rook_attack_line():
    b = _simple_board()
    # 车 e5 直线攻击黑将 e0（中间无子）-> 可攻击，构成将军
    assert can_attack(b, 5, 4, 0, 4)
    # 非直线不可攻击
    assert not can_attack(b, 5, 4, 4, 6)


def test_rook_blocked():
    b = _simple_board()
    b[3][4] = "p"  # 黑卒挡在中间
    assert not can_attack(b, 5, 4, 0, 4)


def test_is_check():
    b = _simple_board()
    # 红车 e5 直线可吃到黑将 e0，中间无子 -> 黑方被将军
    assert is_in_check(b, "b") is True
    # 红方自己没被将军
    assert is_in_check(b, "w") is False


def test_knight_leg():
    b = empty_board()
    b[5][4] = "N"   # 红马
    b[5][3] = "P"   # 马腿（左）被占
    # 马向左跳被蹩腿
    assert not can_attack(b, 5, 4, 4, 2)
    # 向右跳（右腿 e5 处无人）可以
    assert can_attack(b, 5, 4, 4, 6)


def test_pawn_attack():
    b = empty_board()
    b[5][4] = "P"  # 红兵，未过河（row5 已可横）
    assert can_attack(b, 5, 4, 4, 4)  # 直进
    assert can_attack(b, 5, 4, 5, 3)  # row5 过河可横
    b2 = empty_board()
    b2[7][4] = "P"  # 红兵 row7 未过河
    assert not can_attack(b2, 7, 4, 7, 3)  # 未过河不能横


def test_apply_move_capture():
    b = empty_board()
    b[5][4] = "R"
    b[0][4] = "p"
    res = apply_move(b, Move(fr=(5, 4), to=(0, 4)), "w")
    assert res.captured == "p"
    assert res.new_board[0][4] == "R"
    assert res.new_board[5][4] == " "


def test_parse_coord_move():
    m = parse_coord_move("d7d3")
    # 排数字：d7 -> row 9-7=2；d3 -> row 9-3=6
    assert m.fr == (2, 3)
    assert m.to == (6, 3)
    assert m.coord == "d7d3"
