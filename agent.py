"""
Agent 核心循环 + 入口测试。

手写 ReAct（Reasoning + Acting）循环，只用 openai 库，不依赖任何 Agent 框架。
循环一圈做五件事：请求模型 -> 存回复 -> 判断是否要调工具 -> 执行工具 -> 存结果。
直到模型不再调用工具、直接给出回答，或达到最大循环次数。

运行方式：python agent.py
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

from tool_registry import ToolRegistry
from tools import tr

if TYPE_CHECKING:
    from openai import OpenAI

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


def create_client() -> OpenAI:
    """实际运行时才读取配置、导入 SDK 并创建客户端。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        pass
    else:
        load_dotenv()

    from openai import OpenAI

    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", "sk-placeholder"),
        base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
    )


def run_agent(
    user_input: str,
    max_iterations: int = 5,
    *,
    client: OpenAI | None = None,
    registry: ToolRegistry | None = None,
    model: str | None = None,
) -> str:
    """运行一次完整的 Agent 任务。

    Args:
        user_input: 用户的自然语言指令。
        max_iterations: 最大循环次数，防止大模型陷入死循环。
        client: 可传入已有客户端；不传则按环境变量创建并在结束后关闭。
        registry: 可替换的工具注册表，默认使用 tools.tr。
        model: 模型名称，默认读取 LLM_MODEL。

    Returns:
        Agent 最终给用户的回答。
    """
    if not isinstance(user_input, str) or not user_input.strip():
        raise ValueError("user_input 必须是非空字符串")
    if type(max_iterations) is not int or max_iterations < 1:
        raise ValueError("max_iterations 必须是正整数")

    registry = tr if registry is None else registry
    if client is not None:
        return _run_loop(user_input, max_iterations, client, registry, model)

    with create_client() as owned_client:
        return _run_loop(user_input, max_iterations, owned_client, registry, model)


def _run_loop(
    user_input: str,
    max_iterations: int,
    client: OpenAI,
    registry: ToolRegistry,
    model: str | None,
) -> str:
    """执行对话循环；这里不负责创建或关闭客户端。"""
    model = model or os.getenv("LLM_MODEL", "deepseek-chat")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ]

    for iteration in range(1, max_iterations + 1):
        print(f"\n===== 第 {iteration} 轮 =====")

        request: dict[str, Any] = {"model": model, "messages": messages}
        schemas = registry.schemas
        if schemas:
            request.update(tools=schemas, tool_choice="auto")

        try:
            response = client.chat.completions.create(**request)
        except Exception as exc:
            return f"[Error]: 模型请求失败：{type(exc).__name__}: {exc}"

        if not response.choices:
            return "[Error]: 模型返回为空，未收到候选回复。"
        choice = response.choices[0]
        if choice.finish_reason == "length":
            return "[Error]: 模型回复因长度限制被截断，任务尚未完成。"
        if choice.finish_reason == "content_filter":
            return "[Error]: 模型回复被内容过滤终止，任务尚未完成。"

        message = choice.message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            if not message.content or not message.content.strip():
                return "[Error]: 模型未返回回答或工具调用。"
            print(f"[最终回答] {message.content}")
            return message.content

        print(f"[模型回复] {message.content or '（决定调用工具）'}")
        for tool_call in message.tool_calls:
            name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except (json.JSONDecodeError, TypeError) as exc:
                result = f"[Error]: {name} 的参数不是合法 JSON：{exc}"
            else:
                print(f"[调用工具] {name}({args})")
                result = registry.call(name, args)

            print(f"[工具结果] {result}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                }
            )

    print(f"\n[终止] 已达最大循环次数 {max_iterations}")
    return f"任务在 {max_iterations} 轮内尚未完成，已停止继续调用工具。"


def main() -> None:
    question = "去前面看看，然后告诉我电量"
    print("=" * 55)
    print(f"用户指令：{question}")
    print("=" * 55)

    answer = run_agent(question)

    print("\n" + "=" * 55)
    print(f"最终答案：{answer}")
    print("=" * 55)


if __name__ == "__main__":
    main()
