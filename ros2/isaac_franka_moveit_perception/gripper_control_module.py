#!/usr/bin/env python3
"""
Standalone Gripper Control Module for LLM-controlled repositories

This module provides a simple interface for controlling robot grippers
that can be easily imported and used in other projects.
"""

import time
from typing import Dict
import rclpy
from rclpy.action import ActionClient
from control_msgs.action import GripperCommand
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray
from rclpy.node import Node

import time
from time import sleep  

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
            print(f"⚠️ Warning: Could not initialize ROS2 context: {e}")
            return False
    return True


class GripperController:
    """ROS2-based gripper controller"""
    
    def __init__(self):
        """Initialize the gripper controller"""
        self.node = None
        self.action_client = None
        self._initialized = False
        
    def _ensure_ros_init(self):
        """Ensure ROS2 is initialized and controller is ready"""
        if not self._initialized:
            try:
                # Use shared ROS2 context
                if not _ensure_ros_context():
                    return False
                    
                self.node = Node('gripper_controller')
                self.action_client = ActionClient(self.node, GripperCommand, '/panda_hand_controller/gripper_cmd')
                self._initialized = True
                print("🤖 ROS2 gripper controller initialized")
            except Exception as e:
                print(f"⚠️ Warning: Could not initialize ROS2 controller: {e}")
                print("🔄 Falling back to simulation mode")
                return False
        return True
    
    def _send_gripper_command(self, position: float, max_effort: float) -> bool:
        """Send actual gripper command via ROS2"""
        if not self._ensure_ros_init():
            return False
            
        try:
            goal_msg = GripperCommand.Goal()
            goal_msg.command.position = position
            goal_msg.command.max_effort = max_effort
            
            # Wait for action server
            if not self.action_client.wait_for_server(timeout_sec=2.0):
                print("⚠️ Gripper action server not available")
                return False
            
            # Send goal and wait for result
            future = self.action_client.send_goal_async(goal_msg)
            rclpy.spin_until_future_complete(self.node, future, timeout_sec=5.0)
            
            if future.done():
                goal_handle = future.result()
                if goal_handle.accepted:
                    # Wait for result
                    result_future = goal_handle.get_result_async()
                    rclpy.spin_until_future_complete(self.node, result_future, timeout_sec=5.0)
                    if result_future.done():
                        result = result_future.result().result
                        if result.reached_goal:
                            return True
                        else:
                            print(f"⚠️ Gripper goal not reached. Final position: {result.position}")
                            return False
                else:
                    print("⚠️ Gripper goal rejected")
                    return False
            else:
                print("⚠️ Gripper command timeout")
                return False
                
        except Exception as e:
            print(f"⚠️ Error sending gripper command: {e}")
            return False
        
        return False


