"""
工具定义层：把 MockGo2 的能力转成大模型能识别的 JSON Schema（Tool Calling 格式），
并提供"工具名 -> 真实 Python 函数"的映射表。

description 字段决定大模型会不会选中这个工具，写的时候要把用户可能的说法都覆盖到。
"""

from mock_go2 import MockGo2

go2 = MockGo2()

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "move_forward",
            "description": "控制机器狗向前直行。当用户要求前进、走向某个方向、向前移动时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "speed": {
                        "type": "number",
                        "description": "前进速度，单位米每秒（m/s），建议 0.1 ~ 1.5。",
                    },
                    "distance": {
                        "type": "number",
                        "description": "前进距离，单位米（m），建议 0.1 ~ 10.0。",
                    },
                },
                "required": ["speed", "distance"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "turn",
            "description": "控制机器狗原地转向。当用户要求左转、右转、改变朝向时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["left", "right"],
                        "description": "转向方向：left 表示左转，right 表示右转。",
                    },
                    "angle": {
                        "type": "number",
                        "description": "转向角度，单位度（°），建议 0 ~ 360。",
                    },
                },
                "required": ["direction", "angle"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_battery",
            "description": "查询机器狗当前剩余电量。当用户询问电量、续航，或执行任务前需要确认电力时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_photo",
            "description": "让机器狗拍照。当用户说看、看看、看一眼、观察、拍照、拍张照片、前方有什么、画面时，调用本工具。这是唯一能获取视觉信息的工具。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

TOOL_MAP = {
    "move_forward": go2.move_forward,
    "turn": go2.turn,
    "get_battery": go2.get_battery,
    "take_photo": go2.take_photo,
}
