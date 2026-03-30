#!/usr/bin/env python3
"""
Robot Control Tools for HRC DS-RFM

This module contains all the robot control functions that can be converted to tools
for use with the language agent. These functions simulate robot actions and can be
easily modified to interface with real robot hardware or Isaac Sim.
"""

import time
from typing import Dict, List, Optional
import rclpy
from rclpy.action import ActionClient
from control_msgs.action import GripperCommand
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray
from rclpy.node import Node
import subprocess

from world_model import WorldModel


world = WorldModel()

# Get the kinematic solver
from lerobot_teleoperator_devices.processors.delta_to_joints import _make_default_teleop_action_processor_with_keyboard_patch
from lerobot.model.kinematics import RobotKinematics
from pathlib import Path
import tempfile
# could have a cleaner way to get the urdf path(?)
original_urdf = Path("/home/student/lerobot-ros-agent/isaac_franka_moveit_perception/src/panda_description/urdf/panda.urdf")
urdf_text = original_urdf.read_text()
package_dir = "/home/student/lerobot-ros-agent/isaac_franka_moveit_perception/src/panda_description"
urdf_text = urdf_text.replace("package://panda_description", package_dir)
temp_urdf = tempfile.NamedTemporaryFile(mode="w", suffix=".urdf", delete=False)
temp_urdf.write(urdf_text)
temp_urdf.flush()

kinematics_engine = RobotKinematics(
    urdf_path=temp_urdf.name,
    target_frame_name="panda_hand",
    joint_names=[
        "panda_joint1", "panda_joint2", "panda_joint3",
        "panda_joint4", "panda_joint5", "panda_joint6", "panda_joint7"
    ]
)

# ============================================================================
# LEROBOT/VLA IMPORTS - For execute_vla_task function
# ============================================================================
import os
import torch
import numpy as np

# Try to import lerobot components
try:
    from lerobot.policies.factory import get_policy_class, make_pre_post_processors
    from lerobot.policies.utils import build_inference_frame, make_robot_action
    from lerobot.datasets.utils import hw_to_dataset_features
    from lerobot.utils.utils import get_safe_torch_device
    from lerobot.robots.utils import make_robot_from_config
    from lerobot_robot_ros import (
        PandaROSPositionConfig,
        PandaROSConfig,
        PandaROSCartesianConfig
    )
    LEROBOT_AVAILABLE = True
    ROBOT_AVAILABLE = True
except ImportError as e:
    LEROBOT_AVAILABLE = False
    ROBOT_AVAILABLE = False
    LEROBOT_IMPORT_ERROR = str(e)
    ROBOT_IMPORT_ERROR = str(e)

# ============================================================================
# VLA TOOL GLOBAL VARIABLES - For caching policy and robot
# ============================================================================
_cached_policy = None
_cached_preprocessor = None
_cached_postprocessor = None
_cached_robot = None
_cached_device = None
_cached_policy_type = None
_cached_policy_path = None
_cached_config = None  # Cache for loaded config

# Global ROS2 context management - robust approach
_shared_executor = None
_shared_context = None

def get_shared_executor():
    """Get or create a shared ROS2 executor"""
    global _shared_executor, _shared_context
    try:
        if not rclpy.ok():
            rclpy.init()
            print("🔧 ROS2 context initialized for robot tools")
        
        if _shared_executor is None:
            from rclpy.executors import SingleThreadedExecutor
            _shared_executor = SingleThreadedExecutor()
            print("🔧 Shared ROS2 executor created")
            
        return _shared_executor
    except Exception as e:
        print(f"⚠️ Warning: Could not create shared executor: {e}")
        return None

def ensure_rclpy_init():
    """Ensure rclpy is initialized only once"""
    try:
        if not rclpy.ok():
            rclpy.init()
            print("🔧 ROS2 context initialized for robot tools")
        return True
    except Exception as e:
        print(f"⚠️ Warning: Could not initialize ROS2 context: {e}")
        return False

