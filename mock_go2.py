"""
MockGo2 —— 机器狗能力的模拟层。

没有真机的阶段，用这个类替代真实机器狗，只打印日志、不做真实控制。
方法签名对齐 unitree_sdk2_python，将来换成真机实现时，Agent 层无需改动。
"""

import time


class MockGo2:
    """模拟宇树 Go2 机器狗，所有动作仅打印日志。"""

    def __init__(self, battery: int = 85) -> None:
        self.battery = battery
        self.position = "原点"
        self._step = 0

    def move_forward(self, speed: float, distance: float) -> str:
        """控制机器狗向前直行。

        Args:
            speed: 前进速度，单位米每秒（m/s），建议范围 0.1 ~ 1.5。
            distance: 前进距离，单位米（m），建议范围 0.1 ~ 10.0。

        Returns:
            一段描述本次移动结果的文本。
        """
        time.sleep(min(distance / max(speed, 0.1), 2.0))
        self.battery -= int(distance * 0.5)
        self.position = f"前方 {distance} 米处"
        print(f"[MockGo2] 向前移动 {distance} 米，速度 {speed} m/s，当前电量 {self.battery}%")
        return f"已向前移动 {distance} 米，速度 {speed} m/s，当前位于{self.position}。"

    def turn(self, direction: str, angle: float) -> str:
        """控制机器狗原地转向。

        Args:
            direction: 转向方向，只能是 "left"（左）或 "right"（右）。
            angle: 转向角度，单位度（°），建议范围 0 ~ 360。

        Returns:
            一段描述本次转向结果的文本。
        """
        dir_cn = {"left": "左", "right": "右"}.get(direction, direction)
        time.sleep(0.5)
        self.battery -= 1
        print(f"[MockGo2] 向{dir_cn}转 {angle} 度，当前电量 {self.battery}%")
        return f"已向{dir_cn}转 {angle} 度。"

    def get_battery(self) -> str:
        """查询机器狗当前剩余电量。

        在用户询问电量、或需要判断能否继续执行任务前调用。

        Returns:
            当前电量的文本描述，例如 "当前电量 85%"。
        """
        print(f"[MockGo2] 查询电量：{self.battery}%")
        return f"当前电量 {self.battery}%。"

    def take_photo(self) -> str:
        """让机器狗用自带相机拍一张照片并保存。

        在用户要求"看看前面有什么""拍照"时调用。

        Returns:
            照片文件名及其保存位置的描述。
        """
        self._step += 1
        filename = f"go2_photo_{self._step:03d}.jpg"
        time.sleep(0.5)
        self.battery -= 2
        print(f"[MockGo2] 拍照并保存为 {filename}，当前电量 {self.battery}%")
        return f"已拍摄照片，保存为 {filename}（模拟文件，未真正写入磁盘）。"
