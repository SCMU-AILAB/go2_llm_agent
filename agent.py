"""
Agent 核心循环 + 入口测试。

手写 ReAct（Reasoning + Acting）循环，只用 openai 库，不依赖任何 Agent 框架。
循环一圈做五件事：请求模型 -> 存回复 -> 判断是否要调工具 -> 执行工具 -> 存结果。
直到模型不再调用工具、直接给出回答，或达到最大循环次数。

运行方式：python agent.py
"""

import json
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from openai import OpenAI

from tools import TOOLS_SCHEMA, TOOL_MAP

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY", "sk-placeholder"),
    base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
)
MODEL = os.getenv("LLM_MODEL", "deepseek-chat")

SYSTEM_PROMPT = """你是一台宇树 Go2 机器狗的智能控制助手。

你负责理解用户的自然语言指令，并调用工具控制机器狗完成任务。

工作原则：
1. 先想清楚需要哪些动作，再调用对应工具。
2. 必须用工具获取真实状态，不要编造电量或位置。
3. "看看""看一下""观察一下""前方有什么"这类词，都表示要调用 take_photo 拍照。
   如果用户同时要求移动，必须先 move_forward 再 take_photo，两步都不能省，
   不允许把该做的动作改成"问用户要不要做"。
4. 用户指令中提到的每一个动作都要执行完，再给最终回答。
5. 任务完成后，用简洁的中文总结你做了什么。
6. 始终使用中文思考和回答。
"""


def run_agent(user_input: str, max_iterations: int = 5) -> str:
    """运行一次完整的 Agent 任务。

    Args:
        user_input: 用户的自然语言指令。
        max_iterations: 最大循环次数，防止大模型陷入死循环。

    Returns:
        Agent 最终给用户的回答。
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    for iteration in range(1, max_iterations + 1):
        print(f"\n===== 第 {iteration} 轮 =====")

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            print(f"[最终回答] {message.content}")
            return message.content or ""

        print(f"[模型思考] {message.content or '（决定调用工具）'}")
        for tool_call in message.tool_calls:
            name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments or "{}")
                print(f"[调用工具] {name}({args})")
                result = TOOL_MAP[name](**args)
            except Exception as exc:
                result = f"执行失败：{exc}。请检查参数后重试。"

            print(f"[工具结果] {result}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                }
            )

    print(f"\n[终止] 已达最大循环次数 {max_iterations}")
    return f"任务在 {max_iterations} 轮内未完成，请重新描述需求。"


if __name__ == "__main__":
    question = "去前面看看，然后告诉我电量"
    print("=" * 55)
    print(f"用户指令：{question}")
    print("=" * 55)

    answer = run_agent(question)

    print("\n" + "=" * 55)
    print(f"最终答案：{answer}")
    print("=" * 55)
