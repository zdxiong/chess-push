# chess-push 项目分析报告

## 项目概述

**chess-push** 是一个中国象棋实时走子推演解说系统。它通过读取本地 TCHESS/Pikafish 引擎服务（默认 8787 端口）的当前盘面，取引擎最佳着法，结合 FEN 做确定性走子效果分析（将军/吃子/术语标签等），再由本地 LLM（qwen3.5-4b，OpenAI 兼容，默认 8000 端口）生成"我方视角"的中文解说词，实时监听盘面变化并自动推送。

## 架构评分

项目整体架构清晰，分层合理（core/services/pipeline/pushers/listener），代码质量在中等偏上水平。35 个单元测试全部通过。但存在若干**功能缺陷、安全隐患、健壮性不足和工程化缺失**的问题。

---

## 一、功能缺陷（BUG / 逻辑错误）

### 1.1 `apply_move` 不做走法合法性校验

**文件**: `src/chesspush/core/board.py:159-175`

`apply_move` 只检查了越界、起点无子、吃到己方子，但**不校验走法路径是否合法**（如车是否直线、马是否日字、炮是否翻山等）。如果引擎返回了一个非法走法（或盘面与引擎分析不同步），`apply_move` 会静默地"飞子"——把棋子从起点直接搬到终点，产生完全错误的局面。

**影响**: `evaluator.py` 基于这个新局面做的所有分析（将军/吃子/抓子）都会出错，LLM 解说也会跟着错。

**建议**: `apply_move` 应至少做 `can_attack` 级别的路径校验（车直线无阻、马日字蹩腿、炮翻山等），或在走法不合法时抛出明确异常。

### 1.2 `_mate_if_check` 将死判定过于粗糙

**文件**: `src/chesspush/core/evaluator.py:160-164`

```python
def _mate_if_check(new_board, opp_side, is_check: bool) -> bool:
    if not is_check:
        return False
    return find_king(new_board, opp_side) is None
```

这个函数只有在对方将/帅**已被吃掉**时才返回 True。但真正的将死（绝杀）是"被将军且无法解将"。当前实现完全依赖引擎的 `mate` 参数——如果引擎没给 `mate`，则永远不会标"将死（绝杀）"。

**影响**: 术语标签中"将死（绝杀）"几乎不会被触发（除非引擎给了 mate 且将帅已被吃），导致关键术语缺失。

**建议**: 要么完全依赖引擎 `mate` 参数（去掉 `_mate_if_check`），要么实现一个简化版的将死判定（检查所有可能的解将走法）。

### 1.3 `describe_move` 函数的 `board` 参数未被使用

**文件**: `src/chesspush/core/move.py:68-75`

```python
def describe_move(board, move: Move, side: str, move_cn: str | None = None) -> str:
    if move_cn:
        return move_cn
    ch = board[move.fr[0]][move.fr[1]]
    name = char_to_name(ch)
    direction = describe_direction(board, move, side)
    return f"{name}{direction}"
```

`board` 参数传进来了，`describe_direction` 的签名也接收 `board`，但 `describe_direction` 内部根本没用到 `board`。这只是个代码异味，不影响正确性，但让人误以为需要棋盘信息。

### 1.4 兵/卒过河判定边界有误

**文件**: `src/chesspush/core/board.py:117-132`

```python
if ch == "P":  # 红兵
    forward = -1
    crossed = r <= 5  # 到达/越过河界行(5)后可横
```

红兵从 row 5 开始算"过河"（`crossed = r <= 5`），但 row 5 正好是河界线。严格来说，红兵过河应该是 `r < 5`（即 row 4 及以上才是对方半场）。`_pawn_intents` 中 `fr[0] >= 5 and to[0] < 5` 的判定倒是对的，但 `can_attack` 中的 `crossed` 定义与之不一致——row 5 的红兵可以横移，但实际上 row 5 还在河这边（红方半场是 row 5-9，黑方半场是 row 0-4）。

**影响**: 处于河界线（row 5 红兵 / row 4 黑卒）的兵卒被错误地认为可以横走攻击，可能导致将军/抓子判定出错。

### 1.5 `_is_protected` 判定不排除走子前的起点

