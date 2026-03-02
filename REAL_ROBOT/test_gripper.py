#!/usr/bin/env python3
"""
Simple Gripper Test Script for Real Franka Panda Robot

This script tests the gripper using SpaceMouse buttons to open and close.
Similar to move_to_joint_angles.py in style and structure.

Prerequisites:
    On control PC (192.168.1.2):
        ros2 launch franka_bringup franka.launch.py robot_ip:=192.168.1.101
        ros2 run spacenav spacenav_node --ros-args -r /spacenav/joy:=/joy

Usage:
    python test_gripper.py                    # Test gripper with SpaceMouse
    python test_gripper.py --check-topics     # Check available topics
    python test_gripper.py --test-only        # Run automated test without SpaceMouse
    python test_gripper.py --joy-topic /joy   # Custom joy topic
"""

import argparse
import sys
import time
import threading
from typing import Dict, List

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import Joy

from real_robot_control import (
    control_gripper,
    check_franka_running,
    check_available_topics,
    cleanup,
)


def print_topics_report():
    """Print a report of available ROS2 topics"""
    print("📡 Available ROS2 Topics")
    print("=" * 60)

    topics = check_available_topics()
    if not topics:
        print("❌ No ROS2 topics found!")
        print("   Is ROS2 sourced? Is the control PC running?")
        return False

    # Categorize topics
    gripper_topics = [t for t in topics if 'gripper' in t.lower()]
    joint_topics = [t for t in topics if 'joint' in t.lower()]
    joy_topics = [t for t in topics if 'joy' in t.lower()]

    if gripper_topics:
        print("\n🤏 Gripper Topics:")
        for t in sorted(gripper_topics):
            print(f"   {t}")

    if joint_topics:
        print("\n📊 Joint Topics:")
        for t in sorted(set(joint_topics) - set(gripper_topics)):
            print(f"   {t}")

    if joy_topics:
        print("\n🖱️ Joy Topics:")
        for t in sorted(joy_topics):
            print(f"   {t}")

    # Run checks
    print("\n" + "=" * 60)
    print("🔍 Connectivity Checks:")
    checks = check_franka_running()
    for check, status in checks.items():
        icon = "✅" if status else "❌"
        print(f"   {icon} {check}")

    print("=" * 60)
    return checks.get('gripper_move', False)


def run_automated_test() -> Dict:
    """Run automated gripper test without SpaceMouse"""
    print("🧪 Running Automated Gripper Test")
    print("=" * 60)

    try:
        # Test opening (block=True so each step completes before next)
        print("\n📋 Test 1: Opening gripper...")
        result = control_gripper("open", block=True)
        if result.get('success'):
            print(f"✅ {result.get('message')}")
        else:
            print(f"❌ Failed to open: {result.get('error')}")
            return result

        time.sleep(2.0)

        # Test half-open
        print("\n📋 Test 2: Half-open gripper...")
        result = control_gripper("half", block=True)
        if result.get('success'):
            print(f"✅ {result.get('message')}")
        else:
            print(f"❌ Failed to half-open: {result.get('error')}")
            return result

        time.sleep(2.0)

        # Test closing
        print("\n📋 Test 3: Closing gripper...")
        result = control_gripper("close", block=True)
        if result.get('success'):
            print(f"✅ {result.get('message')}")
        else:
            print(f"❌ Failed to close: {result.get('error')}")
            return result

        time.sleep(2.0)

        # Test opening again
        print("\n📋 Test 4: Opening gripper again...")
        result = control_gripper("open", block=True)
        if result.get('success'):
            print(f"✅ {result.get('message')}")
        else:
            print(f"❌ Failed to open: {result.get('error')}")
            return result

        return {
            "success": True,
            "message": "All automated tests passed",
        }

    except Exception as e:
        return {"success": False, "error": f"Test failed: {str(e)}"}


class GripperTestNode(Node):
    """ROS2 node for SpaceMouse gripper control"""

    def __init__(self, joy_topic: str):
        super().__init__("gripper_test_node")
        self.joy_topic = joy_topic
        self._latest_joy: Joy | None = None
        self._joy_lock = threading.Lock()
        self._last_button_0 = False
        self._last_button_1 = False

        self.create_subscription(Joy, joy_topic, self._joy_callback, 10)
        self.get_logger().info(f"Subscribed to {joy_topic}")

    def _joy_callback(self, msg: Joy) -> None:
        with self._joy_lock:
            self._latest_joy = msg

    def check_button_presses(self) -> tuple[bool, bool]:
        """
        Check button presses with edge detection.
        Returns (button_0_pressed, button_1_pressed)
        """
        with self._joy_lock:
            if self._latest_joy is None:
                return False, False

            buttons = self._latest_joy.buttons
            if len(buttons) < 2:
                return False, False

            button_0_current = buttons[0] == 1
            button_1_current = buttons[1] == 1

            # Edge detection: trigger on rising edge only
            button_0_pressed = button_0_current and not self._last_button_0
            button_1_pressed = button_1_current and not self._last_button_1

            self._last_button_0 = button_0_current
            self._last_button_1 = button_1_current

            return button_0_pressed, button_1_pressed