class GripperController:
    """ROS2-based gripper controller"""
    def __init__(self):
        self.node = None
        self.action_client = None
        self._initialized = False
    
    def _ensure_ros_init(self):
        if not self._initialized:
            try:
                if not ensure_rclpy_init():
                    return False
                
                self.node = Node(f'gripper_controller_{int(time.time())}')
                self.action_client = ActionClient(self.node, GripperCommand, '/panda_hand_controller/gripper_cmd')
                self._initialized = True
                print("🤖 ROS2 gripper controller initialized")
            except Exception as e:
                print(f"⚠️ Warning: Could not initialize ROS2 gripper controller: {e}")
                return False
        return True
    def _send_gripper_command(self, position: float, max_effort: float) -> bool:
        if not self._ensure_ros_init():
            return False
        
        # Try ROS2 CLI as fallback to avoid context conflicts
        try:
            import subprocess
            import json
            
            # Use ROS2 CLI to send the command - this avoids context conflicts
            # for real panda
            cmd = [
                'ros2', 'action', 'send_goal', 
                '/panda_gripper/gripper_action',
                'control_msgs/action/GripperCommand',
                f'{{"command": {{"position": {position}, "max_effort": {max_effort}}}}}',
                '--feedback'  # Get feedback
            ]
            
            print(f"🔧 Sending gripper command via ROS2 CLI: position={position}, effort={max_effort}")
            
            print(f"copmmand: {cmd}")
            # Run command with timeout
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=5.0
            )

            
            if result.returncode == 0:
                print("✅ Gripper command sent successfully via ROS2 CLI")
                return True
            else:
                print(f"⚠️ ROS2 CLI command failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("⚠️ ROS2 CLI command timeout")
            return False
        except Exception as e:
            print(f"⚠️ ROS2 CLI fallback failed: {e}")
            return False


class ArmController:
    """ROS2-based arm controller"""
    def __init__(self):
        self.node = None
        self.action_client = None
        self.joint_state_subscription = None
        self.position_publisher = None  # Publisher for position controller topic
        self.current_joint_positions = None
        self._initialized = False
        self.action_server_name = None  # Store discovered action server name
        self._action_server_available = None  # Cache: True/False/None (not checked)
        self._use_position_topic_directly = False  # Skip action server, use position topic directly
    
    def _discover_arm_action_server(self):
        """Discover available FollowJointTrajectory action servers"""
        print("🔍 Discovering arm action servers...")
        
        if not ensure_rclpy_init():
            print("❌ ROS2 not initialized, cannot discover action servers")
            return None
        
        # Common controller names to try
        possible_names = [
            '/panda_arm_controller/follow_joint_trajectory',
            '/panda_controller/follow_joint_trajectory',
            '/arm_controller/follow_joint_trajectory',
            '/joint_trajectory_controller/follow_joint_trajectory',
            '/position_controller/follow_joint_trajectory',
            '/trajectory_controller/follow_joint_trajectory',
            
        ]
        
        # Try to discover via ROS2 CLI first
        try:
            import subprocess
            print("📋 Listing all ROS2 actions...")
            result = subprocess.run(
                ['ros2', 'action', 'list'],
                capture_output=True,
                text=True,
                timeout=5.0
            )
            
            if result.returncode == 0:
                print(result)
                available_actions = [line.strip() for line in result.stdout.split('\n') if line.strip()]
                print(f"📋 Found {len(available_actions)} action servers:")
                for action in available_actions:
                    print(f"   - {action}")
                
                # Look for FollowJointTrajectory actions
                trajectory_actions = []
                for action in available_actions:
                    if 'follow_joint_trajectory' in action.lower():
                        trajectory_actions.append(action)
                        print(f"🔍 Found trajectory action: {action}")
                        # Check if it's one of our expected names or contains 'panda' or 'arm'
                        if any(name in action for name in ['panda', 'arm', 'controller']):
                            print(f"✅ Using discovered action server: {action}")
                            return action
                
                if trajectory_actions:
                    # Use the first trajectory action found even if it doesn't match our expected names
                    print(f"✅ Using first trajectory action found: {trajectory_actions[0]}")
                    return trajectory_actions[0]
                else:
                    print("⚠️ No trajectory actions found in action list")
            else:
                print(f"⚠️ Failed to list actions via CLI (return code {result.returncode})")
                if result.stderr:
                    print(f"   Error: {result.stderr}")
        except subprocess.TimeoutExpired:
            print("⚠️ Timeout while listing actions via CLI")
        except FileNotFoundError:
            print("⚠️ ROS2 CLI not found - is ROS2 sourced?")
        except Exception as e:
            print(f"⚠️ Could not list actions via CLI: {e}")
        
        # Try each possible name by checking server availability
        print("🔍 Checking common controller names...")
        temp_node = None
        try:
            temp_node = Node(f'arm_discovery_{int(time.time())}')
            for name in possible_names:
                print(f"   Checking: {name}")
                client = ActionClient(temp_node, FollowJointTrajectory, name)
                if client.wait_for_server(timeout_sec=1.0):
                    print(f"✅ Found working action server: {name}")
                    return name
                else:
                    print(f"   ❌ Not available")
        except Exception as e:
            print(f"⚠️ Error during discovery: {e}")
        finally:
            if temp_node:
                try:
                    temp_node.destroy_node()
                except:
                    pass
        
        print("⚠️ Could not discover arm action server")
        print("💡 Tip: Make sure ROS2 is sourced and the robot simulation/controller is running")
        print(f"   Will try default: {possible_names[0]}")
        return possible_names[0]  # Return default
    
    def _ensure_ros_init(self):
        if not self._initialized:
            try:
                if not ensure_rclpy_init():
                    return False
                
                # Discover action server if not already discovered (skip if preloaded)
                if self.action_server_name is None:
                    # Check if this is first-time init without preload
                    global _arm_controller_preloaded
                    if not _arm_controller_preloaded:
                        print("⚠️ Arm controller not preloaded - running discovery (this may take a few seconds)")
                        print("   💡 Tip: Use preload_arm_controller() at startup for faster execution")
                    self.action_server_name = self._discover_arm_action_server()
                    if self.action_server_name is None:
                        print("❌ Could not discover arm action server")
                        return False
                else:
                    # Action server already set (e.g., from preload)
                    print(f"📍 Using pre-configured action server: {self.action_server_name}")
                    
                self.node = Node(f'arm_controller_{int(time.time())}')
                self.action_client = ActionClient(self.node, FollowJointTrajectory, self.action_server_name)
                # Also create publisher for position controller topic (fallback method)
                self.position_publisher = self.node.create_publisher(
                    Float64MultiArray,
                    '/panda_position_controller/commands',
                    10
                )
                self.joint_state_subscription = self.node.create_subscription(
                    JointState,
                    '/joint_states',
                    self._joint_state_callback,
                    10
                )
                self._initialized = True
                print(f"🤖 ROS2 arm controller initialized with: {self.action_server_name}")
                print("   Position controller topic publisher ready: /panda_position_controller/commands")
            except Exception as e:
                print(f"⚠️ Warning: Could not initialize ROS2 arm controller: {e}")
                return False
        return True
    def _joint_state_callback(self, msg):
        try:
            panda_joints = ['panda_joint1', 'panda_joint2', 'panda_joint3', 'panda_joint4', 'panda_joint5', 'panda_joint6', 'panda_joint7']
            current_positions = []
            for joint_name in panda_joints:
                if joint_name in msg.name:
                    idx = msg.name.index(joint_name)
                    current_positions.append(msg.position[idx])
                else:
                    current_positions.append(0.0)
            if len(current_positions) == 7:
                self.current_joint_positions = current_positions
        except Exception as e:
            print(f"⚠️ Error processing joint state: {e}")
    def _get_current_joint_positions(self) -> list:
        if self.current_joint_positions is None:
            print("⏳ Waiting for joint state data...")
            start_time = time.time()
            while self.current_joint_positions is None and (time.time() - start_time) < 5.0:
                try:
                    rclpy.spin_once(self.node, timeout_sec=0.1)
                except Exception:
                    break
            if self.current_joint_positions is None:
                print("⚠️ Could not get current joint positions, using default home")
                return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        return self.current_joint_positions.copy()
    def _send_arm_command(self, joint_positions: list) -> bool:
        if not self._ensure_ros_init():
            return False
        
        # FAST PATH: If configured to use position topic directly, skip action server entirely
        if self._use_position_topic_directly:
            return self._send_arm_command_position_topic(joint_positions)
        
        # CACHED PATH: If we already know action server is unavailable, skip checking
        if self._action_server_available is False:
            return self._send_arm_command_position_topic(joint_positions)
        
        # First try using Python ActionClient API
        try:
            # Only check action server if we haven't cached the result
            if self._action_server_available is None:
                print(f"🔍 Checking if action server is available: {self.action_server_name}")
                self._action_server_available = self.action_client.wait_for_server(timeout_sec=1.0)  # Reduced from 3.0s
                if not self._action_server_available:
                    print(f"⚠️ Arm action server '{self.action_server_name}' not responding (cached for future calls)")
                    return self._send_arm_command_position_topic(joint_positions)
            
            # Create trajectory goal
            goal = FollowJointTrajectory.Goal()
            goal.trajectory.joint_names = [
                'panda_joint1', 'panda_joint2', 'panda_joint3', 'panda_joint4', 
                'panda_joint5', 'panda_joint6', 'panda_joint7'
            ]
            
            point = JointTrajectoryPoint()
            point.positions = joint_positions
            point.velocities = [0.0] * 7
            point.accelerations = [0.0] * 7
            point.time_from_start.sec = 3
            point.time_from_start.nanosec = 0
            
            goal.trajectory.points = [point]
            
            print(f"🔧 Sending arm command via ROS2 API: {[f'{pos:.3f}' for pos in joint_positions]}")
            
            # Send goal and wait for result
            future = self.action_client.send_goal_async(goal)
            
            # Spin with timeout
            start_time = time.time()
            while not future.done() and (time.time() - start_time) < 5.0:
                rclpy.spin_once(self.node, timeout_sec=0.1)
            
            if not future.done():
                print("⚠️ Arm command goal send timeout, trying position controller topic...")
                self._action_server_available = False  # Cache failure
                return self._send_arm_command_position_topic(joint_positions)
            
            goal_handle = future.result()
            if not goal_handle.accepted:
                print(f"⚠️ Arm command goal rejected, trying position controller topic...")
                self._action_server_available = False  # Cache failure
                return self._send_arm_command_position_topic(joint_positions)
            
            # Wait for result
            result_future = goal_handle.get_result_async()
            start_time = time.time()
            while not result_future.done() and (time.time() - start_time) < 20.0:
                rclpy.spin_once(self.node, timeout_sec=0.1)
            
            if result_future.done():
                result = result_future.result().result
                if result.error_code == FollowJointTrajectory.Result.SUCCESSFUL:
                    print("✅ Arm command executed successfully via ROS2 API")
                    return True
                else:
                    print(f"⚠️ Arm command failed with error code {result.error_code}, trying position controller topic...")
                    return self._send_arm_command_position_topic(joint_positions)
            else:
                print("⚠️ Arm command result timeout, trying position controller topic...")
                return self._send_arm_command_position_topic(joint_positions)
                
        except Exception as e:
            print(f"⚠️ ROS2 API arm command failed: {e}, trying position controller topic...")
            self._action_server_available = False  # Cache failure
            return self._send_arm_command_position_topic(joint_positions)
    
    def _send_arm_command_position_topic(self, joint_positions: list) -> bool:
        """Fast method using position controller topic (fire-and-forget)"""
        try:
            if not self._initialized or self.position_publisher is None:
                print("⚠️ Position publisher not initialized, trying CLI fallback...")
                return self._send_arm_command_cli(joint_positions)
            
            print(f"⚡ Sending arm command via position controller topic: {[f'{pos:.3f}' for pos in joint_positions]}")
            
            # Create Float64MultiArray message
            msg = Float64MultiArray()
            msg.data = joint_positions
            
            # Publish the command
            self.position_publisher.publish(msg)
            
            # Minimal spin to ensure publish (reduced from 10 iterations to 2)
            for _ in range(2):
                rclpy.spin_once(self.node, timeout_sec=0.01)  # Reduced from 0.1s to 0.01s
            
            print("✅ Arm command sent via position controller topic")
            return True
            
        except Exception as e:
            print(f"⚠️ Position controller topic method failed: {e}, trying CLI fallback...")
            return self._send_arm_command_cli(joint_positions)
    
    def _send_arm_command_cli(self, joint_positions: list) -> bool:
        """Fallback method using ROS2 CLI"""
        try:
            import subprocess
            import json
            
            # Use discovered action server name, or default if not discovered
            action_server = self.action_server_name or '/panda_arm_controller/follow_joint_trajectory'
            
            # First verify ROS2 CLI is available
            try:
                check_result = subprocess.run(
                    ['ros2', '--help'],
                    capture_output=True,
                    text=True,
                    timeout=2.0
                )
                if check_result.returncode != 0:
                    print("❌ ROS2 CLI not available - is ROS2 sourced?")
                    return False
            except FileNotFoundError:
                print("❌ ROS2 CLI not found - is ROS2 installed and sourced?")
                print("   Try: source /opt/ros/humble/setup.bash (or your ROS2 distro)")
                return False
            
            # Create trajectory goal for ROS2 CLI
            trajectory_goal = {
                "trajectory": {
                    "joint_names": [
                        'panda_joint1', 'panda_joint2', 'panda_joint3', 'panda_joint4', 
                        'panda_joint5', 'panda_joint6', 'panda_joint7'
                    ],
                    "points": [
                        {
                            "positions": joint_positions,
                            "velocities": [0.0] * 7,
                            "accelerations": [0.0] * 7,
                            "time_from_start": {"sec": 3, "nanosec": 0}
                        }
                    ]
                }
            }
            
            # Convert to JSON string for ROS2 CLI
            goal_json = json.dumps(trajectory_goal)
            
            print(f"🔧 Sending arm command via ROS2 CLI to {action_server}: {[f'{pos:.3f}' for pos in joint_positions]}")
            
            cmd = [
                'ros2', 'action', 'send_goal',
                action_server,
                'control_msgs/action/FollowJointTrajectory',
                goal_json,
                '--feedback'
            ]
            
            # Run command with extended timeout for arm movements
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=20.0  # Longer timeout for arm movements
            )
            
            if result.returncode == 0:
                print("✅ Arm command sent successfully via ROS2 CLI")
                return True
            else:
                print(f"⚠️ ROS2 CLI arm command failed (return code {result.returncode})")
                if result.stderr:
                    print(f"   stderr: {result.stderr}")
                if result.stdout:
                    print(f"   stdout: {result.stdout}")
                print(f"💡 Action server '{action_server}' may not exist or is not responding")
                print("   Try running: ros2 action list")
                return False
                
        except subprocess.TimeoutExpired:
            print(f"⚠️ ROS2 CLI arm command timeout after 20 seconds")
            print(f"💡 Action server '{action_server}' is not responding")
            print("   Possible causes:")
            print("   1. Robot simulation/controller is not running")
            print("   2. Action server name is incorrect")
            print("   3. Network/DDS communication issue")
            print("   Try running: ros2 action list")
            return False
        except Exception as e:
            print(f"⚠️ ROS2 CLI arm fallback failed: {e}")
            return False


