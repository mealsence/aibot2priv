from __future__ import annotations

import threading
import time
from typing import Any

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import Joy

from lerobot.teleoperators import Teleoperator
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from .config_spacemouse_cartesian_vel_panda import SpaceMouseCartesianVelTeleopConfig


def _apply_deadzone(value: float, threshold: float) -> float:
    """Scale value so output starts from 0 at the deadzone boundary."""
    if abs(value) < threshold:
        return 0.0
    sign = 1.0 if value > 0.0 else -1.0
    return sign * (abs(value) - threshold) / (1.0 - threshold)


class SpaceMouseCartesianVelTeleop(Teleoperator):
    """SpaceMouse teleoperator that outputs Cartesian velocity commands.

    Mirrors spacemouse_cartesian_vel.py as a LeRobot Teleoperator.
    Returns {vx, vy, vz, gripper.pos} — no IK, direct velocity passthrough.

    Button mapping:
        Button 0 (left):  close gripper  → gripper.pos = 1.0
        Button 1 (right): open gripper   → gripper.pos = 0.0
    """

    config_class = SpaceMouseCartesianVelTeleopConfig
    name = "spacemouse_cartesian_vel_panda"

    def __init__(self, config: SpaceMouseCartesianVelTeleopConfig):
        super().__init__(config)
        self.config = config

        self._ros_node: Node | None = None
        self._joy_sub = None
        self._executor_thread: threading.Thread | None = None

        self._latest_joy: Joy | None = None
        self._joy_lock = threading.Lock()

        # Gripper state: 0.0 = open, 1.0 = closed (normalized convention)
        self._gripper_pos: float = 0.0
        self._gripper_button_pressed: bool = False

    @property
    def action_features(self) -> dict:
        if self.config.use_gripper:
            return {
                "dtype": "float32",
                "shape": (4,),
                "names": {"x.vel": 0, "y.vel": 1, "z.vel": 2, "gripper.pos": 3},
            }
        return {
            "dtype": "float32",
            "shape": (3,),
            "names": {"x.vel": 0, "y.vel": 1, "z.vel": 2},
        }

    @property
    def feedback_features(self) -> dict:
        return {}

    @property
    def is_connected(self) -> bool:
        return self._ros_node is not None and rclpy.ok()

    @property
    def is_calibrated(self) -> bool:
        return True

    def connect(self, calibrate: bool = True) -> None:
        del calibrate
        if self.is_connected:
            raise DeviceAlreadyConnectedError(
                "SpaceMouseCartesianVel teleop is already connected."
            )

        if not rclpy.ok():
            rclpy.init()

        self._ros_node = Node("spacemouse_cartesian_vel_teleop_node")
        self._joy_sub = self._ros_node.create_subscription(
            Joy,
            self.config.joy_topic,
            self._joy_callback,
            10,
        )

        self._executor_thread = threading.Thread(target=self._run_executor, daemon=True)
        self._executor_thread.start()

        time.sleep(0.5)

    def _joy_callback(self, msg: Joy) -> None:
        with self._joy_lock:
            self._latest_joy = msg

            if not self.config.use_gripper or len(msg.buttons) < 2:
                return

            btn0 = bool(msg.buttons[0])
            btn1 = bool(msg.buttons[1])

            if (btn0 or btn1) and not self._gripper_button_pressed:
                if btn0:
                    self._gripper_pos = 1.0  # close
                else:
                    self._gripper_pos = 0.0  # open
                self._gripper_button_pressed = True
            elif not btn0 and not btn1:
                self._gripper_button_pressed = False

    def _run_executor(self) -> None:
        executor = SingleThreadedExecutor()
        executor.add_node(self._ros_node)
        try:
            executor.spin()
        except Exception:
            pass

    def get_action(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(
                "SpaceMouseCartesianVel teleop is not connected."
            )

        with self._joy_lock:
            vx = vy = vz = 0.0

            if self._latest_joy is not None and len(self._latest_joy.axes) >= 3:
                axes = list(self._latest_joy.axes) + [0.0] * (6 - len(self._latest_joy.axes))
                raw_x, raw_y, raw_z = axes[:3]

                # Frame mapping matching spacemouse_cartesian_vel.py:
                #   SpaceMouse x → robot y (invert_y)
                #   SpaceMouse y → robot x (invert_x)
                #   SpaceMouse z → robot z
                mapped_x = (-raw_y if self.config.invert_y else raw_y)
                mapped_y = (-raw_x if self.config.invert_x else raw_x)
                mapped_z = (-raw_z if self.config.invert_z else raw_z)

                mapped_x = _apply_deadzone(mapped_x, self.config.dead_zone)
                mapped_y = _apply_deadzone(mapped_y, self.config.dead_zone)
                mapped_z = _apply_deadzone(mapped_z, self.config.dead_zone)

                vx = mapped_x * self.config.linear_scale
                vy = mapped_y * self.config.linear_scale
                vz = mapped_z * self.config.linear_scale

            gripper_pos = self._gripper_pos

        action: dict[str, Any] = {"x.vel": float(vx), "y.vel": float(vy), "z.vel": float(vz)}
        if self.config.use_gripper:
            action["gripper.pos"] = float(gripper_pos)
        return action

    def send_feedback(self, feedback: dict[str, Any]) -> None:
        del feedback

    def calibrate(self) -> None:
        return

    def configure(self) -> None:
        return

    def disconnect(self) -> None:
        if self._joy_sub is not None:
            try:
                self._joy_sub.destroy()
            except Exception:
                pass
            self._joy_sub = None

        if self._ros_node is not None:
            try:
                self._ros_node.destroy_node()
            except Exception:
                pass
            self._ros_node = None

        if self._executor_thread is not None:
            self._executor_thread.join(timeout=1.0)
            self._executor_thread = None
