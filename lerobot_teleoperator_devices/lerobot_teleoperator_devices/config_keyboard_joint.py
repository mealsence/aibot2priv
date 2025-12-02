from dataclasses import dataclass, field

from lerobot.teleoperators import TeleoperatorConfig
from lerobot.teleoperators.keyboard import KeyboardTeleopConfig


@TeleoperatorConfig.register_subclass("keyboard_joint")
@dataclass
class KeyboardJointTeleopConfig(KeyboardTeleopConfig):
    arm_action_keys: list[str] = field(default_factory=lambda: [f"{i}.pos" for i in range(1, 6)])
    gripper_action_key: str = "gripper.pos"

    # The amount by which a joint action changes when a key is pressed.
    action_increment: float = 0.02


@TeleoperatorConfig.register_subclass("keyboard_joint_panda")
@dataclass
class KeyboardJointPandaTeleopConfig(KeyboardTeleopConfig):
    """Keyboard joint teleoperator for 7-DOF robots like Franka Panda."""

    arm_action_keys: list[str] = field(
        default_factory=lambda: [
            "panda_joint1.pos",
            "panda_joint2.pos",
            "panda_joint3.pos",
            "panda_joint4.pos",
            "panda_joint5.pos",
            "panda_joint6.pos",
            "panda_joint7.pos",
        ]
    )
    gripper_action_key: str = "gripper.pos"  # Use generic key for compatibility with ROS2Robot

    # The amount by which a joint action changes when a key is pressed.
    action_increment: float = 0.01  # Smaller increment for better control
