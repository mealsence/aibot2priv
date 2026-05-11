import logging
import os
import threading
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64

from .aibot2_config import Aibot2Config

logger = logging.getLogger(__name__)


class Aibot2Interface:
    """ROS2 interface for the aibot2 dual-arm humanoid robot.

    Subscribes to /joint_states for observations.
    Publishes PoseStamped to Cartesian command topics for each arm.
    Publishes Float64 to gripper command topics.
    """

    def __init__(self, config: Aibot2Config):
        self.config = config
        self.node: Node | None = None
        self.executor: MultiThreadedExecutor | None = None
        self.executor_thread: threading.Thread | None = None
        self.is_connected = False

        self._left_arm_pub = None
        self._right_arm_pub = None
        self._left_gripper_pub = None
        self._right_gripper_pub = None
        self._joint_state_sub = None

        self._last_joint_state: dict[str, dict[str, float]] | None = None
        self._joint_state_lock = threading.Lock()
        self.camera_nodes: list[Node] = []

        # All joint names we care about for observation
        self._all_joint_names = (
            list(config.left_arm_joint_names)
            + list(config.right_arm_joint_names)
            + [config.left_gripper_joint_name, config.right_gripper_joint_name]
        )

    def connect(self) -> None:
        if not rclpy.ok():
            rclpy.init()

        self.node = Node("aibot2_interface_node")

        # Arm command publishers (PoseStamped)
        self._left_arm_pub = self.node.create_publisher(
            PoseStamped, self.config.left_arm_cmd_topic, 10
        )
        self._right_arm_pub = self.node.create_publisher(
            PoseStamped, self.config.right_arm_cmd_topic, 10
        )

        # Gripper command publishers (Float64)
        self._left_gripper_pub = self.node.create_publisher(
            Float64, self.config.left_gripper_cmd_topic, 10
        )
        self._right_gripper_pub = self.node.create_publisher(
            Float64, self.config.right_gripper_cmd_topic, 10
        )

        # Joint state subscriber
        self._joint_state_sub = self.node.create_subscription(
            JointState,
            self.config.joint_state_topic,
            self._joint_state_callback,
            10,
        )

        # Start executor. Camera callbacks convert image messages to numpy arrays, so
        # multiple executor threads prevent 2-4 camera topics from blocking each other.
        num_threads = int(os.getenv("LEROBOT_ROS_EXECUTOR_THREADS", "6"))
        self.executor = MultiThreadedExecutor(num_threads=num_threads)
        self.executor.add_node(self.node)
        self.executor_thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.executor_thread.start()

        # Wait for first joint state
        timeout = 5.0
        start = time.monotonic()
        while self._last_joint_state is None and (time.monotonic() - start) < timeout:
            time.sleep(0.1)

        if self._last_joint_state is None:
            logger.warning("No joint state received within %.1fs — observations may be delayed", timeout)

        self.is_connected = True
        logger.info("Aibot2Interface connected with %d ROS executor threads", num_threads)

    def _joint_state_callback(self, msg: JointState) -> None:
        if len(msg.name) != len(msg.position):
            return

        name_to_idx = {name: i for i, name in enumerate(msg.name)}
        positions = {}
        velocities = {}

        for joint_name in self._all_joint_names:
            idx = name_to_idx.get(joint_name)
            if idx is not None:
                positions[joint_name] = msg.position[idx]
                velocities[joint_name] = msg.velocity[idx] if idx < len(msg.velocity) else 0.0

        if positions:
            with self._joint_state_lock:
                self._last_joint_state = self._last_joint_state or {}
                self._last_joint_state["position"] = positions
                self._last_joint_state["velocity"] = velocities

    @property
    def joint_state(self) -> dict[str, dict[str, float]] | None:
        with self._joint_state_lock:
            return self._last_joint_state

    def send_left_arm_pose(
        self, x: float, y: float, z: float,
        qx: float, qy: float, qz: float, qw: float,
    ) -> None:
        if self._left_arm_pub is None:
            raise RuntimeError("Aibot2Interface not connected")
        msg = PoseStamped()
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.pose.position.x = x
        msg.pose.position.y = y
        msg.pose.position.z = z
        msg.pose.orientation.x = qx
        msg.pose.orientation.y = qy
        msg.pose.orientation.z = qz
        msg.pose.orientation.w = qw
        self._left_arm_pub.publish(msg)

    def send_right_arm_pose(
        self, x: float, y: float, z: float,
        qx: float, qy: float, qz: float, qw: float,
    ) -> None:
        if self._right_arm_pub is None:
            raise RuntimeError("Aibot2Interface not connected")
        msg = PoseStamped()
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.pose.position.x = x
        msg.pose.position.y = y
        msg.pose.position.z = z
        msg.pose.orientation.x = qx
        msg.pose.orientation.y = qy
        msg.pose.orientation.z = qz
        msg.pose.orientation.w = qw
        self._right_arm_pub.publish(msg)

    def send_left_gripper_command(self, value: float) -> None:
        if self._left_gripper_pub is None:
            raise RuntimeError("Aibot2Interface not connected")
        msg = Float64()
        msg.data = float(value)
        self._left_gripper_pub.publish(msg)

    def send_right_gripper_command(self, value: float) -> None:
        if self._right_gripper_pub is None:
            raise RuntimeError("Aibot2Interface not connected")
        msg = Float64()
        msg.data = float(value)
        self._right_gripper_pub.publish(msg)

    def add_camera_node(self, camera_node: Node) -> None:
        if not self.is_connected or not self.executor:
            raise RuntimeError("Aibot2Interface must be connected before adding camera nodes")
        self.executor.add_node(camera_node)
        self.camera_nodes.append(camera_node)
        logger.info("Added camera node %s to executor", camera_node.get_name())

    def disconnect(self) -> None:
        if self._joint_state_sub:
            self._joint_state_sub.destroy()
            self._joint_state_sub = None

        for pub in [self._left_arm_pub, self._right_arm_pub,
                    self._left_gripper_pub, self._right_gripper_pub]:
            if pub:
                pub.destroy()
        self._left_arm_pub = None
        self._right_arm_pub = None
        self._left_gripper_pub = None
        self._right_gripper_pub = None

        for camera_node in self.camera_nodes:
            if self.executor:
                self.executor.remove_node(camera_node)
        self.camera_nodes.clear()

        if self.node:
            self.node.destroy_node()
            self.node = None

        if self.executor:
            self.executor.shutdown()
            self.executor = None
        if self.executor_thread:
            self.executor_thread.join(timeout=5.0)
            self.executor_thread = None

        self.is_connected = False
        logger.info("Aibot2Interface disconnected")
