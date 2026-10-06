# Go2 LLM Agent

用大模型（LLM）通过自然语言控制宇树 Go2 机器狗的最小智能体（Agent）框架。

当前**无真机**，所有硬件动作由 Mock 层模拟。目标是先跑通
「自然语言 → 大模型决策 → 调用工具 → 观察结果 → 再次决策」的完整闭环。

## 项目定位

- **极简**：只用 `openai` 库手写 ReAct 循环，不依赖 LangChain、AutoGen 等框架。
- **可迁移**：Mock 层的方法签名对齐 `unitree_sdk2_python`，接入真机时只替换 Mock 层，
  Agent 逻辑无需改动。

## 架构

```
用户输入（自然语言）
        │
        ▼
  agent.py   ReAct 循环：请求模型 → 解析 tool_calls → 执行 → 回传结果
        │
        ▼
  tools.py   工具 JSON Schema + 工具名到真实函数的映射
        │
        ▼
  mock_go2.py   MockGo2：move_forward / turn / get_battery / take_photo
                （接真机时，仅替换本层）
```

| 文件 | 职责 |
| --- | --- |
| `mock_go2.py` | 模拟机器狗能力，方法仅打印日志 |
| `tools.py` | 把方法转成大模型可识别的 Tool Calling JSON Schema |
| `agent.py` | Agent 核心循环 + 入口测试 |
| `.gitignore` | 拦截 `.env` 与临时文件，防止密钥泄露 |

## 安装

```bash
pip install openai python-dotenv
```

## 配置

在项目根目录创建 `.env` 文件，填入你的 DeepSeek 密钥：

```
DEEPSEEK_API_KEY=sk-你的密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

`.env` 已在 `.gitignore` 中排除，不会被提交到 GitHub。

## 运行

```bash
python agent.py
```

终端会打印每一轮的模型思考、工具调用与结果，最后给出 Agent 的总结回答。

## 安全设计

- **最大循环次数** `max_iterations=5`：防止大模型陷入死循环。
- **异常兜底**：参数错误、工具不存在、执行报错都会被捕获，并把错误信息回传给模型，
  让它自行修正。
- **密钥隔离**：API Key 通过环境变量读取，且被 `.gitignore` 排除，不会泄露。

## 后续接入真机

接入真机只需替换 `tools.py` 里的实例：

1. 安装官方 SDK：`pip install unitree_sdk2_python`；
2. 新建 `real_go2.py`，用 SDK 实现与 `MockGo2` 同名的方法；
3. 修改 `tools.py`：`go2 = RealGo2("eth0")`，其余代码不动；
4. 真机测试前务必：固定或吊装机器狗、选择空旷平地、保留遥控器急停、
   先在低速小距离下验证。