**文件**: `src/chesspush/core/evaluator.py:167-179`

`_is_protected` 在**走子前棋盘**上判断目标位置是否有根。但此时走子方的棋子还在起点，如果走子的棋子本身就是目标的保护者（比如车在 e6 保护 e5 的马，然后车从 e6 走到 e5 吃马——这不太合理但逻辑上可能），计算会产生偏差。不过更大的问题是：它用的是走子前的 board，而此时目标位置上还放着**即将被吃的对方棋子**，`_is_protected` 会检查对方棋子是否有同方保护——这是正确的。但在某些复杂局面下，走子方走子后可能改变保护关系，当前实现在走前棋盘上判断保护关系，有一定偏差。

---

## 二、安全问题

### 2.1 LLM Prompt 注入风险

**文件**: `src/chesspush/pipeline/narration.py:120-125`

```python
user = (
    "局面事实：\n"
    f"{json.dumps(effect.to_facts(), ensure_ascii=False)}\n"
    "请以上述事实为准，以我方（行棋方）视角解说这一步的走子目的与效果。"
)
```

`to_facts()` 中的 `move_cn` 来自引擎返回的 `moveCn` 字段。如果引擎返回了恶意的 `moveCn`（比如包含 prompt 注入文本），它会被原样插入 LLM 的 user 消息中。虽然 JSON 序列化会加引号，但 LLM 可能仍会被其中的内容影响。

**影响**: 低风险（本地引擎，非公开接口），但如果未来引擎换成远程服务则有隐患。

### 2.2 配置文件无 Schema 校验

**文件**: `src/chesspush/config.py`

`load_config` 只做 YAML 加载和环境变量覆盖，不校验配置结构和值域。如果配置文件中 `poll_interval` 写成了字符串 `"abc"`，或者 `base_url` 写成了空字符串，程序不会报错，而是在运行时产生各种难以追踪的异常。

**建议**: 添加基本的配置校验（关键字段存在性 + 类型检查 + 值域范围）。

---

## 三、健壮性不足

### 3.1 引擎客户端无重试机制

**文件**: `src/chesspush/services/engine_client.py:43-47`

```python
def _get(self, endpoint: str) -> dict:
    url = f"{self.base_url}{endpoint}"
    r = requests.get(url, timeout=self.timeout)
    r.raise_for_status()
    return r.json()
```

单次请求失败就直接抛异常。`listener.py` 中虽然 catch 了异常并 `sleep(poll_interval * 2)` 后继续，但没有指数退避，也没有连续失败计数。如果引擎长时间不可用，会持续高频重试。

### 3.2 LLM 客户端 `resolve_model` 缓存后不可变

**文件**: `src/chesspush/services/llm_client.py:42-53`

模型名探测只在首次调用时做一次（`_resolved_done` 标志位）。如果首次探测时 LLM 服务暂时不可用（返回空列表），则 `_resolved_model` 被设为 `None`，之后即使 LLM 恢复了也不会重试探测——所有后续调用都直接返回 `None`，永远使用规则降级。

**影响**: LLM 短暂不可用 → 永久降级到规则解说，需要重启程序才能恢复。

**建议**: 去掉 `_resolved_done` 缓存，或在 `_resolved_model is None` 时每次都尝试探测。

### 3.3 监听器缺少优雅退出机制

**文件**: `src/chesspush/listener.py:55-103`

`run` 方法是一个 `while` 死循环，靠 `Ctrl+C` 退出。没有信号处理（`signal.SIGINT`/`SIGTERM`），没有清理逻辑（如关闭文件句柄、刷新缓冲）。在生产环境中可能导致日志文件不完整。

### 3.4 文件推送器无文件锁和大小限制

**文件**: `src/chesspush/pushers/filelog.py`

`FilePusher` 每次 `push` 都以 append 模式打开文件写入再关闭。没有文件锁（多进程并发时可能交错），没有日志轮转/大小限制，长期运行可能产生巨大日志文件。

### 3.5 `narration.py` 中 `_dummy_move` 延迟导入

**文件**: `src/chesspush/pipeline/narration.py:151-154`

```python
def _dummy_move():
    from ..core.move import Move
    return Move(fr=(0, 0), to=(0, 0))
```

