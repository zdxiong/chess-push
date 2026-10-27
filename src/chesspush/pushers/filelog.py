"""文件日志推送器：追加写入 JSONL 与可读文本。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..pipeline.narration import NarrationResult


class FilePusher:
    def __init__(self, json_path: str, text_path: str):
        self.json_path = Path(json_path)
        self.text_path = Path(text_path)

    def push(self, result: NarrationResult) -> None:
        # JSONL
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.json_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result.to_dict(), ensure_ascii=False) + os.linesep)

        # 可读文本：带 BOM 的 UTF-8，便于 Windows 记事本正确识别中文
        with open(self.text_path, "a", encoding="utf-8-sig") as f:
            f.write(self._fmt(result) + os.linesep)

    @staticmethod
    def _fmt(result: NarrationResult) -> str:
        head = f"[{result.ts}] {result.side_cn}"
        if result.coord:
            head += f" 走 {result.coord}"
            if result.effect.move_cn:
                head += f"（{result.effect.move_cn}）"
        head += f" [{result.source}]"
        return head + " | " + result.text
