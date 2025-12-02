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

from .config_spacemouse_ee_panda import SpaceMouseEEPandaTeleopConfig
from .processors.delta_to_joints import set_active_keyboard_ee_config


class SpaceMouseEEPandaTeleop(Teleoperator):
    """SpaceMouse teleoperator that outputs Cartesian position deltas for Panda IK control."""

    config_class = SpaceMouseEEPandaTeleopConfig
    name = "spacemouse_ee_panda"

    def __init__(self, config: SpaceMouseEEPandaTeleopConfig):
        super().__init__(config)
        self.config = config
        set_active_keyboard_ee_config(config)

        # ROS2 node and subscriber lifecycle
        self._ros_node: Node | None = None
        self._joy_subscriber = None
        self._executor_thread: threading.Thread | None = None

        # Joy message handling
        self._latest_joy: Joy | None = None
        self._joy_lock = threading.Lock()

        # Gripper action (0 = close, 1 = neutral, 2 = open)
        self._gripper_action = 1.0
        self._gripper_button_pressed = False

    @property
    def action_features(self) -> dict:
        if self.config.use_gripper:
            return {
                "dtype": "float32",
                "shape": (4,),
                "names": {"delta_x": 0, "delta_y": 1, "delta_z": 2, "gripper": 3},
            }
        else:
            return {
                "dtype": "float32",
                "shape": (3,),
                "names": {"delta_x": 0, "delta_y": 1, "delta_z": 2},
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
        del calibrate  # Unused
        if self.is_connected:
            raise DeviceAlreadyConnectedError(
                "SpaceMouseEE teleop is already connected. Do not run `connect()` twice."
            )

        if not rclpy.ok():
            rclpy.init()

        self._ros_node = Node("spacemouse_ee_panda_teleop_node")
        self._joy_subscriber = self._ros_node.create_subscription(
            Joy,
            self.config.joy_topic,
            self._joy_callback,
            10,
        )

        self._executor_thread = threading.Thread(target=self._run_executor, daemon=True)
        self._executor_thread.start()

        # Allow time for the subscriber to start receiving messages
        time.sleep(0.5)

    def _joy_callback(self, msg: Joy) -> None:
        with self._joy_lock:
            self._latest_joy = msg

            if not self.config.use_gripper:
                return

            if len(msg.buttons) >= 2:
                # Button 0: Close gripper
                if msg.buttons[0] == 1 and not self._gripper_button_pressed:
                    self._gripper_action = 0.0
                    self._gripper_button_pressed = True
                # Button 1: Open gripper
                elif msg.buttons[1] == 1 and not self._gripper_button_pressed:
                    self._gripper_action = 2.0
                    self._gripper_button_pressed = True
                elif msg.buttons[0] == 0 and msg.buttons[1] == 0:
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
                "SpaceMouseEE teleop is not connected. You need to run `connect()` before `get_action()`."
            )

        with self._joy_lock:
            delta_x = 0.0
            delta_y = 0.0
            delta_z = 0.0
            gripper_action = self._gripper_action

            if self._latest_joy is not None and len(self._latest_joy.axes) >= 3:
                axes = list(self._latest_joy.axes) + [0.0] * (6 - len(self._latest_joy.axes))
                orig_x, orig_y, orig_z = axes[:3]

                # Apply frame mapping consistent with velocity-based spacemouse teleop
                mapped_x = -orig_y if self.config.invert_y else orig_y
                mapped_y = -orig_x if self.config.invert_x else orig_x
                mapped_z = orig_z if not self.config.invert_z else -orig_z

                def apply_deadzone(value: float, threshold: float) -> float:
                    return 0.0 if abs(value) < threshold else value

                mapped_x = apply_deadzone(mapped_x, self.config.dead_zone)
                mapped_y = apply_deadzone(mapped_y, self.config.dead_zone)
                mapped_z = apply_deadzone(mapped_z, self.config.dead_zone)

                delta_x = mapped_x * self.config.linear_step_m
                delta_y = mapped_y * self.config.linear_step_m
                delta_z = mapped_z * self.config.linear_step_m

        action = {
            "delta_x": float(delta_x),
            "delta_y": float(delta_y),
            "delta_z": float(delta_z),
        }

        if self.config.use_gripper:
            action["gripper"] = float(gripper_action)
            self._gripper_action = 1.0

        return action

    def send_feedback(self, feedback: dict[str, Any]) -> None:
        del feedback  # Not supported

    def disconnect(self) -> None:
        if not self.is_connected and self._ros_node is None:
            return

        if self._joy_subscriber is not None:
            try:
                self._joy_subscriber.destroy()
            except Exception:
                pass
            self._joy_subscriber = None

        if self._ros_node is not None:
            try:
                self._ros_node.destroy_node()
            except Exception:
                pass
            self._ros_node = None

        if self._executor_thread is not None:
            self._executor_thread.join(timeout=1.0)
            self._executor_thread = None

    def calibrate(self) -> None:
        return

    def configure(self) -> None:
        return