`narration.py` 顶部已经通过 `analyze_move` 间接依赖了 `move` 模块，但 `_dummy_move` 却用了函数内延迟导入。虽然功能正确（避免循环导入），但风格不一致。更合理的做法是在文件顶部直接 `from ..core.move import Move`。

---

## 四、工程化缺失

### 4.1 缺少日志框架

整个项目使用 `print()` 输出诊断信息（`listener.py`、`cli.py`）。没有使用 Python `logging` 模块，无法控制日志级别、格式化、输出目标。调试信息、警告、错误混在一起，难以过滤和持久化。

### 4.2 缺少类型标注完整性

- `listener.py` 中 `pushers: List` 应为 `List[Pusher]`（但 `Pusher` 没有 Protocol/基类定义）
- `pushers/__init__.py` 为空，没有定义 `Pusher` 抽象基类或 Protocol
- `narration.py` 的 `_generate_text` 返回类型标注为隐式（`-> tuple[str, str]` 缺失）
- `evaluator.py` 中 handler 函数签名缺少类型标注

### 4.3 Pusher 层没有抽象接口

`ConsolePusher` 和 `FilePusher` 都有 `push(result)` 方法，但没有共同的基类或 Protocol。这意味着：
- 无法做类型检查（mypy/pyright 会报错）
- 新增 pusher 时没有契约约束
- 无法在运行时做 `isinstance` 检查

### 4.4 缺少 CI/CD 配置

没有 `.github/workflows/`、`tox.ini`、`Makefile` 等自动化配置。测试只能手动运行。

### 4.5 缺少 `.gitignore`

项目根目录没有 `.gitignore` 文件（或存在但未在文件结构中体现）。`logs/` 目录下的运行时文件、`__pycache__/`、`.venv/` 等应被忽略。

### 4.6 缺少 `Pusher` 插件化机制

README 提到"推送层（可插拔）"，但当前实现是硬编码在 `build_listener` 和 `_run_once` 中。如果要新增 pusher（如 WebSocket、TTS 语音播报、微信推送），需要修改多处代码，不符合开闭原则。

### 4.7 测试覆盖不充分

当前 35 个测试主要覆盖 `core` 层（fen/board/evaluator），但：
- **services 层零测试**：`engine_client.py` 和 `llm_client.py` 完全没有测试
- **pipeline 层零测试**：`narration.py` 的 `narrate()` 函数没有测试
- **pushers 层零测试**：`ConsolePusher` 和 `FilePusher` 没有测试
- **config.py 零测试**：配置加载和环境变量覆盖没有测试
- **evaluator 的 `is_mate` 逻辑没有专门测试**：将死判定路径未覆盖
- **`can_attack` 对将/帅照面（飞将）的测试缺失**

---

## 五、代码质量问题

### 5.1 `narration.py` 中 `analyze_move` 使用 `snapshot.my_side` 而非 `snapshot.side_to_move`

**文件**: `src/chesspush/pipeline/narration.py:92-93`

```python
effect = analyze_move(
    fen.board,
    snapshot.my_side,          # 我方行棋
    ...
)
```

这里用 `my_side`（我方阵营）而非 `side_to_move`（当前行棋方）。虽然前面有 `is_my_turn` 检查确保两者一致，但这是隐式假设。如果逻辑修改后 `is_my_turn` 检查被移除或绕过，会传入错误的行棋方。

### 5.2 `engine_client.py` 中 `timeout` 参数未从 config 传入

**文件**: `src/chesspush/listener.py:113-116`

```python
engine = EngineClient(
    base_url=engine_cfg.get("base_url", "http://localhost:8787"),
    timeout=engine_cfg.get("timeout", 10.0),
)
```

`config.yaml` 的 `engine` 配置中**没有 `timeout` 字段**，但代码尝试读取它。虽然 `get("timeout", 10.0)` 有默认值不会报错，但配置和代码不同步。

### 5.3 `cli.py` 的 `--no-llm` 逻辑冗余

**文件**: `src/chesspush/cli.py:42-48`

```python
if args.no_llm:
    cfg.setdefault("llm", {})["on_unavailable"] = "fallback"
listener = build_listener(cfg)
llm = listener.llm
if args.no_llm:
    llm = None
```

