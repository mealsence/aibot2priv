# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from dataclasses import dataclass, field
from enum import Enum
import os

from lerobot.cameras import CameraConfig
from lerobot.robots import RobotConfig


class ActionType(Enum):
    CARTESIAN_VELOCITY = "cartesian_velocity"
    JOINT_POSITION = "joint_position"
    JOINT_TRAJECTORY = "joint_trajectory"


class GripperActionType(Enum):
    TRAJECTORY = "trajectory"  # Use JointTrajectoryController for gripper
    ACTION = "action"  # Use GripperActionClient


@dataclass
class ROS2InterfaceConfig:
    # Namespace used by ros2_control / MoveIt2 nodes
    namespace: str = ""

    arm_joint_names: list[str] = field(
        default_factory=lambda: [
            "joint_1",
            "joint_2",
            "joint_3",
            "joint_4",
            "joint_5",
            "joint_6",
        ]
    )
    gripper_joint_name: str = "gripper_joint"

    # Base link name for computing end effector pose / velocity
    # Only applicable for cartesian control
    base_link: str = "base_link"

    # Only applicable if velocity control is used.
    max_linear_velocity: float = 0.10
    max_angular_velocity: float = 0.25  # rad/s

    # Only applicable if position control is used.
    min_joint_positions: list[float] | None = None
    max_joint_positions: list[float] | None = None

    gripper_open_position: float = 0.0
    gripper_close_position: float = 1.0

    gripper_action_type: GripperActionType = GripperActionType.TRAJECTORY

    # Controller names for arm and gripper
    # For Panda: use "panda_arm_controller" and "panda_hand_controller"
    # For other robots: typically "arm_controller" and "gripper_controller"
    arm_controller_name: str = "arm_controller"
    position_controller_name: str = "position_controller"
    gripper_controller_name: str = "gripper_controller"


@dataclass
class ROS2Config(RobotConfig):
    # Action type for controlling the robot. Can be 'cartesian_velocity' or 'joint_position'.
    action_type: ActionType = ActionType.JOINT_POSITION

    # `max_relative_target` limits the magnitude of the relative positional target vector for safety purposes.
    # Set this to a positive scalar to have the same value for all motors, or a list that is the same length as
    # the number of motors in your follower arms.
    max_relative_target: int | None = None

    # cameras
    cameras: dict[str, CameraConfig] = field(default_factory=dict)

    # ROS2 interface configuration
    ros2_interface: ROS2InterfaceConfig = field(default_factory=ROS2InterfaceConfig)


@RobotConfig.register_subclass("annin_ar4_mk1")
@dataclass
class AnninAR4Config(ROS2Config):
    """Annin Robotics AR4 robot configuration - extends ROS2Config with
    AR4-specific settings
    """

    action_type: ActionType = ActionType.CARTESIAN_VELOCITY

    ros2_interface: ROS2InterfaceConfig = field(
        default_factory=lambda: ROS2InterfaceConfig(
            gripper_joint_name="gripper_jaw1_joint",
            base_link="base_link",
            min_joint_positions=[-2.9671, -0.7330, -1.5533, -2.8798, -1.8326, -2.7053],
            max_joint_positions=[2.9671, 1.5708, 0.9076, 2.8798, 1.8326, 2.7053],
            gripper_open_position=0.014,
            gripper_close_position=0.0,
            gripper_action_type=GripperActionType.ACTION,
        ),
    )


@RobotConfig.register_subclass("so101_ros")
@dataclass
class SO101ROSConfig(ROS2Config):
    """Configuration for the ROS 2 version of SO101: https://github.com/Pavankv92/lerobot_ws."""

    # Use JOINT_POSITION for compatibility with ROS2 Humble (no MoveIt Servo required)
    # Change to CARTESIAN_VELOCITY if you have MoveIt Servo configured
    action_type: ActionType = ActionType.JOINT_POSITION

    ros2_interface: ROS2InterfaceConfig = field(
        default_factory=lambda: ROS2InterfaceConfig(
            arm_joint_names=["1", "2", "3", "4", "5"],
            gripper_joint_name="6",
            base_link="base",
            min_joint_positions=[-1.91986, -1.74533, -1.74533, -1.65806, -2.79253],
            max_joint_positions=[1.91986, 1.74533, 1.5708, 1.65806, 2.79253],
            gripper_open_position=1.74533,
            gripper_close_position=0.0,
        ),
    )


