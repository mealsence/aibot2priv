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
    JOINT_POSITION = "joint_position"
    JOINT_TRAJECTORY = "joint_trajectory"
    CARTESIAN_VELOCITY = "cartesian_velocity"


class GripperActionType(Enum):
    TRAJECTORY = "trajectory"    # JointTrajectoryController (topic)
    ACTION = "action"            # control_msgs/action/GripperCommand
    FRANKA_MOVE = "franka_move"  # franka_msgs/action/Move — total gap + speed


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

    # Base link name for computing end effector pose
    base_link: str = "base_link"

    # Joint position limits
    min_joint_positions: list[float] | None = None
    max_joint_positions: list[float] | None = None

    gripper_open_position: float = 0.0
    gripper_close_position: float = 1.0
    # Max effort (N) for GripperCommand (ACTION type). Must be > 0 for the gripper to move.
    gripper_max_effort: float = 0.0
    # Speed (m/s) for franka_msgs/action/Move and Grasp (FRANKA_MOVE type).
    gripper_speed: float = 0.1
    # Grasping force (N) for franka_msgs/action/Grasp used when closing.
    gripper_grasp_force: float = 30.0
    # epsilon_outer (m): how far from the target width still counts as a successful grasp.
    # Set to gripper_open_position so any object width between 0 and fully open is accepted.
    gripper_grasp_epsilon_outer: float = 0.08

    gripper_action_type: GripperActionType = GripperActionType.TRAJECTORY

    # Controller names for arm and gripper
    # For Panda sim (panda_ros/panda_ros_position): use "panda_arm_controller" / "panda_hand_controller"
    # For Panda real (panda_ros_cartesian): use "panda_arm_controller" / "panda_gripper"
    # For other robots: typically "arm_controller" and "gripper_controller"
    arm_controller_name: str = "arm_controller"
    position_controller_name: str = "position_controller"
    gripper_controller_name: str = "gripper_controller"

    # Action name for the gripper action server (appended to gripper_controller_name).
    # franka_ros2 uses "gripper_action"; ros2_control typically uses "gripper_cmd".
    gripper_action_name: str = "gripper_cmd"

    # Topic for Cartesian velocity control (ActionType.CARTESIAN_VELOCITY)
    cartesian_velocity_topic: str = "/cartesian_twist_controller/cmd_vel"


@dataclass
class ROS2Config(RobotConfig):
    # Action type for controlling the robot: 'joint_position' or 'joint_trajectory'.
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

    action_type: ActionType = ActionType.JOINT_TRAJECTORY

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


def _get_camera_config() -> dict[str, CameraConfig]:
    """Get camera configuration from environment variables or use defaults.

    Default resolution is 640×480 (VGA), which is the standard used across LeRobot datasets
    like ALOHA, Reachy2, and LeKiwi. This provides a good balance between image quality
    and dataset size, and is compatible with all policy types.

    Camera settings can be customized via environment variables:
    - LEROBOT_CAMERA_TOPIC (default: /rgb/camera_1)
    - LEROBOT_CAMERA_WIDTH (default: 640)
    - LEROBOT_CAMERA_HEIGHT (default: 480)
    - LEROBOT_CAMERA_FPS (default: 30)
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


@RobotConfig.register_subclass("panda_ros")
@dataclass
class PandaROSConfig(ROS2Config):
    """Configuration for Franka Emika Panda robot with ROS2.

    Uses JOINT_TRAJECTORY for smooth motion with trajectory interpolation.
    Includes ROS2 camera support (configurable via environment variables).

    Example:
        lerobot-record --robot.type=panda_ros --robot.id=my_panda ...
    """

    action_type: ActionType = ActionType.JOINT_TRAJECTORY

    cameras: dict[str, CameraConfig] = field(default_factory=_get_camera_config)

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


@RobotConfig.register_subclass("panda_ros_position")
@dataclass
class PandaROSPositionConfig(PandaROSConfig):
    """Configuration for Franka Emika Panda with direct position control.

    Uses JOINT_POSITION action type for ultra-low latency control
    (~15-20ms vs ~120ms with trajectory control). Ideal for responsive teleoperation.

    Uses JointGroupPositionController instead of JointTrajectoryController:
    - No trajectory interpolation (instant command execution)
    - 6-8x faster response time
    - Slightly jerkier motion (no smoothing)

    Example:
        lerobot-record --robot.type=panda_ros_position --robot.id=my_panda ...
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
        ),
    )


@RobotConfig.register_subclass("panda_ros_cartesian")
@dataclass
class PandaROSCartesianConfig(PandaROSConfig):
    """Configuration for Franka Panda real robot data collection via Cartesian velocity control.

    Uses CARTESIAN_VELOCITY action type: publishes geometry_msgs/Twist to
    /cartesian_twist_controller/cmd_vel. The same controller used by spacemouse_cartesian_vel.py.

    Action space: {vx, vy, vz, gripper.pos}  (Cartesian velocities + gripper)
    Observation:  joint positions + camera (same as panda_ros)

    Example:
        lerobot-record --robot.type=panda_ros_cartesian --robot.id=my_panda ...
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
            # franka_msgs/action/Move uses TOTAL gap (both fingers combined).
            # max_width ≈ 0.0775 m; use 0.075 m to stay safely within range.
            gripper_open_position=0.075,
            # Target 0.0 m (fully closed). The Franka gripper's built-in force sensing
            # stops the fingers automatically when they contact the GelSight sensors or
            # an object — no mechanical damage. Mirrors test_gripper.py move_gripper(0.0).
            gripper_close_position=0.0,
            gripper_speed=0.1,
            gripper_grasp_force=30.0,
            # Accept any grasp width up to fully open (object between fingers = success).
            gripper_grasp_epsilon_outer=0.08,
            gripper_action_type=GripperActionType.FRANKA_MOVE,
            gripper_controller_name="panda_gripper",
            cartesian_velocity_topic="/cartesian_twist_controller/cmd_vel",
        ),
    )
