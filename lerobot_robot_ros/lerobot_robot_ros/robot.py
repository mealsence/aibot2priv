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

import logging
import time
from functools import cached_property
from typing import Any

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.robots import Robot
from lerobot.robots.utils import ensure_safe_goal_position
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from .config import ActionType, PandaROSCartesianConfig, ROS2Config
from .ros_interface import ROS2Interface

# Import ROS2Camera for type checking
try:
    from .ros2_camera import ROS2Camera
except ImportError:
    ROS2Camera = None  # type: ignore

logger = logging.getLogger(__name__)


class ROS2Robot(Robot):
    config_class = ROS2Config
    name = "ros2"

    def __init__(self, config: ROS2Config):
        super().__init__(config)
        self.config = config
        self.ros2_interface = ROS2Interface(config.ros2_interface, config.action_type)
        self.cameras = make_cameras_from_configs(config.cameras)

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3) for cam in self.cameras
        }

    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        all_joint_names = self.config.ros2_interface.arm_joint_names.copy()
        if self.config.ros2_interface.gripper_joint_name:
            all_joint_names.append(self.config.ros2_interface.gripper_joint_name)
        motor_state_ft = {f"{motor}.pos": float for motor in all_joint_names}
        return {**motor_state_ft, **self._cameras_ft}

    @cached_property
    def action_features(self) -> dict[str, type]:
        return {f"{joint}.pos": float for joint in self.config.ros2_interface.arm_joint_names} | {
            "gripper.pos": float
        }

    @property
    def is_connected(self) -> bool:
        return self.ros2_interface.is_connected and all(cam.is_connected for cam in self.cameras.values())

    def connect(self, calibrate: bool = True) -> None:
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")

        # Connect cameras first
        for cam in self.cameras.values():
            cam.connect()

        # Connect ROS2 interface (this starts the executor thread)
        self.ros2_interface.connect()

        # Add ROS2Camera nodes to the shared executor
        if ROS2Camera is not None:
            for cam in self.cameras.values():
                if isinstance(cam, ROS2Camera):
                    self.ros2_interface.add_camera_node(cam.node)
                    logger.info(f"Added {cam} to ROS2Interface executor")

    @property
    def is_calibrated(self) -> bool:
        return True

    def calibrate(self) -> None:
        pass  # robot must be calibrated before running LeRobot

    def configure(self) -> None:
        pass  # robot must be configured before running LeRobot

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        obs_dict: dict[str, Any] = {}
        joint_state = self.ros2_interface.joint_state
        if joint_state is None:
            raise ValueError("Joint state is not available yet.")
        obs_dict.update({f"{joint}.pos": pos for joint, pos in joint_state["position"].items()})

        # Capture images from cameras
        for cam_key, cam in self.cameras.items():
            start = time.perf_counter()
            try:
                obs_dict[cam_key] = cam.async_read(timeout_ms=300)
            except Exception as e:
                logger.error(f"Failed to read camera {cam_key}: {e}")
                obs_dict[cam_key] = None
            dt_ms = (time.perf_counter() - start) * 1e3
            logger.debug(f"{self} read {cam_key}: {dt_ms:.1f}ms")

        return obs_dict

    def send_action(self, action: dict[str, float]) -> dict[str, float]:
        """Command arm to move to a target joint configuration.

        The relative action magnitude may be clipped depending on the configuration parameter
        `max_relative_target`. In this case, the action sent differs from original action.
        Thus, this function always returns the action actually sent.

        Args:
            action (dict[str, float]): The goal positions for the motors.

        Raises:
            DeviceNotConnectedError: if robot is not connected.

        Returns:
            dict[str, float]: The action sent to the motors, potentially clipped.
        """
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        if self.config.max_relative_target is not None:
            goal_present_pos = {}
            joint_state = self.ros2_interface.joint_state
            if joint_state is None:
                raise ValueError("Joint state is not available yet.")

            for key, goal in action.items():
                present_pos = joint_state["position"].get(key.replace(".pos", ""), 0.0)
                goal_present_pos[key] = (goal, present_pos)
            action = ensure_safe_goal_position(goal_present_pos, self.config.max_relative_target)

        joint_positions = [action[joint + ".pos"] for joint in self.config.ros2_interface.arm_joint_names]
        self.ros2_interface.send_joint_position_command(joint_positions)

        gripper_pos = action["gripper.pos"]
        self.ros2_interface.send_gripper_command(gripper_pos)
        return action

    def disconnect(self):
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        for cam in self.cameras.values():
            cam.disconnect()
        self.ros2_interface.disconnect()

        logger.info(f"{self} disconnected.")


class SO101ROS(ROS2Robot):
    pass


class AnninAR4(ROS2Robot):
    pass


class PandaROS(ROS2Robot):
    """Panda robot with ROS2 camera support and trajectory control."""
    pass


class PandaROSPosition(ROS2Robot):
    """Panda robot with ROS2 camera support and fast direct position control."""
    pass


class PandaROSCartesian(ROS2Robot):
    """Panda robot controlled via Cartesian velocity for real robot data collection.

    Action space: {vx, vy, vz, gripper.pos}
    Observation:  joint positions + camera (same as PandaROS)

    Publishes geometry_msgs/Twist to /cartesian_twist_controller/cmd_vel.
    Gripper is commanded only when the target position changes (avoids blocking).
    """

    config_class = PandaROSCartesianConfig
    name = "panda_ros_cartesian"

    def __init__(self, config: PandaROSCartesianConfig):
        super().__init__(config)
        self._gripper_target: float | None = None

    @cached_property
    def action_features(self) -> dict[str, type]:
        return {"x.vel": float, "y.vel": float, "z.vel": float, "gripper.pos": float}

    def send_action(self, action: dict[str, Any]) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        self.ros2_interface.send_cartesian_velocity_command(
            vx=float(action.get("x.vel", 0.0)),
            vy=float(action.get("y.vel", 0.0)),
            vz=float(action.get("z.vel", 0.0)),
        )

        gripper_pos = float(action.get("gripper.pos", 0.0))
        if self._gripper_target is None or abs(gripper_pos - self._gripper_target) > 0.4:
            self.ros2_interface.send_gripper_command(gripper_pos)
            self._gripper_target = gripper_pos

        return action
