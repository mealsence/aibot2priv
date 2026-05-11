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
    gripper_joint_state_topic: str = "/joint_states"
    left_gripper_joint_name: str = "2FEG_l_Joint1"
    right_gripper_joint_name: str = "2FEG_r_Joint1"
    gripper_open_value: float = 0.8
    gripper_close_value: float = 0.0
    left_gripper_default: float = 0.0
    right_gripper_default: float = 0.0
    initial_message_timeout_s: float = 5.0
    require_initial_target: bool = True