# Global controller instances
_gripper_controller = GripperController()
_arm_controller = ArmController()
_arm_controller_preloaded = False  # Track if arm controller was preloaded
_gripper_controller_preloaded = False  # Track if gripper controller was preloaded

# Cached image provider for scan_environment (avoids creating new nodes each call)
_cached_image_provider = None
_image_provider_preloaded = False


def preload_gripper_controller() -> bool:
    """
    Pre-load gripper controller at startup.
    
    Returns:
        True if successful, False if failed
    """
    global _gripper_controller, _gripper_controller_preloaded
    
    try:
        print("🔄 Pre-loading gripper controller...")
        
        if not ensure_rclpy_init():
            print("⚠️ ROS2 not available, gripper controller preload skipped")
            return False
        
        if _gripper_controller._ensure_ros_init():
            _gripper_controller_preloaded = True
            print("✅ Gripper controller pre-loaded successfully")
            return True
        else:
            print("⚠️ Warning: Gripper controller initialization failed during preload")
            return False
            
    except Exception as e:
        print(f"⚠️ Warning: Failed to pre-load gripper controller: {e}")
        return False


def preload_image_provider() -> bool:
    """
    Pre-load the ImageProvider node at startup to avoid creating new nodes each scan.
    
    This prevents ROS2 "wait set index too big" errors that occur when multiple
    ImageProvider nodes are created without proper cleanup.
    
    Returns:
        True if successful, False if failed
    """
    global _cached_image_provider, _image_provider_preloaded
    
    try:
        print("🔄 Pre-loading image provider...")
        
        # Ensure ROS2 is initialized
        if not ensure_rclpy_init():
            print("⚠️ ROS2 not available, image provider preload skipped")
            return False
        
        # Import and create image provider
        from image_getter import ImageProvider
        
        # Create a unique node name to avoid conflicts
        _cached_image_provider = ImageProvider()
        _image_provider_preloaded = True
        
        print("✅ Image provider pre-loaded successfully")
        return True
        
    except Exception as e:
        print(f"⚠️ Warning: Failed to pre-load image provider: {e}")
        return False


def _get_image_provider():
    """Get the cached image provider or create a new one if not cached."""
    global _cached_image_provider, _image_provider_preloaded
    
    if _cached_image_provider is not None:
        return _cached_image_provider, False  # Return cached, don't destroy later
    
    # Create new one (will need cleanup)
    from image_getter import ImageProvider
    print("⚠️ Image provider not preloaded - creating new instance")
    print("   💡 Tip: Use preload_image_provider() at startup for better stability")
    return ImageProvider(), True  # Return new instance, should destroy after use


def preload_all_controllers(
    discover_arm_server: bool = False,
    use_position_topic_directly: bool = True
) -> dict:
    """
    Pre-load all robot controllers at startup for fastest execution.
    
    This is the recommended way to initialize the robot system - call this once
    at startup to eliminate all initialization delays during operation.
    
    Args:
        discover_arm_server: If True, run action server discovery. Default False (fastest).
        use_position_topic_directly: If True, skip action server checks entirely. Default True.
    
    Returns:
        Dictionary with status of each controller preload
    """
    print("🚀 Pre-loading all robot controllers...")
    
    results = {
        "gripper": preload_gripper_controller(),
        "arm": preload_arm_controller(
            discover_if_not_specified=discover_arm_server,
            use_position_topic_directly=use_position_topic_directly
        ),
        "image_provider": preload_image_provider(),
    }
    
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    if success_count == total_count:
        print(f"✅ All {total_count} controllers pre-loaded successfully!")
    else:
        print(f"⚠️ {success_count}/{total_count} controllers pre-loaded")
    
    return results


def preload_arm_controller(
    action_server_name: Optional[str] = None,
    discover_if_not_specified: bool = True,
    use_position_topic_directly: bool = True
) -> bool:
    """
    Pre-load arm controller at startup to avoid delays during first execution.

    This function initializes the arm controller and discovers the action server
    so that control_arm_home_position and other arm commands execute immediately
    without discovery delays.

    Similar to preload_vla_policy(), this should be called at startup.

    Args:
        action_server_name: Specific action server name to use. If None and 
                           discover_if_not_specified is True, will discover automatically.
                           If None and discover_if_not_specified is False, uses default.
        discover_if_not_specified: If True and action_server_name is None, run discovery.
                                  If False, skip discovery and use position controller topic fallback.
        use_position_topic_directly: If True, skip action server checks entirely and always
                                    use position controller topic (fastest mode). Default: True.

    Returns:
        True if successful, False if failed
    """
    global _arm_controller, _arm_controller_preloaded
    
    try:
        print("🔄 Pre-loading arm controller...")
        
        # Ensure ROS2 is initialized
        if not ensure_rclpy_init():
            print("⚠️ ROS2 not available, arm controller preload skipped")
            return False
        
        # Set action server name if provided
        if action_server_name is not None:
            print(f"   Using specified action server: {action_server_name}")
            _arm_controller.action_server_name = action_server_name
        elif discover_if_not_specified:
            # Run discovery once at startup
            print("   Discovering action servers...")
            _arm_controller.action_server_name = _arm_controller._discover_arm_action_server()
        else:
            # Skip discovery, use default (will fall back to position controller topic)
            print("   Skipping discovery, using position controller topic directly (fast mode)")
            _arm_controller.action_server_name = '/panda_arm_controller/follow_joint_trajectory'
        
        # Enable fast mode - skip action server checks entirely
        if use_position_topic_directly:
            _arm_controller._use_position_topic_directly = True
            print("   ⚡ Fast mode enabled: using position controller topic directly")
        
        # Initialize the controller (creates node, action client, publishers)
        if _arm_controller._ensure_ros_init():
            _arm_controller_preloaded = True
            print(f"✅ Arm controller pre-loaded successfully")
            print(f"   Position topic: /panda_position_controller/commands")
            return True
        else:
            print("⚠️ Warning: Arm controller initialization failed during preload")
            return False
            
    except Exception as e:
        print(f"⚠️ Warning: Failed to pre-load arm controller: {e}")
        print(f"   Arm controller will be initialized on first use instead")
        return False


def get_world_model() -> Dict:
    """Get the current world model with all known objects and their locations.
    
    Use this tool to LIST or VIEW objects that have already been detected and stored 
    in the world model. This does NOT scan for new objects - it shows what's already known.
    
    Returns:
        Dictionary with world model information and current state
    """
    print("🌍 Getting world model")
    
    try:
        # Get world context
        world_ctx = world.to_string()
        
        # Create a user-friendly message about objects
        if world.objects:
            object_list = []
            for obj_name, (location, coords) in world.objects.items():
                if coords is not None:
                    object_list.append(f"{obj_name} at ({coords[0]:.2f}, {coords[1]:.2f}, {coords[2]:.2f})")
                else:
                    object_list.append(f"{obj_name} at {location}")
            
            objects_summary = f"Found {len(world.objects)} object(s): " + ", ".join(object_list)
        else:
            objects_summary = "No objects currently known in the world model"
        
        return {
            "success": True,
            "world_model": world_ctx,
            "objects_summary": objects_summary,
            "message": objects_summary
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to get world model: {str(e)}",
            "message": "World model retrieval failed"
        }


