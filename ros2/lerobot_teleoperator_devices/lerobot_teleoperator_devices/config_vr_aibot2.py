from __future__ import annotations

from dataclasses import dataclass

from lerobot.teleoperators.config import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("vr_aibot2")
@dataclass
class VRAibot2TeleopConfig(TeleoperatorConfig):
    """Configuration for AIBOT2 VR target-pose recording.

    The VR/internal robot driver publishes both target poses and executes them.
    This teleoperator only subscribes to that topic and exposes the latest target
    as the LeRobot action.
    """

    target_topic: str = "/control_poses_target"
    message_type: str = "geometry_msgs/msg/PoseArray"
    # /control_poses_target is PoseArray:
    #   poses[0] = left hand target
    #   poses[1] = right hand target
    # Additional poses, such as headset/body references, are ignored by default.
    left_pose_index: int = 0
    right_pose_index: int = 1
    hand_state_topic: str = "/hand_states"
    hand_state_left_index: int = 0
    hand_state_right_index: int = 1
    hand_state_open_value: float = 800.0
    hand_state_close_value: float = 0.0
    left_gripper_default: float = 0.0
    right_gripper_default: float = 0.0
    initial_message_timeout_s: float = 5.0
    require_initial_target: bool = True
