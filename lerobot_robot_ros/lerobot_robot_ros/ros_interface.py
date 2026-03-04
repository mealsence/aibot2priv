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
import threading
import time

import rclpy
from control_msgs.action import GripperCommand
from geometry_msgs.msg import Twist
from lerobot.utils.errors import DeviceNotConnectedError
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import Executor, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.publisher import Publisher
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

try:
    from franka_msgs.action import Move as FrankaMove
    from franka_msgs.action import Grasp as FrankaGrasp
    _FRANKA_MSGS_AVAILABLE = True
except ImportError:
    _FRANKA_MSGS_AVAILABLE = False
    FrankaMove = None
    FrankaGrasp = None

from .config import ActionType, GripperActionType, ROS2InterfaceConfig

from tf2_ros import TransformException
from tf2_ros.buffer import Buffer
from tf2_ros.transform_listener import TransformListener

logger = logging.getLogger(__name__)


class ROS2Interface:
    """Class to interface with a ROS2 robot arm using ros2_control.

    This class supports both JointGroupPositionController and JointTrajectoryController
    from ros2_control for arm control, depending on the configuration:

    - ActionType.JOINT_POSITION:
      Uses JointGroupPositionController.
      Publishes Float64MultiArray messages to '/position_controller/commands'
      Ultra-low latency (~15-20ms) for responsive control.

    - ActionType.JOINT_TRAJECTORY:
      Uses JointTrajectoryController.
      Publishes JointTrajectory messages to '/arm_controller/joint_trajectory'
      Smoother motion with trajectory interpolation.

    The gripper control supports both trajectory and action-based control
    via the gripper_action_type configuration option.

    The executor thread is also used to spin camera nodes for ROS2Camera instances,
    enabling all ROS2 subscriptions (joint states, images) to share a single executor.
    """

    def __init__(self, config: ROS2InterfaceConfig, action_type: ActionType):
        self.config = config
        self.action_type = action_type
        self.robot_node: Node | None = None
        self.pos_cmd_pub: Publisher | None = None
        self.traj_cmd_pub: Publisher | None = None
        self.cart_vel_pub: Publisher | None = None
        self.gripper_action_client: ActionClient | None = None
        self.gripper_move_client: ActionClient | None = None
        self.gripper_grasp_client: ActionClient | None = None
        self.gripper_traj_pub: Publisher | None = None
        self.executor: Executor | None = None
        self.executor_thread: threading.Thread | None = None
        self.is_connected = False
        self._last_joint_state: dict[str, dict[str, float]] | None = None
        self.camera_nodes: list[Node] = []  # Track camera nodes for lifecycle management

    def connect(self) -> None:
        if not rclpy.ok():
            rclpy.init()

        self.robot_node = Node("ros2_interface_node", namespace=self.config.namespace)
        if self.action_type == ActionType.JOINT_POSITION:
            self.pos_cmd_pub = self.robot_node.create_publisher(
                Float64MultiArray, f"/{self.config.position_controller_name}/commands", 10
            )
        elif self.action_type == ActionType.JOINT_TRAJECTORY:
            self.traj_cmd_pub = self.robot_node.create_publisher(
                JointTrajectory, f"/{self.config.arm_controller_name}/joint_trajectory", 10
            )
        elif self.action_type == ActionType.CARTESIAN_VELOCITY:
            self.cart_vel_pub = self.robot_node.create_publisher(
                Twist, self.config.cartesian_velocity_topic, 10
            )

        if self.config.gripper_action_type == GripperActionType.TRAJECTORY:
            self.gripper_traj_pub = self.robot_node.create_publisher(
                JointTrajectory, f"/{self.config.gripper_controller_name}/joint_trajectory", 10
            )
        elif self.config.gripper_action_type == GripperActionType.FRANKA_MOVE:
            if not _FRANKA_MSGS_AVAILABLE:
                raise ImportError(
                    "franka_msgs is not installed. "
                    "Install franka_ros2 or use GripperActionType.ACTION instead."
                )
            # Move: used for opening (position-only, no force semantics)
            self.gripper_move_client = ActionClient(
                self.robot_node,
                FrankaMove,
                f"/{self.config.gripper_controller_name}/move",
                callback_group=ReentrantCallbackGroup(),
            )
            # Grasp: used for closing — handles object contact via epsilon tolerance
            self.gripper_grasp_client = ActionClient(
                self.robot_node,
                FrankaGrasp,
                f"/{self.config.gripper_controller_name}/grasp",
                callback_group=ReentrantCallbackGroup(),
            )
        else:  # ACTION
            self.gripper_action_client = ActionClient(
                self.robot_node,
                GripperCommand,
                f"/{self.config.gripper_controller_name}/{self.config.gripper_action_name}",
                callback_group=ReentrantCallbackGroup(),
            )
            self._goal_msg = GripperCommand.Goal()

        self.joint_state_sub = self.robot_node.create_subscription(
            JointState,
            "joint_states",
            self._joint_state_callback,
            10,
        )

        # Create and start the executor in a separate thread
        self.executor = SingleThreadedExecutor()
        self.executor.add_node(self.robot_node)
        self.executor_thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.executor_thread.start()
        time.sleep(3)  # Give some time to connect to services and receive messages

        for gripper_client in filter(None, [
            self.gripper_move_client,
            self.gripper_grasp_client,
            self.gripper_action_client,
        ]):
            if not gripper_client.wait_for_server(timeout_sec=5.0):
                logger.warning(
                    f"Gripper action server {gripper_client._action_name!r} not available. "
                    "Gripper commands may fail until the server comes up."
                )
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self.robot_node)
        self.is_connected = True

    def send_joint_position_command(self, joint_positions: list[float], unnormalize: bool = True) -> None:
        """
        Send a command to the robot's joints.
        Args:
            joint_positions (list[float]): The target positions for the joints.
            unnormalize (bool): Whether to unnormalize the joint positions based on the robot's configuration.
        """
        if not self.robot_node:
            raise DeviceNotConnectedError("ROS2Interface is not connected. You need to call `connect()`.")

        if unnormalize:
            if self.config.min_joint_positions is None or self.config.max_joint_positions is None:
                raise ValueError(
                    "Joint position normalization requires min and max joint positions to be set."
                )
            joint_positions = [
                min(max(pos, min_pos), max_pos)
                for pos, min_pos, max_pos in zip(
                    joint_positions,
                    self.config.min_joint_positions,
                    self.config.max_joint_positions,
                    strict=True,
                )
            ]

        if len(joint_positions) != len(self.config.arm_joint_names):
            raise ValueError(
                f"Expected {len(self.config.arm_joint_names)} joint positions, but got {len(joint_positions)}."
            )

        if self.action_type == ActionType.JOINT_TRAJECTORY:
            if self.traj_cmd_pub is None:
                raise DeviceNotConnectedError("Trajectory command publisher is not initialized.")
            msg = JointTrajectory()
            msg.joint_names = self.config.arm_joint_names
            point = JointTrajectoryPoint()
            point.positions = joint_positions
            msg.points = [point]
            self.traj_cmd_pub.publish(msg)
        else:
            if self.pos_cmd_pub is None:
                raise DeviceNotConnectedError("Position command publisher is not initialized.")
            msg = Float64MultiArray()
            msg.data = joint_positions
            self.pos_cmd_pub.publish(msg)

    def send_cartesian_velocity_command(
        self,
        vx: float,
        vy: float,
        vz: float,
        wx: float = 0.0,
        wy: float = 0.0,
        wz: float = 0.0,
    ) -> None:
        """Publish a Cartesian velocity command to the twist controller.

        Args:
            vx, vy, vz: Linear velocity components in m/s (robot base frame).
            wx, wy, wz: Angular velocity components in rad/s (default: 0).
        """
        if not self.robot_node:
            raise DeviceNotConnectedError("ROS2Interface is not connected. You need to call `connect()`.")
        if self.cart_vel_pub is None:
            raise DeviceNotConnectedError("Cartesian velocity publisher is not initialized.")
        msg = Twist()
        msg.linear.x = float(vx)
        msg.linear.y = float(vy)
        msg.linear.z = float(vz)
        msg.angular.x = float(wx)
        msg.angular.y = float(wy)
        msg.angular.z = float(wz)
        self.cart_vel_pub.publish(msg)

    def send_gripper_command(self, position: float, unnormalize: bool = True) -> bool:
        """
        Send a command to the gripper to move to a specific position.
        Args:
            position (float): The target position for the gripper (0=open, 1=closed).
        Returns:
            bool: True if the command was sent successfully, False otherwise.
        """
        if not self.robot_node:
            raise DeviceNotConnectedError("ROS2Interface is not connected. You need to call `connect()`.")

        if unnormalize:
            # Map normalized position (0=open, 1=closed) to actual gripper joint position
            open_pos = self.config.gripper_open_position
            closed_pos = self.config.gripper_close_position
            gripper_goal = open_pos + position * (closed_pos - open_pos)
        else:
            gripper_goal = position

        if self.config.gripper_action_type == GripperActionType.TRAJECTORY:
            if self.gripper_traj_pub is None:
                raise DeviceNotConnectedError("Gripper command publisher is not initialized.")
            msg = JointTrajectory()
            msg.joint_names = [self.config.gripper_joint_name]
            point = JointTrajectoryPoint()
            point.positions = [float(gripper_goal)]
            msg.points = [point]
            self.gripper_traj_pub.publish(msg)
            return True
        elif self.config.gripper_action_type == GripperActionType.FRANKA_MOVE:
            midpoint = (self.config.gripper_open_position + self.config.gripper_close_position) / 2
            if gripper_goal <= midpoint:
                # Closing: use Grasp — handles object contact via epsilon tolerance.
                # Move would abort with "Command aborted!" if the fingers stall on an object.
                if not self.gripper_grasp_client:
                    raise DeviceNotConnectedError("Gripper grasp client is not initialized.")
                goal = FrankaGrasp.Goal()
                goal.width = float(gripper_goal)
                goal.speed = float(self.config.gripper_speed)
                goal.force = float(self.config.gripper_grasp_force)
                goal.epsilon.inner = 0.005
                goal.epsilon.outer = float(self.config.gripper_grasp_epsilon_outer)
                future = self.gripper_grasp_client.send_goal_async(goal)
            else:
                # Opening: use Move — purely position-based, no force needed.
                if not self.gripper_move_client:
                    raise DeviceNotConnectedError("Gripper move client is not initialized.")
                goal = FrankaMove.Goal()
                goal.width = float(gripper_goal)
                goal.speed = float(self.config.gripper_speed)
                future = self.gripper_move_client.send_goal_async(goal)
            future.add_done_callback(self._gripper_goal_response_callback)
            return True
        else:  # ACTION
            if not self.gripper_action_client:
                raise DeviceNotConnectedError("Gripper action client is not initialized.")
            self._goal_msg.command.position = float(gripper_goal)
            self._goal_msg.command.max_effort = float(self.config.gripper_max_effort)
            send_goal_future = self.gripper_action_client.send_goal_async(self._goal_msg)
            send_goal_future.add_done_callback(self._gripper_goal_response_callback)
            return True

    def _gripper_goal_response_callback(self, future) -> None:
        goal_handle = future.result()
        if not goal_handle.accepted:
            logger.error("Gripper goal rejected by action server")
            return
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._gripper_result_callback)

    def _gripper_result_callback(self, future) -> None:
        result = future.result().result
        if self.config.gripper_action_type == GripperActionType.FRANKA_MOVE:
            # franka_msgs/action/Move result: success=True means reached width or stalled on object.
            if not result.success:
                logger.warning(f"Gripper move failed: {result.error}")
        else:
            # control_msgs/action/GripperCommand result
            if result.stalled:
                # Gripper contacted an object — successful grasp.
                logger.debug(
                    f"Gripper grasped object. effort: {result.effort:.3f}, position: {result.position:.4f}"
                )
            elif not result.reached_goal:
                # Neither reached target nor stalled on object — unexpected failure.
                logger.warning(
                    f"Gripper did not reach goal. effort: {result.effort:.3f}, position: {result.position:.4f}"
                )

    @property
    def joint_state(self) -> dict[str, dict[str, float]] | None:
        """Get the last received joint state."""
        return self._last_joint_state

    def _joint_state_callback(self, msg: "JointState") -> None:
        self._last_joint_state = self._last_joint_state or {}
        positions = {}
        velocities = {}
        name_to_index = {name: i for i, name in enumerate(msg.name)}
        for joint_name in self.config.arm_joint_names:
            idx = name_to_index.get(joint_name)
            if idx is None:
                raise ValueError(f"Joint '{joint_name}' not found in joint state.")
            positions[joint_name] = msg.position[idx]
            velocities[joint_name] = msg.velocity[idx]

        if self.config.gripper_joint_name:
            idx = name_to_index.get(self.config.gripper_joint_name)
            if idx is None:
                raise ValueError(
                    f"Gripper joint '{self.config.gripper_joint_name}' not found in joint state."
                )
            positions[self.config.gripper_joint_name] = msg.position[idx]
            velocities[self.config.gripper_joint_name] = msg.velocity[idx]

        self._last_joint_state["position"] = positions
        self._last_joint_state["velocity"] = velocities

    def add_camera_node(self, camera_node: Node) -> None:
        """
        Add a camera node to the executor.

        This method adds a ROS2Camera's node to the shared executor thread,
        allowing camera image callbacks to be processed alongside joint state updates.

        Args:
            camera_node: The ROS2 node from a ROS2Camera instance.

        Raises:
            RuntimeError: If called before connect() or if executor is not available.
        """
        if not self.is_connected or not self.executor:
            raise RuntimeError("ROS2Interface must be connected before adding camera nodes")

        self.executor.add_node(camera_node)
        self.camera_nodes.append(camera_node)
        logger.info(f"Added camera node {camera_node.get_name()} to executor")

    def disconnect(self):
        if self.joint_state_sub:
            self.joint_state_sub.destroy()
            self.joint_state_sub = None
        if self.pos_cmd_pub:
            self.pos_cmd_pub.destroy()
            self.pos_cmd_pub = None
        if self.traj_cmd_pub:
            self.traj_cmd_pub.destroy()
            self.traj_cmd_pub = None
        if self.cart_vel_pub:
            # Publish zero velocity on disconnect for safety
            try:
                self.cart_vel_pub.publish(Twist())
            except Exception:
                pass
            self.cart_vel_pub.destroy()
            self.cart_vel_pub = None
        if self.gripper_action_client:
            self.gripper_action_client.destroy()
            self.gripper_action_client = None
        if self.gripper_move_client:
            self.gripper_move_client.destroy()
            self.gripper_move_client = None
        if self.gripper_grasp_client:
            self.gripper_grasp_client.destroy()
            self.gripper_grasp_client = None
        if self.gripper_traj_pub:
            self.gripper_traj_pub.destroy()
            self.gripper_traj_pub = None
        if self.robot_node:
            self.robot_node.destroy_node()
            self.robot_node = None

        # Remove camera nodes from executor (if any)
        for camera_node in self.camera_nodes:
            if self.executor:
                self.executor.remove_node(camera_node)
        self.camera_nodes.clear()

        if self.executor:
            self.executor.shutdown()
            self.executor = None
        if self.executor_thread:
            self.executor_thread.join()
            self.executor_thread = None

        self.is_connected = False
    
    def get_current_state(self) -> dict:
        """Returns the current pose of the end-effector."""
        try:
            # Ensure the tf_buffer exists (it should be initialized in connect())
            if not hasattr(self, 'tf_buffer'):
                return {"pose": {"x": 0.0, "y": 0.0, "z": 1.0}}

            now = rclpy.time.Time()
            # Lookup transform from base (link0) to hand
            trans = self.tf_buffer.lookup_transform(
                'panda_link0', 
                'panda_hand', 
                now,
                timeout=rclpy.duration.Duration(seconds=0.1)
            )
            
            return {
                "pose": {
                    "x": trans.transform.translation.x,
                    "y": trans.transform.translation.y,
                    "z": trans.transform.translation.z
                }
            }
        except Exception as e:
            # If TF fails, we return a safe high Z so the robot doesn't freeze
            return {"pose": {"x": 0.0, "y": 0.0, "z": 1.0}}
