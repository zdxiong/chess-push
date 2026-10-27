"""走子效果分析测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chesspush.core.fen import empty_board, parse_fen
from chesspush.core.move import Move
from chesspush.core.evaluator import analyze_move


FEN_STR = "3nka3/4a4/3cb2Cn/6pC1/1N2R3p/4P1P2/5r2c/8N/4Ar3/2BAK1BR1 b - - 0 1"


def test_capture_effect():
    b = empty_board()
    b[5][4] = "R"   # 红车 e5
    b[9][4] = "K"   # 红帅
    b[0][4] = "k"   # 黑将
    b[3][4] = "p"   # 黑卒 e3
    # 车 e5 吃 e3 黑卒（合法，中间无子）
    eff = analyze_move(b, "w", Move(fr=(5, 4), to=(3, 4)), move_cn="车五进二")
    assert eff.is_capture
    assert eff.captured == "卒"
    # 车吃卒：价值差大，非兑子
    assert "兑车" not in eff.tags


def test_check_effect():
    b = empty_board()
    b[0][4] = "k"     # 黑将
    b[5][4] = "R"     # 红车
    b[9][4] = "K"     # 红帅（避免红被将军）
    b[0][4] = "k"
    # 红车 e5 平到 e0 将军？e5->e0 吃将不合法，换一种：车 e5 走到 e2 将军
    eff = analyze_move(b, "w", Move(fr=(5, 4), to=(2, 4)), move_cn="车五进三")
    assert eff.is_check is True
    assert "将军" in eff.tags


def test_trade_tag():
    b = empty_board()
    # 黑炮 c 在黑方半场任意，红马 n 与红炮：构造炮吃炮
    b[6][4] = "C"   # 红炮 e6
    b[3][4] = "c"   # 黑炮 e3
    b[9][4] = "K"
    b[0][4] = "k"
    eff = analyze_move(b, "w", Move(fr=(6, 4), to=(3, 4)), move_cn="炮五退三")
    assert eff.is_capture
    assert eff.captured == "炮"
    assert "兑炮" in eff.tags  # 炮换炮价值相等


def test_real_fen_best_move():
    """对真实 FEN 与 bestMove d7d3（炮4进4）做分析，不应抛错。"""
    from chesspush.core.move import parse_coord_move
    fen = parse_fen(FEN_STR)
    move = parse_coord_move("d7d3")  # 黑炮 row2 col3 进4到 row6 col3
    eff = analyze_move(fen.board, "b", move, move_cn="炮４进４", score=-2803)
    assert eff.side == "b"
    assert eff.side_cn == "黑方"
    assert eff.piece == "炮"
    assert eff.direction == "进"
    # 有走子类型
    assert eff.new_board is not None
    assert eff.to_facts()["side_to_move"] == "黑方"


def _red_rook_board():
    b = empty_board()
    b[8][1] = "R"      # 红车 c8（底线附近）
    b[9][4] = "K"      # 红帅
    b[0][4] = "k"      # 黑将
    return b


def test_rook_retreat_is_home_guard():
    # 红车从 row8 退到 row9（自己老家）：应标「回车守家」，不是开出直车
    b = _red_rook_board()
    eff = analyze_move(b, "w", Move(fr=(8, 1), to=(9, 1)), move_cn="车八退一")
    assert "回车守家" in eff.tags
    assert "开出直车" not in eff.tags


def test_rook_advance_capture_threat_not_open():
    # 红车从底线进到 e6 攻击黑车 e5：应标「抓车」，不标开出直车
    b = _red_rook_board()
    b[8][4] = "R"
    b[5][4] = "r"      # 黑车 e5
    eff = analyze_move(b, "w", Move(fr=(8, 4), to=(6, 4)), move_cn="车五进二")
    assert "抓车" in eff.tags
    assert "开出直车" not in eff.tags


def test_rook_open_from_base():
    # 红车从底线开出到 e6，无威胁目标：标开出直车
    b = _red_rook_board()
    b[8][4] = "R"
    eff = analyze_move(b, "w", Move(fr=(8, 4), to=(6, 4)), move_cn="车五进二")
    assert "开出直车" in eff.tags


def _base_board():
    b = empty_board()
    b[9][4] = "K"
    b[0][4] = "k"
    return b


def test_horse_linked():
    # 黑马 (4,4) 跳到 (6,3)，与另一黑马 (5,5) 成连环马
    b = _base_board()
    b[4][4] = "n"
    b[5][5] = "n"
    eff = analyze_move(b, "b", Move(fr=(4, 4), to=(6, 3)), move_cn="马３进４")
    assert "连环马" in eff.tags


def test_horse_open():
    # 红马从底线马位 (9,1) 跳出到 (7,2)
    b = _base_board()
    b[9][1] = "N"
    eff = analyze_move(b, "w", Move(fr=(9, 1), to=(7, 2)), move_cn="马八进七")
    assert "出马" in eff.tags


def test_cannon_center():
    # 红炮落到中路列4：镇中炮
    b = _base_board()
    b[8][3] = "C"
    eff = analyze_move(b, "w", Move(fr=(8, 3), to=(6, 4)), move_cn="炮八平五")
    assert "镇中炮" in eff.tags


def test_cannon_pin_rook():
    # 红炮平到 (5,5)，隔(5,6)黑马打(5,7)黑车：平炮打车
    b = _base_board()
    b[5][3] = "C"
    b[5][6] = "n"
    b[5][7] = "r"
    eff = analyze_move(b, "w", Move(fr=(5, 3), to=(5, 5)), move_cn="炮五平四")
    assert "平炮打车" in eff.tags


def test_cannon_double():
    # 红炮 (6,3) 走到 (4,3)，与(8,3)红炮同列：重炮
    b = _base_board()
    b[6][3] = "C"
    b[8][3] = "C"
    eff = analyze_move(b, "w", Move(fr=(6, 3), to=(4, 3)), move_cn="炮六进二")
    assert "重炮" in eff.tags


def test_pawn_cross_river():
    # 红兵从 row5 进到 row4 过河：过河兵
    b = _base_board()
    b[5][4] = "P"
    eff = analyze_move(b, "w", Move(fr=(5, 4), to=(4, 4)), move_cn="兵五进一")
    assert "过河兵" in eff.tags


def test_advisor_fortify():
    # 红士 (8,3) 落子 (7,4) 补强中路：补士固中
    b = _base_board()
    b[8][3] = "A"
    eff = analyze_move(b, "w", Move(fr=(8, 3), to=(7, 4)), move_cn="仕四进五")
    assert "补士固中" in eff.tags


def test_elephant_fly():
    # 红相 (9,2) 飞至 (7,4)：飞相 + 补相固中
    b = _base_board()
    b[9][2] = "B"
    eff = analyze_move(b, "w", Move(fr=(9, 2), to=(7, 4)), move_cn="相七进五")
    assert "飞相" in eff.tags
    assert "补相固中" in eff.tags


def test_king_move():
    # 红帅 (9,4) 上行一步：出将
    b = _base_board()
    eff = analyze_move(b, "w", Move(fr=(9, 4), to=(8, 4)), move_cn="帅五进一")
    assert "出将" in eff.tags


# ---------- 有根 / 无根（抓子与占优的关键） ----------
def test_capture_unrooted_is_advantage():
    # 车吃无根马：净赚大子 -> 吃马占优
    b = _base_board()
    b[6][4] = "R"
    b[5][4] = "n"      # 黑马无根
    eff = analyze_move(b, "w", Move(fr=(6, 4), to=(5, 4)), move_cn="车五进一")
    assert "吃马占优" in eff.tags
    assert "兑车" not in eff.tags


def test_capture_rooted_is_trade():
    # 车吃有根马（黑车保护）：对兑，不占优
    b = _base_board()
    b[6][4] = "R"
    b[5][4] = "n"
    b[4][4] = "r"      # 黑车保护黑马
    eff = analyze_move(b, "w", Move(fr=(6, 4), to=(5, 4)), move_cn="车五进一")
    assert "兑车" in eff.tags
    assert "吃马占优" not in eff.tags


def test_grab_rooted_no_tag():
    # 红车进 e6 威胁黑车 e5，但黑车被 (5,5) 黑车保护（有根）：不标抓车
    b = _base_board()
    b[8][4] = "R"
    b[5][4] = "r"
    b[5][5] = "r"      # 保护黑车 e5
    eff = analyze_move(b, "w", Move(fr=(8, 4), to=(6, 4)), move_cn="车五进二")
    assert "抓车" not in eff.tags


def test_grab_unrooted_tag():
    # 红车进 e6 威胁无根黑车 e5：标抓车
    b = _base_board()
    b[8][4] = "R"
    b[5][4] = "r"      # 黑车无根
    eff = analyze_move(b, "w", Move(fr=(8, 4), to=(6, 4)), move_cn="车五进二")
    assert "抓车" in eff.tags