def move_robot_arm_delta(cur_joint_pos: List[float], dx: float, dy: float, dz: float, speed: float = 1.0) -> Dict:
    """Move the robot arm by given positional deltas. Requires current robot position in radians.

    Args:
        cur_joint_pos: current joint angles
        dx: delta in X-coordinate in meters, + is forward, - is backward
        dy: delta in Y-coordinate in meters, + is forward, - is backward
        dz: delta in Z-coordinate in meters, + is forward, - is backward
        speed: Movement speed (0.1-2.0)
    
    Returns:
        Dictionary with success status and target position in radians
    """
    # Run forward-kinematics to determine current cartesian position
    print(f"current joint position: {cur_joint_pos}")
    joint_obs_deg = np.rad2deg(np.array(cur_joint_pos, dtype=float))
    current_pose = kinematics_engine.forward_kinematics(joint_obs_deg)
    print(f"Current pose: {current_pose}")
    
    # Add deltas to current cartesian position
    desired_pose = current_pose.copy()
    desired_pose[:3, 3] += np.array([dx, dy, dz], dtype=float)
    print(f"Target pose: {desired_pose}")

    # Run inverse-kinematics to determine target joint positions
    target_joint_deg = kinematics_engine.inverse_kinematics(
        joint_obs_deg,
        desired_pose,
        position_weight=1.0,
        orientation_weight=0.05
    )
    
    # Execute movement
    target_joint_rad = np.deg2rad(target_joint_deg[:7]).tolist()
    print(f"Moving robot to: {target_joint_rad}")
    result = _move_robot_arm_joint_position(target_joint_rad)
    return result

