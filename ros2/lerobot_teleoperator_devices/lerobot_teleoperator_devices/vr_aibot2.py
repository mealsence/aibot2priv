from __future__ import annotations

import logging
import threading
import time
from typing import Any

import rclpy
from geometry_msgs.msg import Pose, PoseArray, PoseStamped
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rosidl_runtime_py.utilities import get_message
from std_msgs.msg import Int64MultiArray

from lerobot.teleoperators import Teleoperator
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from .config_vr_aibot2 import VRAibot2TeleopConfig

logger = logging.getLogger(__name__)


def _identity_action(left_gripper: float, right_gripper: float) -> dict[str, float]:
    return {
        "left_arm.x": 0.0,
        "left_arm.y": 0.0,
        "left_arm.z": 0.0,
        "left_arm.qx": 0.0,
        "left_arm.qy": 0.0,
        "left_arm.qz": 0.0,
        "left_arm.qw": 1.0,
        "right_arm.x": 0.0,
        "right_arm.y": 0.0,
        "right_arm.z": 0.0,
        "right_arm.qx": 0.0,
        "right_arm.qy": 0.0,
        "right_arm.qz": 0.0,
        "right_arm.qw": 1.0,
        "left_gripper.pos": float(left_gripper),
        "right_gripper.pos": float(right_gripper),
    }


def _pose_to_action(prefix: str, pose: Pose) -> dict[str, float]:
    return {
        f"{prefix}.x": float(pose.position.x),
        f"{prefix}.y": float(pose.position.y),
        f"{prefix}.z": float(pose.position.z),
        f"{prefix}.qx": float(pose.orientation.x),
        f"{prefix}.qy": float(pose.orientation.y),
        f"{prefix}.qz": float(pose.orientation.z),
        f"{prefix}.qw": float(pose.orientation.w),
    }