class ArmController:
    """ROS2-based arm controller that supports both action and topic-based control"""
    
    def __init__(self):
        """Initialize the arm controller"""
        self.node = None
        self.action_client = None
        self.position_publisher = None
        self.joint_state_subscription = None
        self.current_joint_positions = None
        self._initialized = False
        self.use_action_interface = None  # Will be determined on first use
        
    def _ensure_ros_init(self):
        """Ensure ROS2 is initialized and controller is ready"""
        if not self._initialized:
            try:
                # Use shared ROS2 context
                if not _ensure_ros_context():
                    return False
                    
                self.node = Node('arm_controller')
                
                # Try to initialize action client (for panda_arm_controller)
                self.action_client = ActionClient(self.node, FollowJointTrajectory, '/panda_arm_controller/follow_joint_trajectory')
                
                # Also initialize position publisher (for panda_position_controller)
                self.position_publisher = self.node.create_publisher(
                    Float64MultiArray,
                    '/panda_position_controller/commands',
                    10
                )
                
                # Subscribe to joint states to get current positions
                self.joint_state_subscription = self.node.create_subscription(
                    JointState,
                    '/joint_states',
                    self._joint_state_callback,
                    10
                )
                
                self._initialized = True
                print("🤖 ROS2 arm controller initialized (supports both action and topic interfaces)")
            except Exception as e:
                print(f"⚠️ Warning: Could not initialize ROS2 arm controller: {e}")
                print("🔄 Falling back to simulation mode")
                return False
        return True
    
    def _detect_controller_type(self) -> str:
        """Detect which controller is available: 'action' or 'topic'"""
        if self.use_action_interface is not None:
            return 'action' if self.use_action_interface else 'topic'
        
        print("🔍 Detecting available controller...")
        
        # Try action interface first (wait longer for discovery)
        if self.action_client:
            print("   Checking for panda_arm_controller (action interface)...")
            # Allow more time for ROS2 discovery
            for _ in range(10):
                rclpy.spin_once(self.node, timeout_sec=0.1)
            
            if self.action_client.wait_for_server(timeout_sec=3.0):
                self.use_action_interface = True
                print("✅ Detected panda_arm_controller (action interface)")
                return 'action'
            else:
                print("   panda_arm_controller not available")
        
        # Fall back to topic interface
        print("   Checking for panda_position_controller (topic interface)...")
        # Verify publisher is ready
        if self.position_publisher:
            # Allow time for discovery
            for _ in range(10):
                rclpy.spin_once(self.node, timeout_sec=0.1)
            time.sleep(0.5)
            
            self.use_action_interface = False
            print("✅ Using panda_position_controller (topic interface)")
            print("   Topic: /panda_position_controller/commands")
            return 'topic'
        else:
            print("⚠️ Warning: Position publisher not initialized")
            self.use_action_interface = False
            return 'topic'
    
    def _joint_state_callback(self, msg: JointState):
        """Callback to store current joint positions"""
        try:
            # Find Panda arm joints in the joint state message
            panda_joints = ['panda_joint1', 'panda_joint2', 'panda_joint3', 
                           'panda_joint4', 'panda_joint5', 'panda_joint6', 'panda_joint7']
            
            current_positions = []
            for joint_name in panda_joints:
                if joint_name in msg.name:
                    idx = msg.name.index(joint_name)
                    current_positions.append(msg.position[idx])
                else:
                    # If joint not found, use 0.0 as fallback
                    current_positions.append(0.0)
            
            if len(current_positions) == 7:
                self.current_joint_positions = current_positions
                
        except Exception as e:
            print(f"⚠️ Error processing joint state: {e}")
    
    def _get_current_joint_positions(self) -> list:
        """Get current joint positions, wait if not available yet"""
        if self.current_joint_positions is None:
            print("⏳ Waiting for joint state data...")
            # Wait for joint state data
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
    
    def _send_arm_command(self, joint_positions: list, duration_sec: float = 3.0) -> bool:
        """Send arm command via ROS2 - supports both action and topic interfaces
        
        Args:
            joint_positions: List of 7 joint positions in radians
            duration_sec: Duration in seconds for the movement (for topic interface)
        """
        if not self._ensure_ros_init():
            return False
        
        # Detect which controller is available
        controller_type = self._detect_controller_type()
        
        try:
            if controller_type == 'action':
                # Use action interface (panda_arm_controller)
                return self._send_arm_command_action(joint_positions)
            else:
                # Use topic interface (panda_position_controller)
                return self._send_arm_command_topic(joint_positions, duration_sec)
        except Exception as e:
            print(f"⚠️ Error sending arm command: {e}")
            return False
    
    def _send_arm_command_action(self, joint_positions: list) -> bool:
        """Send arm command via action interface (panda_arm_controller)"""
        try:
            goal_msg = FollowJointTrajectory.Goal()
            trajectory = JointTrajectory()
            
            # Set joint names for Panda arm
            trajectory.joint_names = [
                'panda_joint1', 'panda_joint2', 'panda_joint3', 
                'panda_joint4', 'panda_joint5', 'panda_joint6', 'panda_joint7'
            ]
            
            # Create trajectory point
            point = JointTrajectoryPoint()
            point.positions = joint_positions
            point.velocities = [0.0] * 7  # Zero velocities
            point.accelerations = [0.0] * 7  # Zero accelerations
            point.time_from_start.sec = 3  # 3 seconds to reach position
            
            trajectory.points = [point]
            goal_msg.trajectory = trajectory
            
            # Wait for action server
            if not self.action_client.wait_for_server(timeout_sec=2.0):
                print("⚠️ Arm action server not available")
                return False
            
            # Send goal and wait for result
            future = self.action_client.send_goal_async(goal_msg)
            rclpy.spin_until_future_complete(self.node, future, timeout_sec=10.0)
            
            if future.done():
                goal_handle = future.result()
                if goal_handle.accepted:
                    # Wait for result
                    result_future = goal_handle.get_result_async()
                    rclpy.spin_until_future_complete(self.node, result_future, timeout_sec=10.0)
                    if result_future.done():
                        result = result_future.result().result
                        if result.error_code == 0:  # SUCCESSFUL
                            return True
                        else:
                            print(f"⚠️ Arm goal not reached. Error code: {result.error_code}")
                            return False
                else:
                    print("⚠️ Arm goal rejected")
                    return False
            else:
                print("⚠️ Arm command timeout")
                return False
        except Exception as e:
            print(f"⚠️ Error sending arm command via action: {e}")
            return False
    
    def _send_arm_command_topic(self, joint_positions: list, duration_sec: float = 3.0) -> bool:
        """Send arm command via topic interface (panda_position_controller)
        
        Args:
            joint_positions: List of 7 joint positions in radians
            duration_sec: Duration in seconds to publish commands (position controllers need continuous commands)
        """
        try:
            if self.position_publisher is None:
                print("⚠️ Position command publisher not initialized")
                return False
            
            # Allow time for ROS2 discovery to complete
            print("⏳ Allowing time for ROS2 discovery...")
            for _ in range(10):
                rclpy.spin_once(self.node, timeout_sec=0.1)
            time.sleep(0.5)  # Additional wait for discovery
            
            # Create Float64MultiArray message for position controller
            msg = Float64MultiArray()
            msg.data = list(joint_positions)  # Ensure it's a list
            
            # Verify message data
            if len(msg.data) != 7:
                print(f"⚠️ Error: Expected 7 joint positions, got {len(msg.data)}")
                return False
            
            print(f"📤 Publishing position command to /panda_position_controller/commands")
            print(f"   Joint positions: {[f'{p:.3f}' for p in msg.data]}")
            print(f"   Duration: {duration_sec:.2f} seconds")
            
            # Publish command continuously for the specified duration
            # Position controllers need continuous commands to maintain position and execute movement
            publish_rate = 20.0  # Hz (matches typical controller update rate of 100Hz, but 20Hz is sufficient)
            sleep_time = 1.0 / publish_rate
            publish_count = int(duration_sec * publish_rate)
            
            # Ensure we publish at least a few times even for very short durations
            if publish_count < 10:
                publish_count = 10
            
            print(f"   Publishing {publish_count} commands at {publish_rate} Hz...")
            
            start_time = time.time()
            iteration = 0
            while (time.time() - start_time) < duration_sec:
                self.position_publisher.publish(msg)
                # Process callbacks to ensure message is sent
                rclpy.spin_once(self.node, timeout_sec=0.001)
                iteration += 1
                
                # Sleep to maintain publish rate (but don't sleep on last iteration)
                elapsed = time.time() - start_time
                if elapsed < duration_sec - sleep_time:
                    time.sleep(sleep_time)
            
            print(f"✅ Published {iteration} position commands over {duration_sec:.2f} seconds")
            
            return True
        except Exception as e:
            print(f"⚠️ Error sending arm command via topic: {e}")
            import traceback
            traceback.print_exc()
            return False