# TODO: add constraints to prevent the prevent robot from moving out of boundary
def _move_robot_arm_joint_position(target_joint_positions):
    target_joint_positions = f"{target_joint_positions}"
    session_name = "robot_console"
    script_name = "switch_controllers.sh"
    script_path = f'/home/student/lerobot-ros-agent/{script_name}'

    try:
        # deactivate move_to_home controller
        subprocess.run(["bash", script_path, "cartesian"])

        print(target_joint_positions)
        # Set the goal_position parameter on the controller
        subprocess.run([
            "ros2", "param", "set", 
            "/move_to_home_lerobot", "goal_position", target_joint_positions
        ], check=True, capture_output=True)

        subprocess.run(["bash", script_path, "home"])
        return {"success": True, "message": "Homing command sent to console"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def move_robot_arm(x: float, y: float, z: float, speed: float = 1.0) -> Dict:
    """Move the robot arm to the specified position.
    
    Args:
        x: X-coordinate in meters, + is forward, - is backward
        y: Y-coordinate in meters, + is left, - is right  
        z: Z-coordinate in meters, + is up, - is down
        speed: Movement speed (0.1-2.0)
    
    Returns:
        Dictionary with success status and position
    """
    print(f"🤖 Moving robot arm to position: x={x}, y={y}, z={z} at speed={speed}")
    time.sleep(0.5)  # Simulate movement time
    return {"success": True, "position": {"x": x, "y": y, "z": z}, "message": f"Moved to position ({x}, {y}, {z})"}


def control_gripper(action: str, force: float = 0.5) -> Dict:
    """Control the robot gripper using ROS2 action."""
    print(f"🤏 Gripper action: {action} with force: {force}")
    try:
        if action == "open":
            success = _gripper_controller._send_gripper_command(0.04, 50.0)
            if success:
                return {"success": True, "action": "opened", "message": "Gripper opened successfully via ROS2"}
            else:
                return {"success": False, "error": "Failed to open gripper via ROS2", "action": "open"}
        elif action in ["close", "grasp"]:
            max_effort = force * 50.0
            success = _gripper_controller._send_gripper_command(0.03, max_effort)
            if success:
                past = "closed" if action == "close" else "grasped"
                return {"success": True, "action": action, "force": force, "message": f"Gripper {past} successfully via ROS2 with force {force}"}
            else:
                return {"success": False, "error": f"Failed to {action} gripper via ROS2", "action": action, "force": force}
        else:
            return {"success": False, "error": f"Unknown gripper action: {action}"}
    except Exception as e:
        return {"success": False, "error": f"Gripper control failed: {str(e)}"}


# Something is wrong with this. It keeps reutrning the same thing
def get_current_arm_position() -> Dict:
    """Get the current position of the robot arm."""
    print("📊 Getting current arm position...")
    # try:
    #     if not _arm_controller._initialized:
    #         _arm_controller._ensure_ros_init()
    #     current_positions = _arm_controller._get_current_joint_positions()
    #     if current_positions != [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]:
    #         return {
    #             "success": True,
    #             "action": "position_read",
    #             "message": "Current arm position retrieved successfully",
    #             "joint_angles": current_positions,
    #             "formatted": f"[{', '.join([f'{pos:.3f}' for pos in current_positions])}]"
    #         }
    #     else:
    #         return {
    #             "success": False,
    #             "error": "Could not read current joint positions, using fallback values"
    #         }
    # except Exception as e:
    #     return {"success": False, "error": f"Failed to get current arm position: {str(e)}"}
    if not rclpy.ok():
        try:
            rclpy.init()
        except Exception as e:
            # Handle cases where init might still fail
            pass

    node = rclpy.create_node('franka_joint_reader')
    
    try:
        joint_positions = {}
        target_joints = [
            'panda_joint1', 'panda_joint2', 'panda_joint3',
            'panda_joint4', 'panda_joint5', 'panda_joint6', 'panda_joint7'
        ]

        def callback(msg):
            for name, pos in zip(msg.name, msg.position):
                if name in target_joints:
                    joint_positions[name] = pos

        sub = node.create_subscription(JointState, '/joint_states', callback, 10)
        
        start_time = time.time()
        # Use a shorter spin timeout to stay responsive
        while time.time() - start_time < 3.0:
            rclpy.spin_once(node, timeout_sec=0.1)
            if len(joint_positions) == 7:
                break

        if len(joint_positions) == 7:
            current_positions = [joint_positions[j] for j in target_joints]
            return {
                "success": True,
                "joint_angles": current_positions,
                "formatted": f"[{', '.join([f'{pos:.3f}' for pos in current_positions])}]"
            }
        else:
            return {"success": False, "error": "Timeout reading joints"}

    except Exception as e:
        return {"success": False, "error": str(e)}
    
    finally:
        # Always clean up the node, but keep rclpy alive for the next call
        node.destroy_node()

# TODO: make the move_to_home deactivation less hacky (don't need to activate the cartesian controller)
def control_arm_home_position() -> Dict:
    home_position = "[0.0329, 0.3870, -0.09267, -2.5056, 0.1815, 2.8588, 0.5796]"
    return _move_robot_arm_joint_position(home_position)




def scan_environment() -> Dict:
    """Perform a NEW scan of the environment to detect objects using the camera.
    
    Use this tool to DETECT and FIND new objects in the environment using computer vision.
    This captures a fresh image and processes it to identify objects. The detected objects
    will automatically update the world model. Use get_world_model() to list known objects.
    
    Returns:
        Dictionary with detected objects from real vision processing
    """
    print(f"🔍 Scanning environment for objects")
    
    should_destroy = False
    image_provider = None
    
    try:
        # Use real camera capture and image annotation
        from image_getter import capture_image
        from two_d_img_annotation_utils import annotate_image
        
        # Get cached image provider (or create new one if not preloaded)
        image_provider, should_destroy = _get_image_provider()
        
        # Camera intrinsics (hardcoded from the system)
        camera_intrinsics = {"fx": 634.09, "fy": 566.49, "cx": 640, "cy": 360}
        
        # Capture current image
        image, depth, view_matrix = capture_image(image_provider, require_view_matrix=False)
        
        if image is None:
            return {"success": False, "error": "Failed to capture image from camera"}
        
        # Annotate image to detect objects with optimized settings
        # You can override these defaults in two_d_img_annotation_utils.py VISION_CONFIG
        annotated_image, detected_objects = annotate_image(
            image, depth, camera_intrinsics, view_matrix, "check_target"
            # max_retries, enable_verification, batch_verification now use defaults from VISION_CONFIG
        )
        
        if annotated_image is None:
            return {"success": False, "error": "Failed to process image annotation"}
        
        # Process detected objects into scan results
        scan_results = _process_detected_objects(detected_objects)
        
        # Update world model with detected objects
        _update_world_model_with_objects(scan_results["objects"])
        
        # Create a descriptive message with detected objects
        if scan_results["objects"]:
            object_list = []
            for obj in scan_results["objects"]:
                pos = obj["position"]
                object_list.append(f"{obj['name']} at position ({pos['x']:.2f}, {pos['y']:.2f}, {pos['z']:.2f})")
            
            objects_text = ", ".join(object_list)
            message = f"Detected {len(scan_results['objects'])} object(s): {objects_text}. World model updated."
        else:
            message = "No objects detected in the current view"
        
        return {
            "success": True, 
            "results": scan_results,  
            "message": message,
            "image": annotated_image,
            "detected_objects": detected_objects
        }
        
    except Exception as e:
        print(f"Error during environment scan: {e}")
        return {"success": False, "error": f"Scan failed: {str(e)}"}
    
    finally:
        # Only destroy if we created a new instance (not using cached)
        if should_destroy and image_provider is not None:
            try:
                image_provider.destroy_node()
            except Exception:
                pass  # Ignore cleanup errors


def _process_detected_objects(detected_objects) -> Dict:
    """Process detected objects from image annotation into structured results."""
    if not detected_objects:
        return {"objects": []}
    
    objects = []
    
    for obj in detected_objects:
        # Handle dictionary format from annotate_image function
        if isinstance(obj, dict) and 'label' in obj and 'world_xyz' in obj:
            # Only process objects with valid world coordinates
            if obj['world_xyz'] is not None:
                obj_data = {
                    "name": obj['label'],
                    "position": {
                        "x": float(obj['world_xyz'][0]),
                        "y": float(obj['world_xyz'][1]), 
                        "z": float(obj['world_xyz'][2])
                    }
                }
                objects.append(obj_data)
        # Legacy support for object attributes (if any)
        elif hasattr(obj, 'name') and hasattr(obj, 'position'):
            obj_data = {
                "name": obj.name,
                "position": {
                    "x": obj.position[0] if len(obj.position) > 0 else 0.0,
                    "y": obj.position[1] if len(obj.position) > 1 else 0.0,
                    "z": obj.position[2] if len(obj.position) > 2 else 0.0
                }
            }
            objects.append(obj_data)
    
    return {"objects": objects}


def _update_world_model_with_objects(objects: List[Dict]) -> None:
    """Update the world model with detected objects from scan results."""
    global world
    
    # Clear existing objects to update with fresh scan data
    world.objects.clear()
    
    # Add each detected object to the world model
    for obj in objects:
        obj_name = obj["name"]
        position = obj["position"]
        world_coords = (position["x"], position["y"], position["z"])
        
        # Store object with location "environment" and world coordinates
        world.objects[obj_name] = ("environment", world_coords)
    
    print(f"🌍 Updated world model with {len(objects)} detected objects")


def get_robot_status() -> Dict:
    """Get the current status of the robot.
    
    Returns:
        Dictionary with robot status information
    """
    print("📊 Getting robot status")
    time.sleep(0.2)  # Simulate status check time
    
    return {
        "success": True,
        "status": "ready",
        "position": {"x": 0.0, "y": 0.0, "z": 0.5},
        "gripper": "open",
        "battery": 85,
        "message": "Robot is ready and operational"
    }


def execute_task(task_name: str, parameters: Optional[Dict] = None) -> Dict:
    """Execute a predefined task.
    
    Args:
        task_name: Name of the task to execute
        parameters: Optional parameters for the task
    
    Returns:
        Dictionary with task execution results
    """
    print(f"🎯 Executing task: {task_name}")
    time.sleep(1.0)  # Simulate task execution time
    
    if parameters is None:
        parameters = {}
    
    # Simulate different task results
    task_results = {
        "pick_and_place": {
            "success": True,
            "object_picked": parameters.get("object", "unknown"),
            "pick_position": parameters.get("pick_position", {"x": 0.3, "y": 0.1, "z": 0.2}),
            "place_position": parameters.get("place_position", {"x": 0.7, "y": -0.1, "z": 0.25}),
            "message": f"Successfully picked {parameters.get('object', 'object')} and placed it"
        },
        "sort_objects": {
            "success": True,
            "objects_sorted": 3,
            "categories": ["fruits", "tools", "containers"],
            "message": "Successfully sorted 3 objects into 3 categories"
        },
        "cleanup": {
            "success": True,
            "objects_moved": 2,
            "area_cleared": "workspace",
            "message": "Successfully cleaned up workspace"
        }
    }
    
    result = task_results.get(task_name, {"success": False, "error": f"Unknown task: {task_name}"})
    return result


def debug_gripper_status() -> Dict:
    """Debug the gripper status by getting its current position and effort."""
    print("🔧 Debugging gripper status...")
    
    try:
        # Ensure ROS2 is initialized for the gripper controller
        if not _gripper_controller._initialized:
            _gripper_controller._ensure_ros_init()
        
        # Get current gripper position and effort
        position, effort = _gripper_controller._get_gripper_status()
        
        return {
            "success": True,
            "gripper_position": position,
            "gripper_effort": effort,
            "message": f"Gripper is at position {position:.3f} and effort {effort:.1f}"
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to debug gripper status: {str(e)}"}


def debug_arm_controller_status() -> Dict:
    """Debug the arm controller status by checking action server availability."""
    print("🔧 Debugging arm controller status...")
    
    try:
        # Ensure ROS2 is initialized
        if not ensure_rclpy_init():
            return {"success": False, "error": "ROS2 not initialized"}
        
        # Discover action servers
        if not _arm_controller._initialized:
            _arm_controller.action_server_name = _arm_controller._discover_arm_action_server()
            if _arm_controller.action_server_name:
                _arm_controller._ensure_ros_init()
        
        diagnostics = {
            "success": True,
            "controller_initialized": _arm_controller._initialized,
            "action_server_name": _arm_controller.action_server_name,
        }
        
        # Check if action server is available
        if _arm_controller._initialized and _arm_controller.action_client:
            server_available = _arm_controller.action_client.wait_for_server(timeout_sec=2.0)
            diagnostics["action_server_available"] = server_available
            
            if server_available:
                diagnostics["message"] = f"✅ Arm controller ready: {_arm_controller.action_server_name}"
            else:
                diagnostics["message"] = f"⚠️ Action server not responding: {_arm_controller.action_server_name}"
                diagnostics["success"] = False
        
        # Try to list all available actions via CLI
        try:
            import subprocess
            result = subprocess.run(
                ['ros2', 'action', 'list'],
                capture_output=True,
                text=True,
                timeout=3.0
            )
            if result.returncode == 0:
                all_actions = [line.strip() for line in result.stdout.split('\n') if line.strip()]
                diagnostics["available_actions"] = all_actions
                # Filter for trajectory-related actions
                trajectory_actions = [a for a in all_actions if 'trajectory' in a.lower()]
                diagnostics["trajectory_actions"] = trajectory_actions
        except Exception as e:
            diagnostics["action_list_error"] = str(e)
        
        # Get current joint positions if available
        if _arm_controller._initialized:
            try:
                current_positions = _arm_controller._get_current_joint_positions()
                diagnostics["current_joint_positions"] = current_positions
            except Exception as e:
                diagnostics["joint_position_error"] = str(e)
        
        return diagnostics
        
    except Exception as e:
        return {"success": False, "error": f"Failed to debug arm controller status: {str(e)}"}


# ============================================================================
# VLA TOOL HELPER FUNCTIONS
# ============================================================================

def _ensure_lerobot_available():
    """Check if lerobot is available."""
    if not LEROBOT_AVAILABLE:
        raise ImportError(
            f"lerobot is not available. Import error: {LEROBOT_IMPORT_ERROR}. "
            "Please install lerobot or ensure it's in your Python path."
        )


def _ensure_robot_available():
    """Check if robot components are available."""
    if not ROBOT_AVAILABLE:
        raise ImportError(
            f"Robot components are not available. Import error: {ROBOT_IMPORT_ERROR}. "
            "Please install lerobot-robot-ros or ensure it's in your Python path."
        )


def load_policy_config(config_path: Optional[str] = None) -> Dict:
    """
    Load policy configuration from YAML file.

    Args:
        config_path: Path to config file. If None, looks for:
                    1. LEROBOT_CONFIG_PATH environment variable
                    2. ./policy_config.yaml (in gradio_agent directory)
                    3. ../policy_config.yaml (in parent directory)

    Returns:
        Dictionary with policy configuration
    """
    global _cached_config

    # Return cached config if available
    if _cached_config is not None and config_path is None:
        return _cached_config

    # Determine config file path
    if config_path is None:
        # Try environment variable first
        config_path = os.environ.get("LEROBOT_CONFIG_PATH")

        # Try common locations
        if config_path is None:
            possible_paths = [
                os.path.join(os.path.dirname(__file__), "policy_config.yaml"),
                os.path.join(os.path.dirname(__file__), "..", "policy_config.yaml"),
                "policy_config.yaml",
            ]

            for path in possible_paths:
                if os.path.exists(path):
                    config_path = path
                    break

    # Load config file
    if config_path and os.path.exists(config_path):
        try:
            import yaml
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            print(f"✅ Loaded policy config from: {config_path}")
            _cached_config = config
            return config

        except ImportError:
            print("⚠️ PyYAML not installed. Install with: pip install pyyaml")
            print("   Falling back to environment variables")
        except Exception as e:
            print(f"⚠️ Failed to load config from {config_path}: {e}")
            print("   Falling back to environment variables")

    # Fallback: return empty config (will use environment variables or defaults)
    return {}


def get_policy_config_value(key: str, default: any = None, config: Optional[Dict] = None) -> any:
    """
    Get a configuration value with fallback priority:
    1. Config file (if provided)
    2. Environment variable
    3. Default value

    Args:
        key: Configuration key (e.g., "policy_path", "policy_type", "device")
        default: Default value if not found
        config: Config dictionary (if None, loads from file)

    Returns:
        Configuration value
    """
    # Load config if not provided
    if config is None:
        config = load_policy_config()

    # Check config file first
    if key in config:
        return config[key]

    # Check environment variable (uppercase with LEROBOT_ prefix)
    env_key = f"LEROBOT_{key.upper()}"
    env_value = os.environ.get(env_key)
    if env_value is not None:
        return env_value

    # Return default
    return default


def preload_vla_policy(
    policy_path: Optional[str] = None,
    policy_type: Optional[str] = None,
    device: Optional[str] = None,
    config_path: Optional[str] = None,
) -> bool:
    """
    Pre-load VLA policy at startup to avoid delays during first execution.

    This function loads the policy into global cache so that execute_vla_task
    can use it immediately without loading delays.

    Configuration priority:
    1. Function arguments (if provided)
    2. Config file (policy_config.yaml)
    3. Environment variables (LEROBOT_*)
    4. Default values

    Args:
        policy_path: Path to policy (local or HuggingFace Hub).
                    If None, reads from config file or LEROBOT_POLICY_PATH env var.
        policy_type: Type of policy ("act", "smolvla", etc.).
                    If None, reads from config file or LEROBOT_POLICY_TYPE env var (default: "act").
        device: Device to run on ("cuda", "cpu", or None for auto-detect).
                If None, reads from config file or LEROBOT_DEVICE env var (default: auto-detect).
        config_path: Path to config YAML file. If None, searches standard locations.

    Returns:
        True if successful, False if failed
    """
    try:
        # Load config file
        config = load_policy_config(config_path)

        # Get configuration with fallback priority
        if policy_path is None:
            policy_path = get_policy_config_value(
                "policy_path",
                default="ases200q2/Isaac_panda_pick_cube_act_20251116_101319",
                config=config
            )

        if policy_type is None:
            policy_type = get_policy_config_value(
                "policy_type",
                default="act",
                config=config
            )

        if device is None:
            device = get_policy_config_value(
                "device",
                default=None,
                config=config
            )
        

        print(f"🔄 Pre-loading VLA policy: {policy_path}")
        print(f"   Type: {policy_type}, Device: {device or 'auto-detect'}")

        # Load policy (this will cache it globally)
        policy, preprocessor, postprocessor, loaded_device = _load_policy(
            policy_path=policy_path,
            policy_type=policy_type,
            device=device,
        )

        print(f"✅ VLA policy pre-loaded successfully")
        print(f"   Device: {loaded_device}")
        return True

    except Exception as e:
        print(f"⚠️ Warning: Failed to pre-load VLA policy: {e}")
        print(f"   Policy will be loaded on first use instead")
        return False


def _load_policy(
    policy_path: str,
    policy_type: str = "act",
    device: Optional[str] = None,
) -> tuple:
    """
    Load a pretrained policy and its processors.

    Args:
        policy_path: Path to pretrained policy (local or HuggingFace Hub)
        policy_type: Type of policy ("act", "smolvla", "diffusion", etc.)
        device: Device to run on ("cuda", "cpu", or None for auto-detect)

    Returns:
        Tuple of (policy, preprocessor, postprocessor, device)
    """
    global _cached_policy, _cached_preprocessor, _cached_postprocessor
    global _cached_device, _cached_policy_type, _cached_policy_path

    # Check if we can reuse cached policy
    if (
        _cached_policy is not None
        and _cached_policy_path == policy_path
        and _cached_policy_type == policy_type
    ):
        return _cached_policy, _cached_preprocessor, _cached_postprocessor, _cached_device
    
    _ensure_lerobot_available()
    
    # Get device
    if device is None:
        device = get_safe_torch_device("cuda" if torch.cuda.is_available() else "cpu", log=False)
    else:
        device = get_safe_torch_device(device, log=False)
    
    print(f"🤖 Loading policy: {policy_path} (type: {policy_type}, device: {device})")
    
    # Get policy class
    policy_class = get_policy_class(policy_type)

    
    # Load pretrained policy
    try:
        policy = policy_class.from_pretrained(policy_path, compile_model=False)
        policy.to(device)
        policy.eval()
    except Exception as e:
        raise RuntimeError(f"Failed to load policy from {policy_path}: {e}")
    # Load preprocessor and postprocessor
    try:
        preprocessor, postprocessor = make_pre_post_processors(
            policy_cfg=policy.config,
            pretrained_path=policy_path,
            # Override device in preprocessor to match inference device
            preprocessor_overrides={"device_processor": {"device": str(device)}},
        )
    except Exception as e:
        raise RuntimeError(f"Failed to load processors: {e}")
    
    # Cache for reuse
    _cached_policy = policy
    _cached_preprocessor = preprocessor
    _cached_postprocessor = postprocessor
    _cached_device = device
    _cached_policy_type = policy_type
    _cached_policy_path = policy_path
    
    print(f"✅ Policy loaded successfully")
    
    return policy, preprocessor, postprocessor, device


def _setup_robot(robot_type: str = "panda_ros_position", robot_id: str = "my_panda_follower"):
    """
    Set up and connect to the robot.
    
    Args:
        robot_type: Type of robot configuration
        robot_id: Robot ID
    
    Returns:
        Robot instance
    """
    global _cached_robot
    
    # Check if we can reuse cached robot
    if _cached_robot is not None:
        if _cached_robot.is_connected:
            return _cached_robot
        else:
            # Try to reconnect
            try:
                _cached_robot.connect()
                return _cached_robot
            except Exception:
                _cached_robot = None
    
    _ensure_robot_available()
    
    print(f"🤖 Setting up robot: {robot_type} (id: {robot_id})")
    
    # Create robot config
    if robot_type in ("panda_ros_position", "panda_ros_isaac_fast"):
        robot_cfg = PandaROSPositionConfig(id=robot_id)
    elif robot_type in ("panda_ros", "panda_ros_isaac"):
        robot_cfg = PandaROSConfig(id=robot_id)
    elif robot_type in ("panda_ros_cartesian"):
        robot_cfg = PandaROSCartesianConfig(id=robot_id)
    else:
        raise ValueError(
            f"Unsupported robot type: {robot_type}. "
            f"Supported: panda_ros_position, panda_ros"
        )
    
    # Create robot instance
    try:
        robot = make_robot_from_config(robot_cfg)
    except Exception as e:
        raise RuntimeError(f"Failed to create robot: {e}")
    
    # Connect to robot
    try:
        if not robot.is_connected:
            robot.connect()
        print(f"✅ Robot connected successfully")
    except Exception as e:
        raise RuntimeError(f"Failed to connect to robot: {e}")
    
    # Cache for reuse
    _cached_robot = robot
    
    return robot


def _get_dataset_features(robot) -> Dict:
    """
    Convert robot features to dataset features format.
    
    This is needed for build_inference_frame() and make_robot_action().
    """
    action_features = hw_to_dataset_features(robot.action_features, "action")
    obs_features = hw_to_dataset_features(robot.observation_features, "observation")
    dataset_features = {**action_features, **obs_features}
    return dataset_features


def _busy_wait(seconds: float):
    """
    Wait for the specified duration with platform-specific optimization.
    
    On Linux, time.sleep() is accurate and efficient.
    On Mac/Windows, we need a busy-wait loop for accuracy (but uses more CPU).
    """
    if seconds <= 0:
        return
    
    import platform
    if platform.system() == "Darwin" or platform.system() == "Windows":
        # On Mac and Windows, `time.sleep` is not accurate and we need to use this while loop trick,
        # but it consumes CPU cycles.
        end_time = time.perf_counter() + seconds
        while time.perf_counter() < end_time:
            pass
    else:
        # On Linux time.sleep is accurate
        time.sleep(seconds)


def _verify_task_completion(
    task_description: str,
    before_image: np.ndarray,
    after_image: np.ndarray,
    detail_level: str = "balanced",
    execution_errors: list = None
) -> dict:
    """
    Verify task completion using vision-based LLM analysis.

    Args:
        task_description: The task that was executed (e.g., "pick the red cube")
        before_image: numpy array (H, W, 3) before task execution
        after_image: numpy array (H, W, 3) after task execution
        detail_level: "minimal", "balanced", or "detailed"
        execution_errors: List of errors during execution (optional context)

    Returns:
        dict with verification results or None if verification fails
    """
    try:
        import os
        from PIL import Image as PILImage
        from google import genai
        import json

        # Check for API key
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            print("⚠️ No GOOGLE_API_KEY found, skipping verification")
            return None

        # Convert numpy arrays to PIL Images
        before_pil = PILImage.fromarray(before_image)
        after_pil = PILImage.fromarray(after_image)

        # Create side-by-side comparison image
        width, height = before_pil.size
        combined = PILImage.new('RGB', (width * 2, height))
        combined.paste(before_pil, (0, 0))
        combined.paste(after_pil, (width, 0))

        # Build verification prompt based on detail level
        if detail_level == "minimal":
            prompt = f"""Task: "{task_description}"

Left image: BEFORE task execution
Right image: AFTER task execution

Answer in JSON format:
{{"task_completed": true/false, "confidence": "high/medium/low", "brief_reason": "one sentence"}}"""

        elif detail_level == "detailed":
            error_context = ""
            if execution_errors:
                error_context = f"\n\nExecution errors occurred: {execution_errors[:3]}"

            prompt = f"""Task: "{task_description}"

Left image: BEFORE task execution
Right image: AFTER task execution{error_context}

Analyze the images to determine if the task succeeded. Provide:
1. Did the task complete successfully?
2. What specific changes occurred?
3. Confidence level in your assessment
4. If partial success, what was achieved?

Return JSON:
{{
  "task_completed": true/false,
  "confidence": "high/medium/low",
  "analysis": "detailed explanation",
  "observed_changes": ["change 1", "change 2", ...],
  "partial_success_details": "if applicable"
}}"""

        else:  # balanced (default)
            prompt = f"""Task: "{task_description}"

Left image: BEFORE task execution
Right image: AFTER task execution

Did the task succeed? Analyze the images and return JSON:
{{
  "task_completed": true/false,
  "confidence": "high/medium/low",
  "analysis": "brief explanation of what happened",
  "observed_changes": ["key change 1", "key change 2"]
}}"""

        # Call Gemini API
        print(f"🔍 Verifying task completion via vision analysis...")
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, combined]
        )

        # Parse response
        response_text = response.text.strip()

        # Extract JSON (handle markdown code fences if present)
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        verification_result = json.loads(response_text)

        # Add images to result
        verification_result["before_image"] = before_pil
        verification_result["after_image"] = after_pil
        verification_result["combined_image"] = combined
        verification_result["enabled"] = True

        # Log result
        completed = verification_result.get("task_completed", False)
        confidence = verification_result.get("confidence", "unknown")
        status = "✅ SUCCEEDED" if completed else "❌ FAILED"
        print(f"   {status} (confidence: {confidence})")

        return verification_result

    except json.JSONDecodeError as e:
        print(f"⚠️ Failed to parse verification response: {e}")
        return {
            "task_completed": "error",
            "confidence": "none",
            "analysis": f"Verification parsing error: {str(e)}",
            "error": str(e)
        }
    except Exception as e:
        print(f"⚠️ Verification failed: {e}")
        return None