class VRAibot2Teleop(Teleoperator):
    """Subscribe to VR-published AIBOT2 target poses and expose them as actions."""

    config_class = VRAibot2TeleopConfig
    name = "vr_aibot2"

    def __init__(self, config: VRAibot2TeleopConfig):
        super().__init__(config)
        self.config = config

        self._ros_node: Node | None = None
        self._target_subscription = None
        self._hand_state_subscription = None
        self._executor: SingleThreadedExecutor | None = None
        self._executor_thread: threading.Thread | None = None

        self._action_lock = threading.Lock()
        self._latest_action = _identity_action(
            config.left_gripper_default,
            config.right_gripper_default,
        )
        self._left_gripper = float(config.left_gripper_default)
        self._right_gripper = float(config.right_gripper_default)
        self._has_message = False

    @property
    def action_features(self) -> dict[str, type]:
        return {
            "left_arm.x": float,
            "left_arm.y": float,
            "left_arm.z": float,
            "left_arm.qx": float,
            "left_arm.qy": float,
            "left_arm.qz": float,
            "left_arm.qw": float,
            "right_arm.x": float,
            "right_arm.y": float,
            "right_arm.z": float,
            "right_arm.qx": float,
            "right_arm.qy": float,
            "right_arm.qz": float,
            "right_arm.qw": float,
            "left_gripper.pos": float,
            "right_gripper.pos": float,
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
            raise DeviceAlreadyConnectedError("VRAibot2 teleop is already connected.")

        if not rclpy.ok():
            rclpy.init()

        msg_type = get_message(self.config.message_type)
        self._ros_node = Node("vr_aibot2_teleop_node")
        self._target_subscription = self._ros_node.create_subscription(
            msg_type,
            self.config.target_topic,
            self._target_callback,
            10,
        )
        self._hand_state_subscription = self._ros_node.create_subscription(
            Int64MultiArray,
            self.config.hand_state_topic,
            self._hand_state_callback,
            10,
        )

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._ros_node)
        self._executor_thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._executor_thread.start()

        deadline = time.monotonic() + self.config.initial_message_timeout_s
        while not self._has_message and time.monotonic() < deadline:
            time.sleep(0.05)

        if not self._has_message:
            message = (
                f"No VR target message received on {self.config.target_topic} within "
                f"{self.config.initial_message_timeout_s:.1f}s."
            )
            if self.config.require_initial_target:
                self.disconnect()
                raise TimeoutError(
                    f"{message} Start the VR publisher before recording, or set "
                    "--teleop.require_initial_target=false to allow identity pose startup."
                )
            logger.warning("%s Using identity pose until one arrives.", message)

    def _target_callback(self, msg: Any) -> None:
        try:
            left_pose, right_pose = self._extract_poses(msg)
        except Exception as exc:
            logger.warning("Ignoring malformed VR target message on %s: %s", self.config.target_topic, exc)
            return

        with self._action_lock:
            action = _identity_action(self._left_gripper, self._right_gripper)
            action.update(_pose_to_action("left_arm", left_pose))
            action.update(_pose_to_action("right_arm", right_pose))
            self._latest_action = action
            self._has_message = True

    def _hand_state_callback(self, msg: Int64MultiArray) -> None:
        try:
            left_raw = float(msg.data[self.config.hand_state_left_index])
            right_raw = float(msg.data[self.config.hand_state_right_index])
            left_gripper = self._normalize_hand_gripper(left_raw)
            right_gripper = self._normalize_hand_gripper(right_raw)
        except Exception as exc:
            logger.warning("Ignoring malformed hand states on %s: %s", self.config.hand_state_topic, exc)
            return

        with self._action_lock:
            self._left_gripper = left_gripper
            self._right_gripper = right_gripper
            self._latest_action["left_gripper.pos"] = left_gripper
            self._latest_action["right_gripper.pos"] = right_gripper

    def _normalize_hand_gripper(self, raw_value: float) -> float:
        open_value = float(self.config.hand_state_open_value)
        close_value = float(self.config.hand_state_close_value)
        if open_value == close_value:
            return 0.0
        normalized = (open_value - float(raw_value)) / (open_value - close_value)
        return float(max(0.0, min(1.0, normalized)))

    def _extract_poses(self, msg: Any) -> tuple[Pose, Pose]:
        if isinstance(msg, PoseArray) or hasattr(msg, "poses"):
            poses = msg.poses
            if len(poses) <= max(self.config.left_pose_index, self.config.right_pose_index):
                raise ValueError(
                    f"PoseArray has {len(poses)} poses; expected at least 2 poses with "
                    "poses[0] as left hand and poses[1] as right hand"
                )
            return poses[self.config.left_pose_index], poses[self.config.right_pose_index]

        if isinstance(msg, PoseStamped):
            return msg.pose, msg.pose

        if hasattr(msg, "left_pose") and hasattr(msg, "right_pose"):
            return self._unwrap_pose(msg.left_pose), self._unwrap_pose(msg.right_pose)

        if hasattr(msg, "left") and hasattr(msg, "right"):
            return self._unwrap_pose(msg.left), self._unwrap_pose(msg.right)

        raise TypeError(f"Unsupported message type: {type(msg).__name__}")

    @staticmethod
    def _unwrap_pose(value: Any) -> Pose:
        if isinstance(value, PoseStamped):
            return value.pose
        if isinstance(value, Pose):
            return value
        if hasattr(value, "pose"):
            return value.pose
        raise TypeError(f"Expected Pose or PoseStamped-like value, got {type(value).__name__}")

    def get_action(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError("VRAibot2 teleop is not connected.")

        with self._action_lock:
            return dict(self._latest_action)

    def send_feedback(self, feedback: dict[str, Any]) -> None:
        del feedback

    def calibrate(self) -> None:
        return

    def configure(self) -> None:
        return

    def disconnect(self) -> None:
        if self._target_subscription is not None:
            try:
                self._target_subscription.destroy()
            except Exception:
                pass
            self._target_subscription = None

        if self._hand_state_subscription is not None:
            try:
                self._hand_state_subscription.destroy()
            except Exception:
                pass
            self._hand_state_subscription = None

        if self._executor is not None:
            try:
                self._executor.shutdown()
            except Exception:
                pass
            self._executor = None

        if self._executor_thread is not None:
            self._executor_thread.join(timeout=1.0)
            self._executor_thread = None

        if self._ros_node is not None:
            try:
                self._ros_node.destroy_node()
            except Exception:
                pass
            self._ros_node = None