# Global controller instances
_gripper_controller = GripperController()
_arm_controller = ArmController()


def control_gripper(action: str, force: float = 0.5) -> Dict:
    """Control the robot gripper.
    
    Args:
        action: Gripper action - "open", "close", or "grasp"
        force: Grip force between 0.0 and 1.0 (for close/grasp actions)
    
    Returns:
        Dictionary with success status and action performed
    """
    print(f"🤏 Gripper action: {action} with force: {force}")
    
    try:
        if action == "open":
            # Open gripper to maximum width (0.08 meters)
            success = _gripper_controller._send_gripper_command(0.08, 50.0)
            if success:
                return {"success": True, "action": "opened", "message": "Gripper opened successfully"}
            else:
                # Fallback to simulation if ROS2 fails
                time.sleep(0.3)
                return {"success": True, "action": "opened", "message": "Gripper opened (simulation mode)"}
                
        elif action in ["close", "grasp"]:
            # Close gripper with specified force
            # Convert force from 0.0-1.0 range to actual effort (0-50 N)
            max_effort = force * 50.0
            success = _gripper_controller._send_gripper_command(0.0, max_effort)
            
            if success:
                past = "closed" if action == "close" else "grasped"
                return {"success": True, "action": action, "force": force, "message": f"Gripper {past} successfully with force {force}"}
            else:
                # Fallback to simulation if ROS2 fails
                time.sleep(0.3)
                past = "closed" if action == "close" else "grasped"
                return {"success": True, "action": action, "force": force, "message": f"Gripper {past} with force {force} (simulation mode)"}
        else:
            return {"success": False, "error": f"Unknown gripper action: {action}"}
            
    except Exception as e:
        return {"success": False, "error": f"Gripper control failed: {str(e)}"}


