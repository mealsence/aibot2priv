#!/usr/bin/env python3
"""
Comprehensive Robot State Viewer

This script provides detailed information about the current robot state including:
- Joint positions and velocities
- End effector pose (position and orientation)
- Gripper state
- Robot configuration information

Usage:
    python get_robot_state.py
"""

import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformListener, Buffer
import tf_transformations
from gripper_control_module import get_current_arm_position
import time


class RobotStateViewer:
    """Comprehensive robot state viewer with forward kinematics"""
    
    def __init__(self):
        self.node = None
        self.joint_state_sub = None
        self.tf_buffer = None
        self.tf_listener = None
        self.current_joint_state = None
        self._initialized = False
        
        # Panda robot DH parameters for forward kinematics
        # These are the standard Franka Panda DH parameters
        self.dh_params = [
            {'a': 0, 'd': 0.333, 'alpha': 0},          # joint1
            {'a': 0, 'd': 0, 'alpha': -np.pi/2},        # joint2
            {'a': 0.316, 'd': 0, 'alpha': np.pi/2},     # joint3
            {'a': 0.0825, 'd': 0.384, 'alpha': np.pi/2}, # joint4
            {'a': 0, 'd': 0, 'alpha': -np.pi/2},        # joint5
            {'a': 0.0825, 'd': 0, 'alpha': np.pi/2},    # joint6
            {'a': 0, 'd': 0.107, 'alpha': 0},           # joint7
        ]
        
    def _ensure_ros_init(self):
        """Ensure ROS2 is initialized"""
        if not self._initialized:
            try:
                if not rclpy.ok():
                    rclpy.init()
                    
                self.node = Node('robot_state_viewer')
                
                # Subscribe to joint states
                self.joint_state_sub = self.node.create_subscription(
                    JointState,
                    '/joint_states',
                    self._joint_state_callback,
                    10
                )
                
                # Setup TF listener for end effector pose
                self.tf_buffer = Buffer()
                self.tf_listener = TransformListener(self.tf_buffer, self.node)
                
                self._initialized = True
                print("🤖 Robot state viewer initialized")
                return True
                
            except Exception as e:
                print(f"⚠️ Warning: Could not initialize robot state viewer: {e}")
                return False
        return True
    
    def _joint_state_callback(self, msg):
        """Callback to store current joint state"""
        self.current_joint_state = msg
    
    def _get_joint_positions(self) -> dict:
        """Get current joint positions"""
        if not self._ensure_ros_init():
            return {}
            
        # Wait for joint state data
        if self.current_joint_state is None:
            print("⏳ Waiting for joint state data...")
            start_time = time.time()
            while self.current_joint_state is None and (time.time() - start_time) < 5.0:
                try:
                    rclpy.spin_once(self.node, timeout_sec=0.1)
                except Exception:
                    break
        
        if self.current_joint_state is None:
            print("⚠️ Could not get joint state data")
            return {}
        
        # Extract Panda arm joint positions
        panda_joints = ['panda_joint1', 'panda_joint2', 'panda_joint3', 
                       'panda_joint4', 'panda_joint5', 'panda_joint6', 'panda_joint7']
        
        joint_positions = {}
        for joint_name in panda_joints:
            if joint_name in self.current_joint_state.name:
                idx = self.current_joint_state.name.index(joint_name)
                joint_positions[joint_name] = self.current_joint_state.position[idx]
        
        # Add gripper if available
        if 'panda_finger_joint1' in self.current_joint_state.name:
            idx = self.current_joint_state.name.index('panda_finger_joint1')
            joint_positions['panda_finger_joint1'] = self.current_joint_state.position[idx]
        
        return joint_positions
    
    def _get_end_effector_pose_tf(self) -> dict:
        """Get end effector pose using TF"""
        if not self._ensure_ros_init():
            return {}
        
        try:
            # Wait for transform to be available
            transform = self.tf_buffer.lookup_transform(
                'world',        # base frame
                'panda_hand',   # end effector frame
                rclpy.time.Time()
            )
            
            # Extract position
            position = {
                'x': transform.transform.translation.x,
                'y': transform.transform.translation.y,
                'z': transform.transform.translation.z
            }
            
            # Extract orientation (quaternion)
            orientation = {
                'x': transform.transform.rotation.x,
                'y': transform.transform.rotation.y,
                'z': transform.transform.rotation.z,
                'w': transform.transform.rotation.w
            }
            
            # Convert to Euler angles for easier reading
            euler = tf_transformations.euler_from_quaternion([
                orientation['x'], orientation['y'], orientation['z'], orientation['w']
            ])
            
            return {
                'position': position,
                'orientation_quaternion': orientation,
                'orientation_euler': {
                    'roll': euler[0],
                    'pitch': euler[1], 
                    'yaw': euler[2]
                }
            }
            
        except Exception as e:
            print(f"⚠️ Could not get end effector pose from TF: {e}")
            return {}
    
    def _forward_kinematics(self, joint_angles) -> dict:
        """Calculate end effector pose using forward kinematics"""
        try:
            if len(joint_angles) != 7:
                print(f"⚠️ Expected 7 joint angles, got {len(joint_angles)}")
                return {}
            
            # Initialize transformation matrix
            T = np.eye(4)
            
            # Apply DH transformations for each joint
            for i, (theta, dh) in enumerate(zip(joint_angles, self.dh_params)):
                a = dh['a']
                d = dh['d']
                alpha = dh['alpha']
                
                # DH transformation matrix
                T_i = np.array([
                    [np.cos(theta), -np.sin(theta)*np.cos(alpha), np.sin(theta)*np.sin(alpha), a*np.cos(theta)],
                    [np.sin(theta), np.cos(theta)*np.cos(alpha), -np.cos(theta)*np.sin(alpha), a*np.sin(theta)],
                    [0, np.sin(alpha), np.cos(alpha), d],
                    [0, 0, 0, 1]
                ])
                
                T = T @ T_i
            
            # Extract position from transformation matrix
            position = {
                'x': T[0, 3],
                'y': T[1, 3], 
                'z': T[2, 3]
            }
            
            # Extract rotation matrix and convert to Euler angles
            R = T[:3, :3]
            euler = tf_transformations.euler_from_matrix(R)
            
            # Convert to quaternion
            quaternion = tf_transformations.quaternion_from_euler(euler[0], euler[1], euler[2])
            
            return {
                'position': position,
                'orientation_euler': {
                    'roll': euler[0],
                    'pitch': euler[1],
                    'yaw': euler[2]
                },
                'orientation_quaternion': {
                    'x': quaternion[0],
                    'y': quaternion[1],
                    'z': quaternion[2],
                    'w': quaternion[3]
                }
            }
            
        except Exception as e:
            print(f"⚠️ Forward kinematics calculation failed: {e}")
            return {}
    
    def get_complete_robot_state(self) -> dict:
        """Get complete robot state including joints and end effector pose"""
        print("🔍 Getting complete robot state...")
        
        # Get joint positions using existing module
        joint_result = get_current_arm_position()
        
        # Get detailed joint information
        joint_positions = self._get_joint_positions()
        
        # Get end effector pose (try TF first, then forward kinematics)
        end_effector_pose = self._get_end_effector_pose_tf()
        
        if not end_effector_pose and joint_positions:
            # Fallback to forward kinematics
            joint_angles = [joint_positions.get(f'panda_joint{i+1}', 0.0) for i in range(7)]
            end_effector_pose = self._forward_kinematics(joint_angles)
        
        return {
            'timestamp': time.time(),
            'joint_state': {
                'basic_info': joint_result,
                'detailed_positions': joint_positions
            },
            'end_effector_pose': end_effector_pose,
            'status': 'success' if joint_positions else 'failed'
        }
    
    def print_robot_state(self, state: dict):
        """Print robot state in a readable format"""
        print("\n" + "="*60)
        print("🤖 ROBOT STATE REPORT")
        print("="*60)
        
        # Joint state information
        print("\n📊 JOINT STATE:")
        if state['joint_state']['basic_info'].get('success'):
            joint_angles = state['joint_state']['basic_info']['joint_angles']
            print(f"   Joint Angles (rad): {state['joint_state']['basic_info']['formatted']}")
            
            # Convert to degrees for easier reading
            joint_angles_deg = [np.rad2deg(angle) for angle in joint_angles]
            print(f"   Joint Angles (deg): [{', '.join([f'{angle:.1f}' for angle in joint_angles_deg])}]")
            
            # Detailed joint positions
            if state['joint_state']['detailed_positions']:
                print("\n   Detailed Joint Positions:")
                for joint_name, position in state['joint_state']['detailed_positions'].items():
                    print(f"     {joint_name}: {position:.4f} rad ({np.rad2deg(position):.1f}°)")
        else:
            print("   ❌ Could not read joint state")
        
        # End effector pose
        print("\n📍 END EFFECTOR POSE:")
        if state['end_effector_pose']:
            pose = state['end_effector_pose']
            
            if 'position' in pose:
                pos = pose['position']
                print(f"   Position (meters):")
                print(f"     X: {pos['x']:.4f}")
                print(f"     Y: {pos['y']:.4f}")
                print(f"     Z: {pos['z']:.4f}")
            
            if 'orientation_euler' in pose:
                euler = pose['orientation_euler']
                print(f"   Orientation (Euler, radians):")
                print(f"     Roll:  {euler['roll']:.4f}")
                print(f"     Pitch: {euler['pitch']:.4f}")
                print(f"     Yaw:   {euler['yaw']:.4f}")
                
                print(f"   Orientation (Euler, degrees):")
                print(f"     Roll:  {np.rad2deg(euler['roll']):.1f}°")
                print(f"     Pitch: {np.rad2deg(euler['pitch']):.1f}°")
                print(f"     Yaw:   {np.rad2deg(euler['yaw']):.1f}°")
            
            if 'orientation_quaternion' in pose:
                quat = pose['orientation_quaternion']
                print(f"   Orientation (Quaternion):")
                print(f"     X: {quat['x']:.4f}")
                print(f"     Y: {quat['y']:.4f}")
                print(f"     Z: {quat['z']:.4f}")
                print(f"     W: {quat['w']:.4f}")
        else:
            print("   ❌ Could not determine end effector pose")
        
        print(f"\n⏰ Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(state['timestamp']))}")
        print(f"📈 Status: {state['status']}")
        print("="*60)
    
    def cleanup(self):
        """Cleanup resources"""
        if self.joint_state_sub:
            self.joint_state_sub.destroy()
        if self.node:
            self.node.destroy_node()


def main():
    """Main function to display robot state"""
    viewer = RobotStateViewer()
    
    try:
        # Get complete robot state
        state = viewer.get_complete_robot_state()
        
        # Print in readable format
        viewer.print_robot_state(state)
        
    except KeyboardInterrupt:
        print("\n👋 Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        viewer.cleanup()


if __name__ == "__main__":
    main()
