from __future__ import annotations

from dataclasses import dataclass

from lerobot.teleoperators.config import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("spacemouse_cartesian_vel_panda")
@dataclass
class SpaceMouseCartesianVelTeleopConfig(TeleoperatorConfig):
    """Configuration for SpaceMouse Cartesian velocity teleop on real Franka Panda.

    Mirrors spacemouse_cartesian_vel.py but as a LeRobot Teleoperator.
    Outputs {vx, vy, vz, gripper.pos} directly — no IK required.
    """

    # ROS topic for SpaceMouse joy input (same as spacenav_node default)
    joy_topic: str = "/spacenav/joy"

    # Scaling factors (matching spacemouse_cartesian_vel.py defaults)
    linear_scale: float = 0.05   # m/s per unit SpaceMouse input

    # Deadzone applied per-axis before scaling (matching spacemouse_cartesian_vel.py)
    dead_zone: float = 0.1

    # Axis inversion (match the working spacemouse_cartesian_vel.py frame mapping)
    invert_x: bool = True   # SpaceMouse x → robot y (inverted)
    invert_y: bool = True   # SpaceMouse y → robot x (inverted)
    invert_z: bool = False  # SpaceMouse z → robot z

    # Gripper control via buttons
    # Button 0 (left): close gripper → gripper.pos = 1.0 (normalized closed)
    # Button 1 (right): open gripper  → gripper.pos = 0.0 (normalized open)
    use_gripper: bool = True