@RobotConfig.register_subclass("panda_ros")
@dataclass
class PandaROSConfig(ROS2Config):
    """Configuration for Franka Emika Panda robot with Isaac Sim / MoveIt2."""

    # Use JOINT_TRAJECTORY for MoveIt integration
    # Can also use CARTESIAN_VELOCITY with MoveIt Servo
    action_type: ActionType = ActionType.JOINT_TRAJECTORY

    ros2_interface: ROS2InterfaceConfig = field(
        default_factory=lambda: ROS2InterfaceConfig(
            arm_joint_names=[
                "panda_joint1",
                "panda_joint2",
                "panda_joint3",
                "panda_joint4",
                "panda_joint5",
                "panda_joint6",
                "panda_joint7",
            ],
            gripper_joint_name="panda_finger_joint1",
            base_link="panda_link0",
            min_joint_positions=[-2.9671, -1.8326, -2.9671, -3.1416, -2.9671, -0.0873, -2.9671],
            max_joint_positions=[2.9671, 1.8326, 2.9671, 0.0873, 2.9671, 3.8223, 2.9671],
            gripper_open_position=0.04,
            gripper_close_position=0.0,
            gripper_action_type=GripperActionType.ACTION,
            arm_controller_name="panda_arm_controller",
            gripper_controller_name="panda_hand_controller",
        ),
    )


@RobotConfig.register_subclass("panda_ros_servo")
@dataclass
class PandaROSServoConfig(PandaROSConfig):
    """Configuration for Franka Emika Panda robot with MoveIt Servo (Cartesian velocity control).

    This config is optimized for SpaceMouse teleoperation and other Cartesian velocity control use cases.
    Uses MoveIt Servo for real-time end-effector velocity control.
    """

    action_type: ActionType = ActionType.CARTESIAN_VELOCITY

    ros2_interface: ROS2InterfaceConfig = field(
        default_factory=lambda: ROS2InterfaceConfig(
            arm_joint_names=[
                "panda_joint1",
                "panda_joint2",
                "panda_joint3",
                "panda_joint4",
                "panda_joint5",
                "panda_joint6",
                "panda_joint7",
            ],
            gripper_joint_name="panda_finger_joint1",
            base_link="panda_link0",
            min_joint_positions=[-2.9671, -1.8326, -2.9671, -3.1416, -2.9671, -0.0873, -2.9671],
            max_joint_positions=[2.9671, 1.8326, 2.9671, 0.0873, 2.9671, 3.8223, 2.9671],
            gripper_open_position=0.04,
            gripper_close_position=0.0,
            gripper_action_type=GripperActionType.ACTION,
            arm_controller_name="panda_arm_controller",
            gripper_controller_name="panda_hand_controller",
            # Increased max velocities for smoother SpaceMouse control
            max_linear_velocity=0.4,  # m/s
            max_angular_velocity=0.8,  # rad/s
        ),
    )


def _get_isaac_camera_config() -> dict[str, CameraConfig]:
    """Get camera configuration from environment variables or use defaults for Isaac Sim.

    Default resolution is 640×480 (VGA), which is the standard used across LeRobot datasets
    like ALOHA, Reachy2, and LeKiwi. This provides a good balance between image quality
    and dataset size, and is compatible with all policy types.
    """
    try:
        from .ros2_camera import ROS2CameraConfig
        from lerobot.cameras.configs import ColorMode

        camera_topic = os.getenv("LEROBOT_CAMERA_TOPIC", "/rgb/camera_1")
        camera_width = int(os.getenv("LEROBOT_CAMERA_WIDTH", "640"))
        camera_height = int(os.getenv("LEROBOT_CAMERA_HEIGHT", "480"))
        camera_fps = int(os.getenv("LEROBOT_CAMERA_FPS", "30"))

        return {
            "camera_1": ROS2CameraConfig(
                topic=camera_topic,
                width=camera_width,
                height=camera_height,
                fps=camera_fps,
                color_mode=ColorMode.RGB,
            )
        }
    except ImportError:
        # ROS2Camera not available, return empty dict
        return {}


