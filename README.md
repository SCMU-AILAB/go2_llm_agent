# Go2 LLM Agent

用大模型（LLM）通过自然语言控制宇树 Go2 机器狗的最小智能体（Agent）框架。

目标是把「自然语言 → 大模型决策 → 调用工具 → 观察结果 → 再次决策」这条回路先跑通。
当前**无真机**，硬件动作由 Mock 层模拟，全流程离线可跑。

## 项目定位

- **极简**：只用 `openai` 库手写 ReAct 循环，不依赖 LangChain、AutoGen 等框架。
- **可迁移**：Mock 层的方法签名对齐真机 SDK，接入真机时只替换 Mock 层，Agent 逻辑无需改动。
- **可读**：三个代码文件，每个文件一个明确职责，没有任务队列、技能运行时或额外抽象层。

## 架构

```
用户输入（自然语言）
        │
        ▼
  agent.py   ReAct 循环：请求模型 → 解析 tool_calls → 执行 → 回传结果 → 再请求
        │
        ▼
  tools.py   工具 JSON Schema + 工具名到真实函数的映射（TOOL_MAP）
        │
        ▼
  mock_go2.py   MockGo2：move_forward / turn / get_battery / take_photo
                （接真机时，仅替换本层）
```

**核心回路**（`agent.py` 的 `run_agent`）：

```
input -> 请求 LLM -> 有 tool_calls?
   有  -> 执行工具 -> 结果追加进 messages -> 再请求 LLM -> ...
   无  -> 输出最终回答
```

| 文件 | 职责 |
| --- | --- |
| `mock_go2.py` | 模拟机器狗能力，方法仅打印日志 |
| `tools.py` | 把方法转成大模型可识别的 Tool Calling JSON Schema |
| `agent.py` | Agent 核心循环 + 入口测试 |
| `.gitignore` | 拦截 `.env` 与运行产物，防止密钥泄露 |

## 安装

```bash
pip install openai python-dotenv
```

## 配置

在项目根目录创建 `.env` 文件：

```
DEEPSEEK_API_KEY=sk-你的密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

密钥从环境变量读取，`.env` 已在 `.gitignore` 中排除，不会被提交到 GitHub。
换用其他 OpenAI 格式服务（Qwen、本地 llama-server 等）只需改 `LLM_BASE_URL` 与 `LLM_MODEL`。

## 快速开始

```bash
python agent.py
```

默认执行一条多步指令：`去前面看看，然后告诉我电量`。
终端逐轮打印模型思考、工具调用与结果，最后给出总结回答。

预期日志：

```
===== 第 1 轮 =====
[模型思考] ...
[调用工具] move_forward({'speed': 0.5, 'distance': 2})
[MockGo2] 向前移动 2 米...
[工具结果] 已向前移动 2 米...
```

## 已注册工具

| 工具 | 作用 | 参数 |
| --- | --- | --- |
| `move_forward` | 向前直行 | `speed`（m/s）、`distance`（m） |
| `turn` | 原地转向 | `direction`（left/right）、`angle`（°） |
| `get_battery` | 查询电量 | 无 |
| `take_photo` | 拍照 | 无 |

工具描述（`tools.py` 中的 `description`）直接决定大模型会不会正确选中该工具。
实测：用户说「看看」时，若描述里不含「看」字，模型会漏掉拍照动作，补充关键词后即修复。

## 设计说明

- **最大循环次数** `max_iterations=5`：防止大模型陷入死循环。
- **异常兜底**：参数错误、工具不存在、执行报错都会被捕获，并把错误信息回传，让模型自行修正。
- **上下文累积**：每轮的工具结果都追加进 `messages`，这是多步任务能串起来的关键。

## 已知边界与局限

诚实说明当前实现**不能**做什么，避免误用：

- **Mock 不产生真实物理动作**：所有方法只打印日志并返回文本，不驱动硬件。
- **电量为模拟值**：Mock 按动作扣电，与真实电池无关。
- **多步任务中的状态可能过期**：若某步改变了状态（如拍照后电量下降），Agent 可能汇报较早读到的值。真机上应在汇报前重新查询。
- **模型思考语言不稳定**：`deepseek-chat` 有时用英文推理，不影响工具调用结果。
- **未做单元测试**：验证方式为运行 `python agent.py` 观察日志。
- **未接真机**：真机路径、超时恢复、急停策略均未实现。

## 后续接入真机

目标平台为组内自研的 Python 绑定 [unitree_sdk2_bindings](https://github.com/Yao0454/unitree_sdk2_bindings)（封装宇树官方 C++ SDK）。

接入步骤：

1. 安装该绑定库；
2. 新建 `real_go2.py`，用 SDK 实现与 `MockGo2` **同名同签名**的方法；
3. 修改 `tools.py` 一行：`go2 = RealGo2("eth0")`，Agent 逻辑不动。

真机安全底线：

- 固定或吊装机器狗后再上电；
- 选择空旷平地，保留遥控器急停；
- 移动限速、单次动作时长设上限，先从低速小距离验证；
- SDK 返回 `status=0` 只表示命令被接受，**不代表动作物理完成**。

## 下一步

1. 真机联调与超时/恢复处理；
2. 补充单元测试，覆盖工具调用与多步回路；
3. 相机输入与视觉决策；
4. 多轮对话与上下文管理。

## 参考

- 宇树官方 C++ SDK：https://github.com/unitreerobotics/unitree_sdk2
- 组内 Python 绑定：https://github.com/Yao0454/unitree_sdk2_bindings
