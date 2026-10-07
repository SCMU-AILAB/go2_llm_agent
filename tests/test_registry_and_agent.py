"""只测试注册、转发和 Agent 循环；不访问模型服务或执行 MockGo2 动作。"""

import io
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import agent
import tools
from tool_registry import ToolRegistry


def schema(name):
    return {
        "type": "function",
        "function": {
            "name": name,
            "parameters": {"type": "object", "properties": {}},
        },
    }


def tool_call(call_id, name, arguments="{}"):
    return SimpleNamespace(
        id=call_id,
        type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def response(content=None, calls=None, finish_reason=None):
    payload = {"role": "assistant"}
    if content is not None:
        payload["content"] = content
    if calls:
        payload["tool_calls"] = [
            {
                "id": item.id,
                "type": item.type,
                "function": vars(item.function),
            }
            for item in calls
        ]
    message = SimpleNamespace(
        content=content,
        tool_calls=calls,
        model_dump=Mock(return_value=payload),
    )
    choice = SimpleNamespace(
        message=message,
        finish_reason=finish_reason or ("tool_calls" if calls else "stop"),
    )
    return SimpleNamespace(choices=[choice])


class FakeClient:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result


class RegistryTests(unittest.TestCase):
    def test_registration_preserves_function_and_dispatches_using_schema_name(self):
        registry = ToolRegistry()

        def add(x: int, y: int = 1) -> int:
            return x + y

        self.assertIs(registry.register(schema("sum"))(add), add)
        self.assertEqual(registry.call("sum", {"x": 2}), 3)

    def test_duplicate_registration_preserves_original_tool(self):
        registry = ToolRegistry()
        registry.register(schema("value"))(lambda: "original")
        with self.assertRaisesRegex(ValueError, "重复"):
            registry.register(schema("value"))(lambda: "replacement")
        self.assertEqual(registry.call("value", {}), "original")

    def test_schema_is_protected_from_input_and_output_mutation(self):
        registry = ToolRegistry()
        original = schema("value")
        expected = deepcopy(original)
        registry.register(original)(lambda: 1)
        original["function"]["name"] = "changed"
        exposed = registry.schemas
        exposed[0]["function"]["parameters"]["properties"]["extra"] = {"type": "string"}
        self.assertEqual(registry.schemas, [expected])
        self.assertEqual(registry.call("value", {}), 1)

    def test_registration_rejects_malformed_schema(self):
        for invalid in (
            {},
            {"type": "function", "function": "invalid"},
            schema(" "),
            {"type": "function", "function": {"name": "missing_parameters"}},
        ):
            with self.subTest(schema=invalid), self.assertRaises(ValueError):
                ToolRegistry().register(invalid)

    def test_invalid_arguments_do_not_execute_tool_body(self):
        registry = ToolRegistry()
        executed = Mock()

        @registry.register(schema("echo"))
        def echo(text):
            executed()
            return text

        for arguments in (None, [], "text", {}, {"unexpected": 1}):
            with self.subTest(arguments=arguments):
                self.assertTrue(registry.call("echo", arguments).startswith("[Error]:"))
        executed.assert_not_called()

    def test_unknown_tool_and_internal_key_error_are_distinct(self):
        registry = ToolRegistry()

        @registry.register(schema("broken"))
        def broken():
            raise KeyError("missing data")

        self.assertIn("unknown tool", registry.call("missing", {}))
        result = registry.call("broken", {})
        self.assertIn("KeyError", result)
        self.assertNotIn("unknown tool", result)


class ToolBindingTests(unittest.TestCase):
    def test_all_registered_tools_forward_to_robot_interface(self):
        cases = {
            "move_forward": {"speed": 0.5, "distance": 2},
            "turn": {"direction": "left", "angle": 90},
            "get_battery": {},
            "take_photo": {},
        }
        names = {item["function"]["name"] for item in tools.tr.schemas}
        self.assertEqual(names, set(cases))
        with patch.object(tools, "go2") as robot:
            for name, arguments in cases.items():
                getattr(robot, name).return_value = f"result:{name}"
                with self.subTest(tool=name):
                    self.assertEqual(tools.tr.call(name, arguments), f"result:{name}")
                    getattr(robot, name).assert_called_once_with(**arguments)


class AgentTests(unittest.TestCase):
    def setUp(self):
        output = redirect_stdout(io.StringIO())
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)
        self.registry = ToolRegistry()

    def run_agent(self, client, **kwargs):
        return agent.run_agent("测试任务", client=client, registry=self.registry, **kwargs)

    def test_text_response_and_empty_registry_need_no_tool_configuration(self):
        client = FakeClient(response("你好"))
        self.assertEqual(self.run_agent(client, model="test-model"), "你好")
        request = client.requests[0]
        self.assertEqual(request["model"], "test-model")
        self.assertNotIn("tools", request)
        self.assertNotIn("tool_choice", request)

    def test_multiple_tools_preserve_order_ids_and_results_before_next_request(self):
        executed = []

        @self.registry.register(schema("record"))
        def record(value):
            executed.append(value)
            return value

        client = FakeClient(
            response(calls=[
                tool_call("a", "record", '{"value": 1}'),
                tool_call("b", "record", '{"value": 2}'),
            ]),
            response("完成"),
        )
        self.assertEqual(self.run_agent(client), "完成")
        self.assertEqual(executed, [1, 2])
        history = client.requests[1]["messages"]
        self.assertEqual([item["role"] for item in history], ["system", "user", "assistant", "tool", "tool"])
        self.assertEqual([item["id"] for item in history[2]["tool_calls"]], ["a", "b"])
        self.assertEqual(history[3:], [
            {"role": "tool", "tool_call_id": "a", "content": "1"},
            {"role": "tool", "tool_call_id": "b", "content": "2"},
        ])
        self.assertEqual(client.requests[0]["tools"], self.registry.schemas)

    def test_tool_errors_return_with_matching_ids_and_model_can_correct_arguments(self):
        executed = Mock(return_value="ok")

        @self.registry.register(schema("echo"))
        def echo(text):
            return executed(text)

        @self.registry.register(schema("broken"))
        def broken():
            raise RuntimeError("device unavailable")

        failed = [
            tool_call("bad_json", "echo", "{"),
            tool_call("empty_json", "echo", ""),
            tool_call("array", "echo", "[]"),
            tool_call("null", "echo", "null"),
            tool_call("unknown", "missing"),
            tool_call("missing_arg", "echo"),
            tool_call("exception", "broken"),
        ]
        client = FakeClient(
            response(calls=failed),
            response(calls=[tool_call("fixed", "echo", '{"text": "corrected"}')]),
            response("已修正"),
        )
        self.assertEqual(self.run_agent(client), "已修正")
        errors = client.requests[1]["messages"][3:]
        self.assertEqual([item["tool_call_id"] for item in errors], [item.id for item in failed])
        self.assertTrue(all(item["content"].startswith("[Error]:") for item in errors))
        self.assertEqual(client.requests[2]["messages"][-1]["content"], "ok")
        executed.assert_called_once_with("corrected")

    def test_iteration_limit_stops_repeated_tool_calls(self):
        executed = Mock(return_value="ok")
        self.registry.register(schema("action"))(executed)
        client = FakeClient(*[
            response(calls=[tool_call(str(index), "action")]) for index in range(3)
        ])
        result = self.run_agent(client, max_iterations=2)
        self.assertIn("2 轮内尚未完成", result)
        self.assertEqual(len(client.requests), 2)
        self.assertEqual(executed.call_count, 2)

    def test_failed_model_request_does_not_replay_completed_action(self):
        executed = Mock(return_value="ok")
        self.registry.register(schema("action"))(executed)
        client = FakeClient(
            response(calls=[tool_call("a", "action")]),
            TimeoutError("request timed out"),
        )
        self.assertIn("模型请求失败", self.run_agent(client))
        executed.assert_called_once_with()
        self.assertEqual(len(client.requests), 2)

    def test_truncated_or_filtered_response_does_not_execute_actions(self):
        executed = Mock()
        self.registry.register(schema("action"))(executed)
        for reason in ("length", "content_filter"):
            with self.subTest(reason=reason):
                client = FakeClient(response("partial", [tool_call("a", "action")], reason))
                self.assertTrue(self.run_agent(client).startswith("[Error]:"))
        executed.assert_not_called()

    def test_empty_response_is_reported_as_error(self):
        for result in (SimpleNamespace(choices=[]), response(), response("   ")):
            with self.subTest(response=result):
                self.assertTrue(self.run_agent(FakeClient(result)).startswith("[Error]:"))

    def test_only_internally_created_client_is_closed(self):
        client = MagicMock()
        client.__enter__.return_value = client
        client.chat.completions.create.return_value = response("完成")
        with patch.object(agent, "create_client", return_value=client) as create:
            self.assertEqual(agent.run_agent("测试", registry=self.registry), "完成")
            create.assert_called_once_with()
        client.__exit__.assert_called_once_with(None, None, None)

        client.reset_mock()
        self.assertEqual(self.run_agent(client), "完成")
        client.__exit__.assert_not_called()
        client.close.assert_not_called()

    def test_invalid_user_input_and_limit_fail_before_creating_client(self):
        with patch.object(agent, "create_client") as create:
            for user_input, limit in (("", 5), (" ", 5), ("任务", 0), ("任务", -1), ("任务", True)):
                with self.subTest(input=user_input, limit=limit), self.assertRaises(ValueError):
                    agent.run_agent(user_input, limit)
            create.assert_not_called()

    def test_import_works_without_sdk_or_dotenv(self):
        result = subprocess.run(
            [sys.executable, "-B", "-c", "import sys; sys.modules['openai'] = None; sys.modules['dotenv'] = None; import agent"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