`--no-llm` 先设置 `on_unavailable=fallback`（已经没意义，因为下一步就把 llm 设为 None 了），然后从 listener 取出 llm 再设为 None，最后又赋回 `listener.llm = llm`。逻辑绕了一圈，可以直接 `listener.llm = None` 即可。

### 5.4 `_board_to_fen` 函数内延迟导入

**文件**: `src/chesspush/core/evaluator.py:372-375`

```python
def _board_to_fen(board, side: str) -> str:
    from .fen import FEN
    return FEN(board=board, side_to_move=side).serialize()
```

文件顶部已经 `from .fen import COLS, ROWS, char_to_name, side_of`，却没有一起导入 `FEN`，而是在函数内延迟导入。

### 5.5 `board.py` 中马的蹩腿逻辑对负数除法可能有问题

**文件**: `src/chesspush/core/board.py:81-85`

```python
if abs(dr) == 2:
    leg_r, leg_c = r + dr // 2, c
else:
    leg_r, leg_c = r, c + dc // 2
```

Python 的 `//` 是地板除法，对负数 `-3 // 2 = -2`（而非 -1）。但这里 `dr` 的绝对值是 2，所以 `dr // 2` 只可能是 `1` 或 `-1`（因为 `2 // 2 = 1`，`-2 // 2 = -1`），所以实际上没问题。但代码可读性不够清晰，用 `dr // 2` 不如 `dr // 2 if dr > 0 else -(-dr // 2)` 或直接 `(r + tr) // 2`。

---

## 六、文档与配置问题

### 6.1 README 中的安装命令是 PowerShell 语法

README 使用 `.\.venv\Scripts\Activate.ps1` 等 PowerShell 命令，但项目在 Windows Git Bash 环境下可能不兼容。缺少跨平台的安装说明。

### 6.2 `config.yaml` 中 LLM 模型名为空字符串

```yaml
model: ""            # 留空则启动时自动从 /v1/models 探测
```

注释说明留空时自动探测，但如果 LLM 服务不可用，探测返回空列表后 `_resolved_model` 被缓存为 `None`（见 3.2），导致永久降级。

### 6.3 `config.yaml` 中 `narration.min_score_gap` 配置项未使用

配置文件中定义了 `min_score_gap: 50`，但全代码搜索没有任何地方读取和使用这个值。属于死配置。

### 6.4 `config.yaml` 中 `narration.step_text` 配置项未使用

`step_text: "single"` 同样未被代码读取。README 提到"仅推当前最佳一步"，但这是硬编码行为而非配置驱动。

---

## 七、总结与优先级建议

| 优先级 | 问题 | 影响 |
|--------|------|------|
| **P0** | 1.1 `apply_move` 不校验走法路径合法性 | 可能产生错误局面，连锁影响所有分析 |
| **P0** | 3.2 LLM 模型名缓存导致永久降级 | LLM 短暂不可用后永远无法恢复 |
| **P1** | 1.2 `_mate_if_check` 将死判定无效 | 关键术语"将死（绝杀）"几乎不触发 |
| **P1** | 1.4 兵卒过河边界判定不一致 | 河界线上的兵卒攻击范围判定有误 |
| **P1** | 2.2 配置无 Schema 校验 | 配置错误时难以排查 |
| **P1** | 4.7 测试覆盖不充分 | services/pipeline/pushers 零测试 |
| **P2** | 4.1 缺少日志框架 | 调试和运维困难 |
| **P2** | 3.1 引擎客户端无重试退避 | 引擎不可用时高频重试 |
| **P2** | 4.3 Pusher 层缺少抽象接口 | 扩展困难，类型不安全 |
| **P2** | 4.6 Pusher 插件化机制缺失 | 新增推送渠道需改多处代码 |
| **P3** | 3.3 缺少优雅退出机制 | 日志可能不完整 |
| **P3** | 3.4 文件推送无轮转限制 | 日志文件无限增长 |
| **P3** | 5.3 `--no-llm` 逻辑冗余 | 代码可读性差 |
| **P3** | 6.3/6.4 死配置项 | 配置与代码不同步 |