@RobotConfig.register_subclass("panda_ros_isaac")
@dataclass
class PandaROSIsaacConfig(PandaROSConfig):
    """Configuration for Franka Emika Panda robot with Isaac Sim and camera support.

    This config automatically includes ROS2 camera configuration for Isaac Sim.
    Default resolution is 640×480 (VGA), matching standard LeRobot datasets.

    Camera settings can be customized via environment variables:
    - LEROBOT_CAMERA_TOPIC (default: /rgb/camera_1)
    - LEROBOT_CAMERA_WIDTH (default: 640)
    - LEROBOT_CAMERA_HEIGHT (default: 480)
    - LEROBOT_CAMERA_FPS (default: 30)

    Example:
        lerobot-record --robot.type=panda_ros_isaac --robot.id=my_panda ...
    """

    cameras: dict[str, CameraConfig] = field(default_factory=_get_isaac_camera_config)


@RobotConfig.register_subclass("panda_ros_isaac_fast")
@dataclass
class PandaROSIsaacFastConfig(PandaROSIsaacConfig):
    """Fast configuration for Franka Emika Panda with direct position control.

    This config uses JOINT_POSITION action type for ultra-low latency control
    (~15-20ms vs ~120ms with trajectory control). Ideal for responsive teleoperation
    with SpaceMouse or other input devices.

    Uses JointGroupPositionController instead of JointTrajectoryController:
    - No trajectory interpolation (instant command execution)
    - 6-8x faster response time
    - Slightly jerkier motion (no smoothing)

    Includes camera support for Isaac Sim (640×480 VGA, matching LeRobot datasets).

    Example:
        lerobot-record --robot.type=panda_ros_isaac_fast --robot.id=my_panda ...
    """

    action_type: ActionType = ActionType.JOINT_POSITION

    ros2_interface: ROS2InterfaceConfig = field(
        default_factory=lambda: ROS2InterfaceConfig(
            arm_joint_names=[
                "panda_joint1",
                "panda_joint2",
                "panda_joint3",
                "panda_joint4",
                "panda_joint5",
                "panda_joint6",
                "panda_joint7",
            ],
            gripper_joint_name="panda_finger_joint1",
            base_link="panda_link0",
            min_joint_positions=[-2.9671, -1.8326, -2.9671, -3.1416, -2.9671, -0.0873, -2.9671],
            max_joint_positions=[2.9671, 1.8326, 2.9671, 0.0873, 2.9671, 3.8223, 2.9671],
            gripper_open_position=0.04,
            gripper_close_position=0.0,
            gripper_action_type=GripperActionType.ACTION,
            position_controller_name="panda_position_controller",
            gripper_controller_name="panda_hand_controller",
            max_linear_velocity=0.4,
            max_angular_velocity=0.8,
        ),
    )


@RobotConfig.register_subclass("panda_ros_servo_isaac")
@dataclass
class PandaROSServoIsaacConfig(PandaROSServoConfig):
    """Configuration for Franka Emika Panda with MoveIt Servo and Isaac Sim camera support.

    Combines Cartesian velocity control (MoveIt Servo) with camera observations from Isaac Sim.
    Optimized for SpaceMouse teleoperation with visual feedback.
    Default resolution is 640×480 (VGA), matching standard LeRobot datasets.

    Camera settings can be customized via environment variables:
    - LEROBOT_CAMERA_TOPIC (default: /rgb/camera_1)
    - LEROBOT_CAMERA_WIDTH (default: 640)
    - LEROBOT_CAMERA_HEIGHT (default: 480)
    - LEROBOT_CAMERA_FPS (default: 30)

    Example:
        lerobot-teleoperate --robot.type=panda_ros_servo_isaac --teleop.type=spacemouse_ee_panda ...
    """

    cameras: dict[str, CameraConfig] = field(default_factory=_get_isaac_camera_config)
