"""Listener 触发逻辑测试：FEN 变化 / best 变化应分别触发重推。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chesspush.listener import Listener
from chesspush.pipeline.narration import NarrationResult
from chesspush.services.engine_client import EngineSnapshot


class _FakeEngine:
    """按序号返回预设 snapshot。"""
    def __init__(self, snaps, base_url="http://fake"):
        self.snaps = snaps
        self.base_url = base_url
        self.i = 0

    def snapshot(self):
        s = self.snaps[self.i % len(self.snaps)]
        self.i += 1
        return s


class _Collector:
    def __init__(self):
        self.out = []

    def push(self, result):
        self.out.append(result)


def _snap(fen, best, side="b", score=-100, my_side=None, is_my_turn=True):
    if my_side is None:
        my_side = side  # 默认我方=行棋方，便于测触发
    return EngineSnapshot(
        fen=fen, side_to_move=side, side_cn="黑方", red_to_move=False,
        engine_loaded=True, engine_name="test", best_move=best,
        best_move_cn="", score=score, depth=40, mate=None,
        pv_moves=[best] if best else [], pv_cn=[],
        is_reverse=(my_side == "b"), my_side=my_side,
        my_side_cn="黑方" if my_side == "b" else "红方",
        is_my_turn=is_my_turn,
        raw={},
    )


def test_fen_change_triggers():
    # 场景：首帧推一次，FEN 变化再推一次，best 未变不重复
    fen_a = "3nka3/4a4/4b2Cn/3N2pC1/4P3p/6P2/4c4/5A2N/5r3/2rAK1BR1 w - - 0 1"
    fen_b = "3nka3/4a4/4b2Cn/3N2pC1/4P3p/6P2/4c4/5A2N/5r3/2rAK1BR1 b - - 0 1"
    engine = _FakeEngine([_snap(fen_a, "h0h3"), _snap(fen_b, "h0h3"), _snap(fen_b, "h0h3")])
    col = _Collector()
    lst = Listener(engine=engine, llm=None, pushers=[col], poll_interval=0)
    lst.run(max_iters=3)
    assert len(col.out) == 2  # 首帧 + FEN变化 各一次


def test_best_change_triggers():
    # FEN 不变但 best 变化：应触发重推
    fen = "3nka3/4a4/4b2Cn/3N2pC1/4P3p/6P2/4c4/5A2N/5r3/2rAK1BR1 w - - 0 1"
    engine = _FakeEngine([_snap(fen, "h0h3"), _snap(fen, "g4g5"), _snap(fen, "g4g5")])
    col = _Collector()
    lst = Listener(engine=engine, llm=None, pushers=[col], poll_interval=0)
    lst.run(max_iters=3)
    # 首帧 + best变化(h0h3->g4g5) 一次，之后 g4g5 稳定不再触发
    assert len(col.out) == 2


def test_stable_no_refresh():
    # 一切稳定：只推首帧一次
    fen = "3nka3/4a4/4b2Cn/3N2pC1/4P3p/6P2/4c4/5A2N/5r3/2rAK1BR1 w - - 0 1"
    engine = _FakeEngine([_snap(fen, "h0h3")])
    col = _Collector()
    lst = Listener(engine=engine, llm=None, pushers=[col], poll_interval=0)
    lst.run(max_iters=4)
    assert len(col.out) == 1


def test_opponent_turn_no_output():
    # 我方执红(w)，首帧轮到我方走输出一次；之后轮到对手(b)走，盘面变化也不输出
    fen_a = "3nka3/4a4/4b2Cn/3N2pC1/4P3p/6P2/4c4/5A2N/5r3/2rAK1BR1 w - - 0 1"
    fen_b = "3nka3/4a4/4b2Cn/3N2pC1/4P3p/6P2/4c4/5A2N/5r3/2rAK1BR1 b - - 0 1"
    engine = _FakeEngine([
        _snap(fen_a, "h0h3", side="w", my_side="w", is_my_turn=True),
        _snap(fen_b, "h0h3", side="b", my_side="w", is_my_turn=False),
        _snap(fen_b, "h0h3", side="b", my_side="w", is_my_turn=False),
    ])
    col = _Collector()
    lst = Listener(engine=engine, llm=None, pushers=[col], poll_interval=0)
    lst.run(max_iters=3)
    assert len(col.out) == 1