def execute_vla_task(
    task_description: str,
    num_steps: int = 300,
    policy_path: Optional[str] = None,
    policy_type: str = "pi0", # for some reason its not detecting the policy_type; override for now
    robot_type: str = "panda_ros_cartesian", # same
    robot_id: str = "my_panda_follower",
    device: Optional[str] = None,
    fps: int = 30,  # Control frequency in Hz (must match training!)
    enable_verification: bool = True,  # Enable vision-based task verification
    verification_detail: str = "balanced",  # Detail level: "minimal", "balanced", "detailed"
) -> Dict:
    """
    Execute a robot task using a trained VLA (Vision-Language-Action) policy.

    This tool allows an LLM agent to execute robot tasks by running inference
    with a trained policy. The policy will generate actions based on observations
    and execute them on the robot for a fixed number of timesteps.

    Use this tool when you need to perform a complex manipulation task that requires
    learned behavior, such as "pick the cube", "place the object", etc.

    Note on Action Chunking:
        ACT policy internally predicts multiple actions at once (e.g., 100 actions per chunk).
        The policy.select_action() method handles this automatically - it only runs inference
        when the internal action queue is empty, then returns actions one at a time.
        This means actual GPU inference happens every ~100 steps, not every step.

    Args:
        task_description: Description of the task to execute (e.g., "pick the cube")
        num_steps: Number of control loop steps (timesteps) to execute.
                   Default is 300 (10 seconds at 30 FPS).
                   Common values: 300 (10s), 450 (15s), 600 (20s), 900 (30s).
                   Duration in seconds = num_steps / fps
        policy_path: Path to pretrained policy (local or HuggingFace Hub).
                    If None, uses LEROBOT_POLICY_PATH environment variable.
        policy_type: Type of policy ("act", "smolvla", "diffusion", etc.)
        robot_type: Type of robot configuration
        robot_id: Robot ID
        device: Device to run inference on ("cuda", "cpu", or None for auto-detect)
        fps: Control frequency in Hz (default: 30, must match training FPS!)
        enable_verification: Enable vision-based task verification using camera images
                            and LLM analysis (default: True). Gracefully degrades if
                            camera or API unavailable.
        verification_detail: Detail level for verification - "minimal", "balanced", or
                            "detailed" (default: "balanced"). Controls how thorough the
                            LLM analysis is and what information is returned.

    Returns:
        Dictionary with execution summary and optional verification results:
        {
            "success": bool,              # Based on verification if enabled, else on execution errors
            "task": str,                  # Task description
            "total_steps": int,           # Total steps attempted
            "successful_steps": int,      # Steps completed without errors
            "failed_steps": int,          # Steps with errors
            "duration_seconds": float,    # Actual execution duration
            "message": str,               # Summary message
            "errors": List[str],          # (optional) List of error messages if any occurred
            "verification": {             # (optional) Only present if verification enabled and succeeded
                "enabled": True,
                "task_completed": bool,           # LLM's assessment of task success
                "confidence": str,                # "high", "medium", or "low"
                "analysis": str,                  # Natural language explanation
                "observed_changes": List[str],    # Specific changes detected (detail dependent)
                "before_image": PIL.Image,        # Camera image before task
                "after_image": PIL.Image,         # Camera image after task
                "combined_image": PIL.Image,      # Side-by-side comparison
                "partial_success_details": str    # (optional) If task partially succeeded
            }
        }
    """

    try:
        # somethings not working here
        # activates cartesian controller and deactivates move_to_home controller
        session_name = "robot_console"
        script_name = "switch_controllers.sh"
        script_path = f'/home/student/lerobot-ros-agent/{script_name}'
        controller_arg = "cartesian"

        try:
            subprocess.run(["bash", script_path, controller_arg])
            print("activated cartesian controller")
        except Exception as e:
            return {"success": False, "error": str(e)}

        # Load config to get default values
        config = load_policy_config()

        # Get policy path from config/environment if not provided
        if policy_path is None:
            policy_path = get_policy_config_value(
                "policy_path",
                default="ases200q2/Isaac_panda_pick_cube_act_20251116_101319",
                config=config
            )

        # Get device from config/environment if not provided
        if device is None:
            device = get_policy_config_value("device", default=None, config=config)

        # Get robot config from config file if using defaults
        if robot_type == "panda_ros_position" and "robot" in config:
            robot_config = config.get("robot", {})
            robot_type = robot_config.get("type", robot_type)
            robot_id = robot_config.get("id", robot_id)

        # Get execution params from config
        if "execution" in config:
            exec_config = config.get("execution", {})
            if fps == 30:  # Only override if using default
                fps = exec_config.get("fps", fps)
            if num_steps == 300:  # Only override if using default
                num_steps = exec_config.get("default_num_steps", num_steps)

        print(f"🎯 Executing VLA task: '{task_description}'")
        print(f"   Policy: {policy_path} ({policy_type})")
        print(f"   Robot: {robot_type} (id: {robot_id})")
        print(f"   Steps: {num_steps} ({num_steps / fps:.1f} seconds at {fps} FPS)")
        
        # Load policy
        policy, preprocessor, postprocessor, device = _load_policy(
            policy_path=policy_path,
            policy_type=policy_type,
            device=device,
        )
        
        # Set up robot
        robot = _setup_robot(robot_type=robot_type, robot_id=robot_id)

        # Get dataset features (needed for build_inference_frame and make_robot_action)
        print("Converting robot features to dataset format...")
        dataset_features = _get_dataset_features(robot)
        print("✅ Dataset features ready")

        # Reset policy and processor states before starting inference
        # This is critical for temporal policies (ACT, etc.) that maintain action queues
        policy.reset()
        preprocessor.reset()
        postprocessor.reset()
        print("✅ Policy and processor states reset")

        # Capture before image for verification
        before_image = None
        if enable_verification:
            try:
                print("📸 Capturing 'before' image...")
                obs_before = robot.get_observation()
                before_image = obs_before.get("camera_1")
                if before_image is not None:
                    print(f"   ✅ Captured image: {before_image.shape}")
                else:
                    print("   ⚠️ Camera observation not available")
                    enable_verification = False
            except Exception as e:
                print(f"   ⚠️ Failed to capture before image: {e}")
                enable_verification = False

        # Execute inference loop
        successful_actions = 0
        failed_actions = 0
        errors = []

        # Calculate expected duration
        expected_duration_s = num_steps / fps
        print(f"🚀 Starting inference loop:")
        print(f"   Steps: {num_steps}")
        print(f"   FPS: {fps} Hz")
        print(f"   Expected duration: {expected_duration_s:.1f} seconds")

        for step_idx in range(num_steps):
            try:
                # Start timing for this control loop iteration
                loop_start = time.perf_counter()

                # 1. Get observation from robot
                obs = robot.get_observation()

                # 2. Build inference frame (converts robot obs to dataset format and prepares for inference)
                obs_frame = build_inference_frame(
                    observation=obs,
                    ds_features=dataset_features,
                    device=device,
                    task=task_description,
                    robot_type=robot_type,
                )

                # 3. Preprocess observation
                obs_processed = preprocessor(obs_frame)

                # 4. Run inference
                action_tensor = policy.select_action(obs_processed)

                # 5. Postprocess action
                action_tensor = postprocessor(action_tensor)

                # 6. Convert action to robot format
                action = make_robot_action(action_tensor, dataset_features)

                # 7. Send action to robot
                robot.send_action(action)

                successful_actions += 1

                # Progress update: print every second (fps steps = 1 second)
                # This gives a nice once-per-second update regardless of FPS
                if (step_idx + 1) % fps == 0:
                    elapsed_s = (step_idx + 1) / fps
                    print(f"   ✓ Step {step_idx + 1}/{num_steps} ({elapsed_s:.1f}s)")

                # Maintain target FPS
                dt = time.perf_counter() - loop_start
                _busy_wait(1.0 / fps - dt)
                    
            except Exception as e:
                failed_actions += 1
                error_msg = f"Error in step {step_idx + 1}: {str(e)}"
                errors.append(error_msg)
                print(f"   ⚠ {error_msg}")
                import traceback
                traceback.print_exc()
                # Continue with next step
        
        actual_duration_s = successful_actions / fps
        print(f"✅ Task execution completed")
        print(f"   Successful steps: {successful_actions}/{num_steps}")
        print(f"   Duration: {actual_duration_s:.1f}s (expected: {expected_duration_s:.1f}s)")
        if failed_actions > 0:
            print(f"   Failed steps: {failed_actions}/{num_steps}")

        # Capture after image for verification
        after_image = None
        if enable_verification and before_image is not None:
            try:
                print("📸 Capturing 'after' image...")
                import time as time_module
                time_module.sleep(0.5)  # Let robot settle
                obs_after = robot.get_observation()
                after_image = obs_after.get("camera_1")
                if after_image is not None:
                    print(f"   ✅ Captured image: {after_image.shape}")
                else:
                    print("   ⚠️ Camera observation not available")
                    enable_verification = False
            except Exception as e:
                print(f"   ⚠️ Failed to capture after image: {e}")
                enable_verification = False

        # Run verification
        verification_result = None
        if enable_verification and before_image is not None and after_image is not None:
            verification_result = _verify_task_completion(
                task_description=task_description,
                before_image=before_image,
                after_image=after_image,
                detail_level=verification_detail,
                execution_errors=errors if errors else None
            )

        # Return result
        result = {
            "success": failed_actions == 0,
            "task": task_description,
            "total_steps": num_steps,
            "successful_steps": successful_actions,
            "failed_steps": failed_actions,
            "duration_seconds": actual_duration_s,
            "message": (
                f"Successfully executed {successful_actions}/{num_steps} steps ({actual_duration_s:.1f}s) for task: {task_description}"
                if failed_actions == 0
                else f"Executed {successful_actions}/{num_steps} steps with {failed_actions} failures for task: {task_description}"
            ),
        }

        if errors:
            result["errors"] = errors

        # Apply verification results
        if verification_result:
            result["verification"] = verification_result

            # Override success based on verification
            if "task_completed" in verification_result:
                task_completed = verification_result["task_completed"]
                if task_completed is True or task_completed is False:
                    result["success"] = task_completed

                    # Update message to reflect verification
                    if task_completed and failed_actions == 0:
                        result["message"] = f"✅ Task succeeded: {task_description}"
                    elif task_completed and failed_actions > 0:
                        result["message"] = f"⚠️ Task succeeded with {failed_actions} execution errors: {task_description}"
                    elif not task_completed and failed_actions == 0:
                        result["message"] = f"❌ Task failed (visual verification): {task_description}"
                    else:
                        result["message"] = f"❌ Task failed with {failed_actions} execution errors: {task_description}"

        return result
        
    except ImportError as e:
        return {
            "success": False,
            "error": f"Import error: {str(e)}",
            "message": "Failed to import required lerobot components. Please ensure lerobot is installed.",
        }
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"❌ Error executing VLA task: {e}")
        print(error_trace)
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to execute task: {task_description}. Error: {str(e)}",
        }


