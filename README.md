# chess-push · 中国象棋实时走子推演解说

读取本地 TCHESS（Pikafish 引擎）对外服务（默认 `http://localhost:8787`）的当前盘面，
取引擎最佳着法，结合当前 FEN **计算走子之后的效果与走子目的**（将军、对子、压马、
进兵活马、补士固中等），由本地 qwen3.5-4b（vLLM / OpenAI 兼容，默认
`http://localhost:8000/v1`）生成「我方视角」的解说词，并**实时监听盘面变化自动推送**。

## 核心能力

- **盘面信息提取**：FEN、行棋方、棋盘数组、引擎多 PV 分析（depth / score / mate / bestMove / 中文谱）。
- **走子效果计算（规则引擎，确定性强）**：应用最佳走法得到新局面，判定
  是否将军 / 吃子（吃了什么）、走子类型与方向、进兵活马、压马、补士固中等术语标签。
- **走子目的解说（LLM 增强）**：把结构化事实喂给本地 LLM，生成流畅的中文解说；
  LLM 不可用时降级为规则模板解说。
- **实时监听**：轮询 8787，FEN 变化即触发推演并推送；首帧也推一次当前局面。
- **我方视角（isReverse）**：盘面 `isReverse=False` = 我执红，`true` = 我执黑。
  只在**轮到我方走棋**时解说走法；轮到对手走棋时不输出。

## 目录结构

```
chess-push/
├── config/config.yaml          # 全局配置（引擎/LLM/监听/解说/推送）
├── src/chesspush/
│   ├── config.py               # 配置加载
│   ├── core/                   # 领域层（纯逻辑，无 IO）
│   │   ├── fen.py              # FEN 解析 / 序列化
│   │   ├── move.py             # 走法模型（坐标↔中文）
│   │   ├── board.py            # 棋盘模型 + 将军检测 + 攻击判定
│   │   └── evaluator.py        # 走子效果与术语标签分析
│   ├── services/               # 服务层（外部依赖）
│   │   ├── engine_client.py    # 8787 TCHESS 客户端
│   │   └── llm_client.py       # 8000 vLLM OpenAI 兼容客户端（含降级）
│   ├── pipeline/
│   │   └── narration.py        # 推演编排（拉取→分析→LLM→组装解说）
│   ├── pushers/                # 推送层（可插拔）
│   │   ├── console.py
│   │   └── filelog.py
│   ├── listener.py             # 实时监听循环
│   └── cli.py                  # 命令行入口
├── tests/                      # pytest 单测
└── logs/                       # 推送日志（narration.jsonl / narration.txt）
```

## 安装与运行

```powershell
cd chess-push
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .          # 可选：安装为可执行包

# 单次推演（拉取当前盘面推一次）
python -m chesspush.cli --once

# 实时监听（盘面变化自动推送）
python -m chesspush.cli --listen

# 指定配置 / 轮询间隔
python -m chesspush.cli --config config\config.yaml --interval 0.5
```

## 前置依赖

1. **TCHESS 引擎服务**（8787）已在运行：提供 `/api/fen`、`/api/analysis`、`/api/state`。
2. **qwen3.5-4b LLM**（8000）建议以 vLLM 启动、OpenAI 兼容接口：
   ```
   vllm serve Qwen/Qwen3.5-4B-Instruct --port 8000
   ```
   LLM 未启动时程序会**自动降级**为规则模板解说（`on_unavailable: fallback`）。

## 效果计算说明

`core/evaluator.py` 基于中国象棋走子规则做确定性判定；其中「进兵活马」「压马」
「补士固中」等**意图类**标签采用启发式规则（代码内已注释），作为 LLM 解说的结构化
输入而非绝对结论，最终目的表述以 LLM 生成为准。

## 测试

```powershell
python -m pytest tests -q
```