def get_current_arm_position() -> Dict:
    """Get the current position of the robot arm.
    
    Returns:
        Dictionary with current joint positions and status
    """
    print("📊 Getting current arm position...")
    
    try:
        # Ensure ROS2 is initialized for the arm controller
        if not _arm_controller._initialized:
            _arm_controller._ensure_ros_init()
        
        # Get current joint positions
        current_positions = _arm_controller._get_current_joint_positions()
        
        if current_positions != [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]:
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
                "error": "Could not read current joint positions, using fallback values"
            }
            
    except Exception as e:
        return {"success": False, "error": f"Failed to get current arm position: {str(e)}"}


def control_arm_home_position() -> Dict:
    """Move the robot arm to the predefined home position.
    
    This function moves the arm TO the fixed home position
    
    [-0.034, -0.436, -0.076, -2.581, -0.038, 2.145, 0.703]
    from wherever it currently is.
    
    Returns:
        Dictionary with success status and action performed
    """
    print("🏠 Moving robot arm to home position...")
    
    try:
        # Fixed predefined home position
        home_positions = [-0.034, -0.436, -0.076, -2.581, -0.038, 2.145, 0.703]
        print(f"📍 Moving arm TO home position: {[f'{pos:.3f}' for pos in home_positions]}")
        
        # Send command to move arm TO these positions
        success = _arm_controller._send_arm_command(home_positions, duration_sec=2.0)
        
        if success:
            return {"success": True, "action": "homed", "message": "Robot arm moved to home position successfully", "position": "home", "joint_angles": home_positions}
        else:
            # Fallback to simulation if ROS2 fails
            time.sleep(2.0)  # Simulate arm movement time
            return {"success": True, "action": "homed", "message": "Robot arm moved to home position (simulation mode)", "position": "home", "joint_angles": home_positions}
            
    except Exception as e:
        return {"success": False, "error": f"Arm home position control failed: {str(e)}"}


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


# Example usage and testing
if __name__ == "__main__":
    print("🧪 Testing Gripper and Arm Control Module...")
    
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
        sleep(4)
        
        # Test close action
        result = control_gripper("close")
        print(f"Close result: {result}")
        sleep(4)

        # Test grasp action with custom force
        result = control_gripper("grasp", 0.8)
        print(f"Grasp result: {result}")
        
        # Test invalid action
        result = control_gripper("invalid")
        print(f"Invalid action result: {result}")
        
    finally:
        cleanup()