def cleanup():
    """Cleanup ROS2 resources"""
    global _gripper_controller, _arm_controller, _ros_context_initialized
    if hasattr(_gripper_controller, '_initialized') and _gripper_controller._initialized and getattr(_gripper_controller, 'node', None):
        _gripper_controller.node.destroy_node()
    if hasattr(_arm_controller, '_initialized') and _arm_controller._initialized and getattr(_arm_controller, 'node', None):
        _arm_controller.node.destroy_node()
    if _ros_context_initialized and rclpy and rclpy.ok():
        rclpy.shutdown()
        _ros_context_initialized = False
    _ros_context_failed = False
    print("🧹 Cleanup completed")


# List of all available robot tools for easy importing
ROBOT_TOOLS = [
    get_world_model,
    move_robot_arm,
    control_gripper,
    get_current_arm_position,
    control_arm_home_position,
    scan_environment,
    get_robot_status,
    execute_task,
    debug_gripper_status,
    debug_arm_controller_status,
    execute_vla_task,  # VLA policy execution tool
    move_robot_arm_delta
]


def get_robot_tools():
    """Get a list of all available robot tools.
    
    Returns:
        List of robot control functions
    """
    return ROBOT_TOOLS.copy()


def get_tool_names():
    """Get a list of all available tool names.
    
    Returns:
        List of tool function names
    """
    return [tool.__name__ for tool in ROBOT_TOOLS]


def get_tool_by_name(name: str):
    """Get a specific tool function by name.
    
    Args:
        name: Name of the tool function
    
    Returns:
        The tool function if found, None otherwise
    """
    for tool in ROBOT_TOOLS:
        if tool.__name__ == name:
            return tool
    return None


# Example usage and testing
if __name__ == "__main__":
    print("🧪 Testing Integrated Gripper and Arm Control Module...")
    
    try:
        # Test getting current arm position
        result = get_current_arm_position()
        print(f"Current arm position result: {result}")
        
        # Test arm home position
        result = control_arm_home_position()
        print(f"Arm home position result: {result}")
        
        # Test open action
        result = control_gripper("open")
        print(f"Open result: {result}")
        time.sleep(4)
        
        # Test close action
        result = control_gripper("close")
        print(f"Close result: {result}")
        time.sleep(4)

        # Test grasp action with custom force
        result = control_gripper("grasp", 0.8)
        print(f"Grasp result: {result}")
        
        # Test invalid action
        result = control_gripper("invalid")
        print(f"Invalid action result: {result}")
        
    finally:
        cleanup()
