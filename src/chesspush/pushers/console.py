"""控制台推送器。"""
from __future__ import annotations

from ..pipeline.narration import NarrationResult


class ConsolePusher:
    def push(self, result: NarrationResult) -> None:
        print("\n" + "=" * 56)
        print(f"[{result.ts}] 轮走方：{result.side_cn}")
        if result.coord:
            print(f"最佳走法：{result.coord}"
                  + (f"（{result.effect.move_cn}）" if result.effect.move_cn else ""))
            print(f"走子类型：{result.effect.piece} {result.effect.direction}")
            if result.effect.tags:
                print("术语标签：" + "、".join(result.effect.tags))
            if result.effect.is_capture:
                print(f"吃子：{result.effect.captured}")
            if result.engine_score is not None:
                print(f"引擎评分：{result.engine_score}"
                      + (f"（depth {result.depth}）" if result.depth is not None else ""))
            print("-" * 56)
            print("解说：" + result.text)
            if result.source == "rules":
                print("（注：LLM 未连接，以上为规则兜底解说）")
        else:
            print("解说：" + result.text)
        print("=" * 56)
