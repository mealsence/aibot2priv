#!/usr/bin/env python3
"""
Real Robot Control Module for Franka Panda

Standalone control module for interfacing with a REAL Franka Panda robot
via franka_ros2. Designed to run on the workstation and communicate over
ROS2 DDS to the control PC (192.168.1.2) which runs franka_bringup.

Network Setup:
    Robot IP:     192.168.1.101 (Franka FCI)
    Control PC:   192.168.1.2   (runs franka_ros2 bringup)
    Workstation:  this machine  (runs this script)

Key differences from Isaac Sim version (gripper_control_module.py):
    - Joint states on /joint_states (franka_ros2 standard)
    - Gripper uses franka_msgs.action.Move on /panda_gripper/move
    - Auto-detects available controllers (trajectory, position, or torque)
    - Extra safety checks for real hardware
"""

import time
import subprocess
import sys
from typing import Dict, List, Optional

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.executors import SingleThreadedExecutor

from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from control_msgs.action import FollowJointTrajectory

# Try to import franka-specific messages (available when franka_ros2 is installed)
try:
    from franka_msgs.action import Move as FrankaMove
    FRANKA_MSGS_AVAILABLE = True
except ImportError:
    FRANKA_MSGS_AVAILABLE = False
    print("⚠️ franka_msgs not found. Gripper control will use fallback GripperCommand action.")

try:
    from control_msgs.action import GripperCommand
    GRIPPER_COMMAND_AVAILABLE = True
except ImportError:
    GRIPPER_COMMAND_AVAILABLE = False


# Panda joint names
PANDA_JOINT_NAMES = [
    'panda_joint1', 'panda_joint2', 'panda_joint3',
    'panda_joint4', 'panda_joint5', 'panda_joint6', 'panda_joint7'
]

# Panda joint limits (radians) - from Franka documentation
PANDA_JOINT_LIMITS = {
    'panda_joint1': (-2.8973, 2.8973),
    'panda_joint2': (-1.7628, 1.7628),
    'panda_joint3': (-2.8973, 2.8973),
    'panda_joint4': (-3.0718, -0.0698),
    'panda_joint5': (-2.8973, 2.8973),
    'panda_joint6': (-0.0175, 3.7525),
    'panda_joint7': (-2.8973, 2.8973),
}

# Maximum joint velocity (rad/s) - conservative limits for safety
PANDA_MAX_JOINT_VELOCITY = [2.175, 2.175, 2.175, 2.175, 2.610, 2.610, 2.610]

# Global ROS2 context management
_ros_context_initialized = False


def _ensure_ros_context():
    """Ensure ROS2 context is initialized once for all controllers"""
    global _ros_context_initialized
    if not _ros_context_initialized:
        try:
            rclpy.init()
            _ros_context_initialized = True
            print("🤖 ROS2 context initialized")
        except Exception as e:
            err_str = str(e).lower()
            if "already been initialized" in err_str or "must only be called once" in err_str:
                _ros_context_initialized = True
                return True
            print(f"⚠️ Warning: Could not initialize ROS2 context: {e}")
            return False
    return True