def run_spacemouse_control(node: GripperTestNode) -> None:
    """Main control loop for SpaceMouse gripper control.

    Uses non-blocking gripper commands so pressing Open can interrupt Close
    when the gripper is grasping an object (close would otherwise block
    waiting for target width that cannot be reached).
    """
    print("\n" + "=" * 60)
    print("🖱️ SpaceMouse Gripper Control")
    print("=" * 60)
    print("   Button 0 (left):  Close gripper")
    print("   Button 1 (right): Open gripper")
    print("   Press Ctrl+C to stop")
    print("=" * 60)

    loop_count = 0

    try:
        while rclpy.ok():
            button_0_pressed, button_1_pressed = node.check_button_presses()

            if button_0_pressed:
                print("\n🔴 Button 0 pressed -> Closing gripper...")
                result = control_gripper("close")
                if result.get('success'):
                    print(f"✅ {result.get('message')}")
                else:
                    print(f"❌ Failed: {result.get('error')}")

            elif button_1_pressed:
                print("\n🟢 Button 1 pressed -> Opening gripper...")
                result = control_gripper("open")
                if result.get('success'):
                    print(f"✅ {result.get('message')}")
                else:
                    print(f"❌ Failed: {result.get('error')}")

            # Status update every 2 seconds
            loop_count += 1
            if loop_count % 20 == 0:
                print(".", end="", flush=True)

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n👋 Stopped by user")


def main():
    parser = argparse.ArgumentParser(
        description="Simple gripper test for real Franka Panda robot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_gripper.py                      # SpaceMouse control
  python test_gripper.py --check-topics       # Diagnostics only
  python test_gripper.py --test-only          # Automated test
  python test_gripper.py --joy-topic /joy     # Custom joy topic

Prerequisites:
  1. ros2 launch franka_bringup franka.launch.py robot_ip:=192.168.1.101
  2. ros2 run spacenav spacenav_node --ros-args -r /spacenav/joy:=/joy
        """
    )
    parser.add_argument('--check-topics', action='store_true',
                       help='Only check available topics and exit')
    parser.add_argument('--test-only', action='store_true',
                       help='Run automated test without SpaceMouse')
    parser.add_argument('--joy-topic', default='/spacenav/joy',
                       help='Joy topic from SpaceMouse (default: /spacenav/joy)')

    args = parser.parse_args()

    print("🤏 Real Robot Gripper Test Script")
    print("=" * 60)
    print(f"   Robot IP:   192.168.1.101")
    print(f"   Control PC: 192.168.1.2")
    print("=" * 60)

    # Check topics mode
    if args.check_topics:
        print_topics_report()
        return

    # Pre-flight checks
    print("\n🔍 Running pre-flight checks...")
    checks = check_franka_running()

    if not checks.get('ros2_available'):
        print("❌ ROS2 topics not accessible. Is ROS2 sourced?")
        sys.exit(1)

    if not checks.get('joint_states'):
        print("❌ Joint states topic not found. Is franka_ros2 running on the control PC?")
        print("   Start it with: ros2 launch franka_bringup franka.launch.py robot_ip:=192.168.1.101")
        sys.exit(1)

    if not checks.get('gripper_move'):
        print("❌ Gripper topics not found. Is the gripper controller running?")
        sys.exit(1)

    print("✅ Pre-flight checks passed")

    # Automated test mode
    if args.test_only:
        result = run_automated_test()
        print("\n" + "=" * 60)
        print("📋 TEST RESULT")
        print("=" * 60)
        if result.get('success'):
            print(f"✅ Status: SUCCESS")
            print(f"💬 Message: {result.get('message')}")
        else:
            print(f"❌ Status: FAILED")
            print(f"💬 Error: {result.get('error')}")
        print("=" * 60)
        return

    # SpaceMouse control mode
    # Initialize ROS2
    rclpy.init()

    try:
        # Create gripper test node
        node = GripperTestNode(joy_topic=args.joy_topic)

        # Spin in executor
        executor = SingleThreadedExecutor()
        executor.add_node(node)

        def spin():
            try:
                executor.spin()
            except Exception:
                pass

        exec_thread = threading.Thread(target=spin, daemon=True)
        exec_thread.start()
        time.sleep(0.5)

        # Check if SpaceMouse is available
        print("\n🖱️ Checking for SpaceMouse...")
        time.sleep(1.0)

        if node._latest_joy is None:
            print("⚠️ No SpaceMouse detected on topic:", args.joy_topic)
            print("   Make sure spacenav is running:")
            print(f"     ros2 run spacenav spacenav_node --ros-args -r /spacenav/joy:={args.joy_topic}")
            print("\n💡 Tip: Use --test-only for automated testing without SpaceMouse")
            executor.shutdown()
            node.destroy_node()
            rclpy.shutdown()
            sys.exit(1)

        print("✅ SpaceMouse detected")

        # Run control loop
        run_spacemouse_control(node)

    except KeyboardInterrupt:
        print("\n👋 Interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        try:
            executor.shutdown()
            node.destroy_node()
            rclpy.shutdown()
        except Exception:
            pass
        try:
            cleanup()
        except Exception:
            pass


if __name__ == "__main__":
    main()
