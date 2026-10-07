"""工具注册表：绑定 schema 与函数，并按名称分发调用。"""

from collections.abc import Callable
from copy import deepcopy
from typing import Any, TypeVar

ToolFn = Callable[..., Any]
F = TypeVar("F", bound=ToolFn)


class ToolRegistry:
    def __init__(self) -> None:
        self.registered_tools: dict[str, tuple[dict[str, Any], ToolFn]] = {}

    def register(self, schema: dict[str, Any]) -> Callable[[F], F]:
        """接收 OpenAI 格式的 schema，装饰器登记并原样返回函数。"""
        schema = deepcopy(schema)
        function = schema.get("function")
        if schema.get("type") != "function" or not isinstance(function, dict):
            raise ValueError("工具 schema 必须使用 type=function 的格式")
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("工具名称必须是非空字符串")
        parameters = function.get("parameters")
        if not isinstance(parameters, dict) or parameters.get("type") != "object":
            raise ValueError("工具 parameters 必须是 object schema")

        def deco(fn: F) -> F:
            if name in self.registered_tools:
                raise ValueError(f"工具名称重复：{name!r}")
            if not callable(fn):
                raise TypeError("只能注册可调用对象")
            self.registered_tools[name] = (schema, fn)
            return fn

        return deco

    @property
    def schemas(self) -> list[dict[str, Any]]:
        """返回 schema 副本，供 OpenAI 兼容的 Tool Calling 接口使用。"""
        return [deepcopy(schema) for schema, _ in self.registered_tools.values()]

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        """执行工具；未知工具、参数错误和执行异常统一转为错误文本。"""
        if name not in self.registered_tools:
            return f"[Error]: unknown tool {name!r}"
        if not isinstance(arguments, dict):
            return "[Error]: 工具 arguments 必须是 JSON 对象"

        _, fn = self.registered_tools[name]
        try:
            return fn(**arguments)
        except Exception as exc:
            return f"[Error]: {name}: {type(exc).__name__}: {exc}"