def check_available_topics() -> List[str]:
    """Check available ROS2 topics (useful for diagnostics)"""
    try:
        result = subprocess.run(
            ['ros2', 'topic', 'list'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            topics = [t.strip() for t in result.stdout.strip().split('\n') if t.strip()]
            return topics
        else:
            print(f"⚠️ Failed to list topics: {result.stderr}")
            return []
    except subprocess.TimeoutExpired:
        print("⚠️ Timeout listing ROS2 topics")
        return []
    except FileNotFoundError:
        print("⚠️ ros2 command not found. Is ROS2 sourced?")
        return []


def check_franka_running() -> Dict[str, bool]:
    """Check if franka_ros2 is running and which topics/controllers are available"""
    topics = check_available_topics()

    checks = {
        'ros2_available': len(topics) > 0,
        'joint_states': '/joint_states' in topics or '/franka/joint_states' in topics,
        'gripper_move': any('/panda_gripper' in t for t in topics),
        'arm_controller': any('panda_arm_controller' in t for t in topics),
        'position_controller': any('panda_position_controller' in t or 'position_controller' in t for t in topics),
        'trajectory_controller': any('joint_trajectory_controller' in t for t in topics),
    }

    return checks


class RealRobotGripperController:
    """Gripper controller for real Franka Panda using franka_msgs.action.Move"""

    def __init__(self):
        self.node = None
        self.franka_action_client = None
        self.fallback_action_client = None
        self._initialized = False

    def _ensure_ros_init(self):
        if not self._initialized:
            try:
                if not _ensure_ros_context():
                    return False

                self.node = Node('real_gripper_controller')

                # Prefer native Franka gripper action
                if FRANKA_MSGS_AVAILABLE:
                    self.franka_action_client = ActionClient(
                        self.node, FrankaMove, '/panda_gripper/move'
                    )
                    print("🤖 Gripper: using franka_msgs.action.Move on /panda_gripper/move")

                # Fallback to GripperCommand
                if GRIPPER_COMMAND_AVAILABLE:
                    self.fallback_action_client = ActionClient(
                        self.node, GripperCommand, '/panda_hand_controller/gripper_cmd'
                    )

                self._initialized = True
                print("🤖 Real gripper controller initialized")
            except Exception as e:
                print(f"⚠️ Warning: Could not initialize gripper controller: {e}")
                return False
        return True

    def move_gripper(self, width: float, speed: float = 0.1) -> bool:
        """
        Move gripper to specified width using native Franka action.

        Args:
            width: Target width in meters (0.0 = closed, 0.08 = fully open)
            speed: Movement speed in m/s
        """
        if not self._ensure_ros_init():
            return False

        # Try native Franka action first
        if self.franka_action_client:
            try:
                print(f"📡 Waiting for /panda_gripper/move action server...")
                if not self.franka_action_client.wait_for_server(timeout_sec=5.0):
                    print("⚠️ /panda_gripper/move not available, trying fallback...")
                else:
                    goal_msg = FrankaMove.Goal()
                    goal_msg.width = width
                    goal_msg.speed = speed

                    print(f"🤏 Moving gripper: width={width:.3f}m, speed={speed:.2f}m/s")

                    future = self.franka_action_client.send_goal_async(goal_msg)
                    rclpy.spin_until_future_complete(self.node, future, timeout_sec=5.0)

                    if future.done():
                        goal_handle = future.result()
                        if goal_handle.accepted:
                            result_future = goal_handle.get_result_async()
                            rclpy.spin_until_future_complete(self.node, result_future, timeout_sec=10.0)
                            if result_future.done():
                                print("✅ Gripper move completed")
                                return True
                        else:
                            print("⚠️ Gripper goal rejected")
                    else:
                        print("⚠️ Gripper command timeout")
            except Exception as e:
                print(f"⚠️ Franka gripper action failed: {e}")

        # Fallback to GripperCommand
        if self.fallback_action_client:
            return self._send_gripper_command_fallback(width)

        print("❌ No gripper action server available")
        return False

    def _send_gripper_command_fallback(self, position: float) -> bool:
        """Fallback gripper control using GripperCommand action"""
        try:
            if not self.fallback_action_client.wait_for_server(timeout_sec=2.0):
                print("⚠️ GripperCommand action server not available")
                return False

            goal_msg = GripperCommand.Goal()
            goal_msg.command.position = position
            goal_msg.command.max_effort = 50.0

            future = self.fallback_action_client.send_goal_async(goal_msg)
            rclpy.spin_until_future_complete(self.node, future, timeout_sec=5.0)

            if future.done():
                goal_handle = future.result()
                if goal_handle.accepted:
                    result_future = goal_handle.get_result_async()
                    rclpy.spin_until_future_complete(self.node, result_future, timeout_sec=5.0)
                    if result_future.done():
                        return True
            return False
        except Exception as e:
            print(f"⚠️ Fallback gripper command failed: {e}")
            return False


class RealRobotArmController:
    """
    Arm controller for real Franka Panda.

    Auto-detects the available control interface:
    - FollowJointTrajectory action on /panda_arm_controller/follow_joint_trajectory
    - JointTrajectory topic on /panda_arm_controller/joint_trajectory
    - Float64MultiArray topic on /panda_position_controller/commands

    Also subscribes to /joint_states to read current joint positions.
    """

    def __init__(self):
        self.node = None
        self.action_client = None
        self.trajectory_publisher = None
        self.position_publisher = None
        self.joint_state_subscription = None
        self.current_joint_positions = None
        self._initialized = False
        self._controller_type = None  # 'action', 'trajectory_topic', 'position_topic'

    def _ensure_ros_init(self):
        if not self._initialized:
            try:
                if not _ensure_ros_context():
                    return False

                self.node = Node('real_arm_controller')

                # Set up action client for FollowJointTrajectory
                self.action_client = ActionClient(
                    self.node, FollowJointTrajectory,
                    '/panda_arm_controller/follow_joint_trajectory'
                )

                # Set up trajectory topic publisher
                self.trajectory_publisher = self.node.create_publisher(
                    JointTrajectory,
                    '/panda_arm_controller/joint_trajectory',
                    10
                )

                # Set up position topic publisher
                self.position_publisher = self.node.create_publisher(
                    Float64MultiArray,
                    '/panda_position_controller/commands',
                    10
                )

                # Subscribe to joint states (try both standard and Franka-specific)
                self.joint_state_subscription = self.node.create_subscription(
                    JointState,
                    '/joint_states',
                    self._joint_state_callback,
                    10
                )

                self._initialized = True
                print("🤖 Real arm controller initialized")
            except Exception as e:
                print(f"⚠️ Warning: Could not initialize arm controller: {e}")
                return False
        return True

    def _joint_state_callback(self, msg: JointState):
        """Callback to store current joint positions"""
        try:
            current_positions = []
            for joint_name in PANDA_JOINT_NAMES:
                if joint_name in msg.name:
                    idx = msg.name.index(joint_name)
                    current_positions.append(msg.position[idx])
                else:
                    return  # Not all joints found, skip this message

            if len(current_positions) == 7:
                self.current_joint_positions = current_positions
        except Exception as e:
            print(f"⚠️ Error processing joint state: {e}")

    def _detect_controller_type(self) -> str:
        """Detect which controller is available"""
        if self._controller_type is not None:
            return self._controller_type

        print("🔍 Detecting available arm controller...")

        # Allow time for ROS2 discovery
        for _ in range(20):
            rclpy.spin_once(self.node, timeout_sec=0.1)

        # Try action interface first (most reliable for trajectory control)
        if self.action_client:
            print("   Checking FollowJointTrajectory action...")
            if self.action_client.wait_for_server(timeout_sec=3.0):
                self._controller_type = 'action'
                print("✅ Detected: FollowJointTrajectory action interface")
                return 'action'
            else:
                print("   FollowJointTrajectory action not available")

        # Try trajectory topic
        print("   Checking trajectory topic interface...")
        topic_names = [t[0] for t in self.node.get_topic_names_and_types()]
        if '/panda_arm_controller/joint_trajectory' in topic_names:
            self._controller_type = 'trajectory_topic'
            print("✅ Detected: JointTrajectory topic interface")
            return 'trajectory_topic'

        # Try position controller topic
        if '/panda_position_controller/commands' in topic_names:
            self._controller_type = 'position_topic'
            print("✅ Detected: Position controller topic interface")
            return 'position_topic'

        # Default to trajectory topic (most common with franka_ros2)
        print("⚠️ No specific controller detected, defaulting to trajectory topic")
        self._controller_type = 'trajectory_topic'
        return 'trajectory_topic'

    def get_current_joint_positions(self) -> Optional[List[float]]:
        """Get current joint positions. Returns None if not available."""
        if not self._ensure_ros_init():
            return None

        if self.current_joint_positions is None:
            print("⏳ Waiting for joint state data...")
            start_time = time.time()
            while self.current_joint_positions is None and (time.time() - start_time) < 5.0:
                try:
                    rclpy.spin_once(self.node, timeout_sec=0.1)
                except Exception:
                    break

            if self.current_joint_positions is None:
                print("⚠️ Could not get current joint positions")
                return None

        return self.current_joint_positions.copy()

    def validate_joint_angles(self, joint_angles: List[float]) -> Dict:
        """
        Validate joint angles against Panda limits.

        Returns dict with 'valid' bool and 'warnings' list.
        """
        if len(joint_angles) != 7:
            return {'valid': False, 'warnings': [f'Expected 7 joint angles, got {len(joint_angles)}']}

        warnings = []
        for i, (name, angle) in enumerate(zip(PANDA_JOINT_NAMES, joint_angles)):
            lower, upper = PANDA_JOINT_LIMITS[name]
            if angle < lower or angle > upper:
                warnings.append(
                    f"Joint {name} ({i+1}): {angle:.4f} rad is outside limits "
                    f"[{lower:.4f}, {upper:.4f}]"
                )

        return {
            'valid': len(warnings) == 0,
            'warnings': warnings
        }

    def publish_joint_command(self, joint_positions: List[float], duration_sec: float = 0.1) -> bool:
        """
        Publish joint trajectory for real-time teleop (non-blocking).

        Always uses the trajectory TOPIC (not the action interface) for streaming.
        Matches the working simulation approach: position-only, no time_from_start,
        no velocities, no accelerations. The JointTrajectoryController handles
        interpolation internally.
        """
        if not self._ensure_ros_init():
            return False
        validation = self.validate_joint_angles(joint_positions)
        if not validation['valid']:
            return False
        try:
            msg = JointTrajectory()
            msg.joint_names = list(PANDA_JOINT_NAMES)
            point = JointTrajectoryPoint()
            point.positions = list(joint_positions)
            # No time_from_start, no velocities, no accelerations
            # This lets the trajectory controller handle interpolation smoothly
            msg.points = [point]
            self.trajectory_publisher.publish(msg)
            return True
        except Exception as e:
            print(f"⚠️ Publish failed: {e}")
            return False

    def send_joint_command(self, joint_positions: List[float], duration_sec: float = 3.0) -> bool:
        """
        Send arm command to move to target joint positions.

        Auto-detects the available controller type and uses the appropriate interface.

        Args:
            joint_positions: List of 7 joint positions in radians
            duration_sec: Duration in seconds for the movement
        """
        if not self._ensure_ros_init():
            return False

        # Validate joint angles
        validation = self.validate_joint_angles(joint_positions)
        if not validation['valid']:
            for w in validation['warnings']:
                print(f"❌ {w}")
            print("❌ Joint angle validation failed. Aborting for safety.")
            return False

        controller_type = self._detect_controller_type()

        try:
            if controller_type == 'action':
                return self._send_via_action(joint_positions, duration_sec)
            elif controller_type == 'trajectory_topic':
                return self._send_via_trajectory_topic(joint_positions, duration_sec)
            elif controller_type == 'position_topic':
                return self._send_via_position_topic(joint_positions, duration_sec)
            else:
                print(f"❌ Unknown controller type: {controller_type}")
                return False
        except Exception as e:
            print(f"⚠️ Error sending arm command: {e}")
            return False

    def _send_via_action(self, joint_positions: List[float], duration_sec: float) -> bool:
        """Send arm command via FollowJointTrajectory action"""
        try:
            goal_msg = FollowJointTrajectory.Goal()
            trajectory = JointTrajectory()
            trajectory.joint_names = list(PANDA_JOINT_NAMES)

            point = JointTrajectoryPoint()
            point.positions = list(joint_positions)
            point.velocities = [0.0] * 7
            point.accelerations = [0.0] * 7
            point.time_from_start.sec = int(duration_sec)
            point.time_from_start.nanosec = int((duration_sec % 1) * 1e9)

            trajectory.points = [point]
            goal_msg.trajectory = trajectory

            if not self.action_client.wait_for_server(timeout_sec=3.0):
                print("⚠️ FollowJointTrajectory action server not available")
                return False

            print(f"📤 Sending FollowJointTrajectory goal ({duration_sec:.1f}s)...")
            future = self.action_client.send_goal_async(goal_msg)
            rclpy.spin_until_future_complete(self.node, future, timeout_sec=10.0)

            if future.done():
                goal_handle = future.result()
                if goal_handle.accepted:
                    print("✅ Goal accepted, waiting for completion...")
                    result_future = goal_handle.get_result_async()
                    rclpy.spin_until_future_complete(
                        self.node, result_future,
                        timeout_sec=duration_sec + 10.0
                    )
                    if result_future.done():
                        result = result_future.result().result
                        if result.error_code == 0:
                            print("✅ Trajectory execution completed successfully")
                            return True
                        else:
                            print(f"⚠️ Trajectory failed with error code: {result.error_code}")
                            return False
                else:
                    print("⚠️ Trajectory goal rejected")
                    return False
            else:
                print("⚠️ Timeout sending trajectory goal")
                return False
        except Exception as e:
            print(f"⚠️ Error in action interface: {e}")
            return False

    def _send_via_trajectory_topic(self, joint_positions: List[float], duration_sec: float) -> bool:
        """Send arm command via JointTrajectory topic"""
        try:
            msg = JointTrajectory()
            msg.joint_names = list(PANDA_JOINT_NAMES)

            point = JointTrajectoryPoint()
            point.positions = list(joint_positions)
            point.time_from_start.sec = int(duration_sec)
            point.time_from_start.nanosec = int((duration_sec % 1) * 1e9)

            msg.points = [point]

            print(f"📤 Publishing JointTrajectory to /panda_arm_controller/joint_trajectory...")
            self.trajectory_publisher.publish(msg)

            # Spin to ensure message is sent
            for _ in range(10):
                rclpy.spin_once(self.node, timeout_sec=0.05)

            print(f"✅ Trajectory command published. Waiting {duration_sec:.1f}s for execution...")
            time.sleep(duration_sec + 0.5)
            return True
        except Exception as e:
            print(f"⚠️ Error in trajectory topic interface: {e}")
            return False

    def _send_via_position_topic(self, joint_positions: List[float], duration_sec: float) -> bool:
        """Send arm command via position controller topic (continuous publishing)"""
        try:
            msg = Float64MultiArray()
            msg.data = list(joint_positions)

            print(f"📤 Publishing to /panda_position_controller/commands for {duration_sec:.1f}s...")

            publish_rate = 20.0  # Hz
            sleep_time = 1.0 / publish_rate
            start_time = time.time()
            iteration = 0

            while (time.time() - start_time) < duration_sec:
                self.position_publisher.publish(msg)
                rclpy.spin_once(self.node, timeout_sec=0.001)
                iteration += 1
                elapsed = time.time() - start_time
                if elapsed < duration_sec - sleep_time:
                    time.sleep(sleep_time)

            print(f"✅ Published {iteration} position commands over {duration_sec:.1f}s")
            return True
        except Exception as e:
            print(f"⚠️ Error in position topic interface: {e}")
            return False


# Global controller instances
_gripper_controller = RealRobotGripperController()
_arm_controller = RealRobotArmController()


def control_gripper(action: str, force: float = 0.5) -> Dict:
    """
    Control the real robot gripper.

    Args:
        action: "open", "close", or "half"
        force: Not used for Franka native action (preserved for API compatibility)
    """
    print(f"🤏 Gripper action: {action}")

    try:
        if action == "open":
            success = _gripper_controller.move_gripper(0.08, speed=0.1)
            return {"success": success, "action": "opened",
                    "message": "Gripper opened" + (" successfully" if success else " (failed)")}
        elif action in ["close", "grasp"]:
            success = _gripper_controller.move_gripper(0.0, speed=0.1)
            return {"success": success, "action": action,
                    "message": f"Gripper {action}d" + (" successfully" if success else " (failed)")}
        elif action == "half":
            success = _gripper_controller.move_gripper(0.04, speed=0.1)
            return {"success": success, "action": "half_open",
                    "message": "Gripper half-opened" + (" successfully" if success else " (failed)")}
        else:
            return {"success": False, "error": f"Unknown gripper action: {action}"}
    except Exception as e:
        return {"success": False, "error": f"Gripper control failed: {str(e)}"}


def get_current_arm_position(verbose: bool = True) -> Dict:
    """Get the current position of the real robot arm."""
    if verbose:
        print("📊 Getting current arm position...")

    try:
        if not _arm_controller._initialized:
            _arm_controller._ensure_ros_init()

        current_positions = _arm_controller.get_current_joint_positions()

        if current_positions is not None:
            return {
                "success": True,
                "action": "position_read",
                "message": "Current arm position retrieved successfully",
                "joint_angles": current_positions,
                "formatted": f"[{', '.join([f'{pos:.3f}' for pos in current_positions])}]"
            }
        else:
            return {
                "success": False,
                "error": "Could not read current joint positions from real robot"
            }
    except Exception as e:
        return {"success": False, "error": f"Failed to get current arm position: {str(e)}"}


def cleanup():
    """Cleanup ROS2 resources"""
    global _gripper_controller, _arm_controller, _ros_context_initialized

    if _gripper_controller._initialized and _gripper_controller.node:
        _gripper_controller.node.destroy_node()

    if _arm_controller._initialized and _arm_controller.node:
        _arm_controller.node.destroy_node()

    if _ros_context_initialized and rclpy.ok():
        rclpy.shutdown()
        _ros_context_initialized = False


if __name__ == "__main__":
    print("🧪 Testing Real Robot Control Module...")
    print("=" * 60)

    # Run diagnostics
    print("\n📡 Checking franka_ros2 connectivity...")
    checks = check_franka_running()
    for check, status in checks.items():
        icon = "✅" if status else "❌"
        print(f"   {icon} {check}: {status}")

    if not checks.get('joint_states', False):
        print("\n⚠️ Joint states not available. Is franka_ros2 running on the control PC?")
        print("   Start it with: ros2 launch franka_bringup franka.launch.py robot_ip:=192.168.1.101")
        sys.exit(1)

    try:
        # Test getting current arm position
        result = get_current_arm_position()
        print(f"\n📍 Current arm position: {result}")

    except KeyboardInterrupt:
        print("\n👋 Interrupted")
    finally:
        cleanup()
