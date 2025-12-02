from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from lerobot.teleoperators.keyboard.configuration_keyboard import KeyboardEndEffectorTeleopConfig


def _default_urdf_path() -> str:
    base_dir = Path(__file__).resolve().parents[4]
    urdf_path = base_dir / "isaac_franka_moveit_perception" / "src" / "panda_description" / "urdf" / "panda.urdf"
    return str(urdf_path)


@KeyboardEndEffectorTeleopConfig.register_subclass("spacemouse_ee_panda")
@dataclass
class SpaceMouseEEPandaTeleopConfig(KeyboardEndEffectorTeleopConfig):
    """Configuration for SpaceMouse-based Panda end-effector control."""

    # IK configuration (same defaults as keyboard_ee_panda)
    linear_step_m: float = 0.01
    gripper_step: float = 0.0025
    position_weight: float = 1.0
    orientation_weight: float = 0.05
    joint_names: Sequence[str] = field(
        default_factory=lambda: (
            "panda_joint1",
            "panda_joint2",
            "panda_joint3",
            "panda_joint4",
            "panda_joint5",
            "panda_joint6",
            "panda_joint7",
        )
    )
    gripper_joint_name: str = "panda_finger_joint1"
    urdf_path: str = field(default_factory=_default_urdf_path)
    ee_frame: str = "panda_hand"
    workspace_min: Sequence[float] = field(default_factory=lambda: (-0.6, -0.6, 0.0))
    workspace_max: Sequence[float] = field(default_factory=lambda: (0.6, 0.6, 0.8))
    gripper_limits: Sequence[float] = field(default_factory=lambda: (0.0, 0.04))

    # SpaceMouse parameters
    joy_topic: str = "/spacenav/joy"
    invert_x: bool = True
    invert_y: bool = True
    invert_z: bool = False
    dead_zone: float = 0.05




