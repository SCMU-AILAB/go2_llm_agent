# Go2 LLM Agent

用大模型（LLM）通过自然语言控制宇树 Go2 机器狗的最小智能体（Agent）框架。

目标是把「自然语言 → 大模型决策 → 调用工具 → 观察结果 → 再次决策」这条回路先跑通。
当前**无真机**，硬件动作由 Mock 层模拟。运行 Agent 仍需连接配置的模型服务；注册表和调用循环的单元测试可以离线运行。

## 项目定位

- **极简**：只用 `openai` 库手写 ReAct 循环，不依赖 LangChain、AutoGen 等框架。
- **可迁移**：Mock 层的方法签名对齐真机 SDK，接入真机时只替换 Mock 层，Agent 逻辑无需改动。
- **可读**：四个核心代码文件，分别负责调用循环、工具注册表、工具定义和 Mock 实现。

## 架构

```
用户输入（自然语言）
        │
        ▼
  agent.py   ReAct 循环：请求模型 → 解析 tool_calls → 执行 → 回传结果 → 再请求
        │
        ▼
  tool_registry.py   ToolRegistry：register / schemas / call
        │
        ▼
  tools.py   @tr.register(schema) 把说明书与工具函数绑定在一起
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
| `tool_registry.py` | 注册 schema 与函数，统一分发调用和处理工具异常 |
| `agent.py` | Agent 核心循环 + 入口测试 |
| `tests/test_registry_and_agent.py` | 注册表、工具转发和 Agent 循环的离线测试 |
| `.gitignore` | 拦截 `.env` 与运行产物，防止密钥泄露 |

## 安装

```bash
pip install openai python-dotenv
```

需要 Python 3.10 或更新版本。离线测试仅使用 Python 标准库，不要求安装上述依赖。

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
终端逐轮打印模型回复、工具调用与结果，最后给出总结回答。

预期日志：

```
===== 第 1 轮 =====
[模型回复] ...
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

新增工具时，在 `tools.py` 中为函数加上装饰器即可，不需要另外维护工具映射表：

```python
@tr.register({
    "type": "function",
    "function": {
        "name": "echo",
        "description": "原样返回给定文本，用于测试工具调用。",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
})
def echo(text: str) -> str:
    return text
```

`tr.schemas` 提供所有工具说明；`tr.call("echo", {"text": "你好"})` 根据名称执行工具。装饰器返回原函数，保留其类型和直接调用方式。只有经过 `tr.call()` 的调用才会把执行异常转成 `[Error]: ...` 文本。

## 设计说明

- **最大循环次数** `max_iterations=5`：防止大模型陷入死循环。
- **职责划分**：Agent 解析模型返回的 JSON 参数；注册表检查参数是否为对象、查找函数并执行。
- **异常兜底**：JSON 解析错误、工具不存在、函数参数错误和执行异常都按原 `tool_call_id` 回传，让模型自行修正。模型请求异常则结束本次任务并返回错误文本。
- **注册检查**：重复工具名和明显错误的 schema 在注册时立即报错；schema 输入与输出使用副本，避免外部修改导致登记信息错乱。
- **终止检查**：空回复、长度截断和内容过滤会明确返回错误，截断回复中的工具调用不会执行。
- **上下文累积**：每轮的工具结果都追加进 `messages`，这是多步任务能串起来的关键。
- **可测试性**：`run_agent()` 可通过关键字参数 `client`、`registry`、`model` 替换依赖。默认客户端在运行时创建、结束后关闭；传入的客户端由调用方管理。

默认注册表 `tools.tr` 绑定模块中的同一个机器狗实例；多个 `run_agent()` 调用会共用它，但每次调用都重新创建对话消息历史。

## 离线测试

在仓库根目录执行：

```bash
python3 -B -m unittest discover -s tests -v
```

测试替换模型客户端和工具执行对象，不调用外部模型、不执行 MockGo2 动作。覆盖工具注册与转发、错误回传、多工具顺序和 ID 配对、执行轮数上限、模型请求失败、截断回复及客户端生命周期。

## 已知边界与局限

诚实说明当前实现**不能**做什么，避免误用：

- **Mock 不产生真实物理动作**：所有方法只打印日志并返回文本，不驱动硬件。
- **电量为模拟值**：Mock 按动作扣电，与真实电池无关。
- **多步任务中的状态可能过期**：若某步改变了状态（如拍照后电量下降），Agent 可能汇报较早读到的值。真机上应在汇报前重新查询。
- **模型思考语言不稳定**：`deepseek-chat` 有时用英文推理，不影响工具调用结果。
- **schema 不等于运行时参数校验**：类型注解和参数 schema 不会自动检查取值范围或 enum；注册表目前检查参数对象形状，并捕获函数调用异常。
- **错误结果仍是文本**：为保持 `call() -> Any` 接口简洁，错误采用 `[Error]: ...` 字符串，没有独立的结构化错误类型。
- **提示词不保证动作顺序**：代码按模型返回的工具调用顺序执行，尚未引入动作依赖检查，也不会验证最终回答是否覆盖了全部任务。
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
2. 增加真实模型服务的集成测试；
3. 相机输入与视觉决策；
4. 多轮对话与上下文管理。

## 参考

- 宇树官方 C++ SDK：https://github.com/unitreerobotics/unitree_sdk2
- 组内 Python 绑定：https://github.com/Yao0454/unitree_sdk2_bindings
