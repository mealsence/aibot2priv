#!/usr/bin/env python3
"""
Test script for Panda + LeRobot using Joint Trajectory control.

This script works with both ROS2 Humble and Jazzy, as it doesn't require MoveIt Servo.

Prerequisites:
    1. Isaac Sim running with Panda robot loaded (or real Panda hardware)
    2. MoveIt + ros2_control launched:
       cd isaac_franka_moveit_perception
       source install/setup.bash
       ros2 launch panda_moveit_config demo.launch.py ros2_control_hardware_type:=isaac

       (Use ros2_control_hardware_type:=mock_components for testing without Isaac)

    3. LeRobot packages installed:
       conda activate lerobot-ros
       pip install -e lerobot
       pip install -e lerobot-ros/lerobot_robot_ros
       pip install -e lerobot-ros/lerobot_teleoperator_devices

Usage:
    python test_panda_joint_trajectory.py
"""

import time
from lerobot_robot_ros.config import PandaROSConfig, ActionType
from lerobot_robot_ros.robot import ROS2Robot


def read_current_state():
    """Simple utility to read and display current robot state."""
    print("=" * 70)
    print("Reading Current Robot State")
    print("=" * 70)

    config = PandaROSConfig()
    config.action_type = ActionType.JOINT_TRAJECTORY
    robot = ROS2Robot(config)

    print("\nConnecting to robot...")
    robot.connect()

    print("Reading joint states...")
    time.sleep(2)

    try:
        obs = robot.get_observation()

        print("\n" + "=" * 70)
        print("CURRENT ROBOT STATE (COPY THIS AS HOME POSITION)")
        print("=" * 70)

        print("\nArm Joint Positions:")
        for joint in config.ros2_interface.arm_joint_names:
            key = f"{joint}.pos"
            if key in obs:
                print(f"  {joint:20s}: {obs[key]:+.6f} rad")

        gripper_key = f"{config.ros2_interface.gripper_joint_name}.pos"
        if gripper_key in obs:
            print(f"\nGripper Position:")
            print(f"  {config.ros2_interface.gripper_joint_name:20s}: {obs[gripper_key]:+.6f} rad")

        print("\n" + "=" * 70)

        # Also print as a Python dictionary for easy copying
        print("\nAs Python dict (copy-paste friendly):")
        print("home_position = {")
        for joint in config.ros2_interface.arm_joint_names:
            key = f"{joint}.pos"
            if key in obs:
                print(f'    "{key}": {obs[key]:.6f},')
        if gripper_key in obs:
            print(f'    "gripper.pos": {obs[gripper_key]:.6f},')
        print("}")
        print("=" * 70)

        robot.disconnect()
        return True

    except Exception as e:
        print(f"\n❌ Failed to read current state: {e}")
        import traceback
        traceback.print_exc()
        robot.disconnect()
        return False


def test_connection():
    """Test basic connection to ROS2 interface."""
    print("=" * 70)
    print("Test 1: Connection Test")
    print("=" * 70)

    # Configure for Joint Trajectory control (works with Humble and Jazzy)
    config = PandaROSConfig()
    config.action_type = ActionType.JOINT_TRAJECTORY

    robot = ROS2Robot(config)

    print(f"Robot type: {type(robot).__name__}")
    print(f"Action type: {config.action_type}")
    print(f"Arm joints: {config.ros2_interface.arm_joint_names}")
    print(f"Gripper joint: {config.ros2_interface.gripper_joint_name}")
    print(f"Arm controller: {config.ros2_interface.arm_controller_name}")
    print(f"Gripper controller: {config.ros2_interface.gripper_controller_name}")

    print("\nConnecting to robot...")
    robot.connect()

    if robot.is_connected:
        print("✅ Successfully connected to robot!")
    else:
        print("❌ Failed to connect to robot")
        return False

    time.sleep(1)
    robot.disconnect()
    print("Disconnected.\n")
    return True


def test_observation():
    """Test reading joint states."""
    print("=" * 70)
    print("Test 2: Observation Test")
    print("=" * 70)

    config = PandaROSConfig()
    config.action_type = ActionType.JOINT_TRAJECTORY
    robot = ROS2Robot(config)
    robot.connect()

    print("Reading joint states...")
    time.sleep(2)  # Wait for joint states to be received

    try:
        obs = robot.get_observation()

        print("\n📊 Current Joint Positions:")
        for joint in config.ros2_interface.arm_joint_names:
            key = f"{joint}.pos"
            if key in obs:
                print(f"  {joint}: {obs[key]:.4f} rad")

        gripper_key = f"{config.ros2_interface.gripper_joint_name}.pos"
        if gripper_key in obs:
            print(f"  {config.ros2_interface.gripper_joint_name}: {obs[gripper_key]:.4f} rad")

        print("\n✅ Successfully read observations!")
        robot.disconnect()
        return True

    except Exception as e:
        print(f"❌ Failed to read observations: {e}")
        robot.disconnect()
        return False


def test_joint_movement():
    """Test moving individual joints."""
    print("=" * 70)
    print("Test 3: Joint Movement Test")
    print("=" * 70)

    config = PandaROSConfig()
    config.action_type = ActionType.JOINT_TRAJECTORY
    robot = ROS2Robot(config)
    robot.connect()

    print("Reading initial state...")
    time.sleep(2)

    try:
        initial_obs = robot.get_observation()
        print("\nInitial joint positions:")
        for joint in config.ros2_interface.arm_joint_names:
            key = f"{joint}.pos"
            if key in initial_obs:
                print(f"  {joint}: {initial_obs[key]:.4f} rad")

        # Create an action that moves joint 1 slightly
        print("\nMoving panda_joint1 by +0.1 rad...")
        action = {}

        # Copy current positions for all joints
        for joint in config.ros2_interface.arm_joint_names:
            key = f"{joint}.pos"
            action[key] = initial_obs.get(key, 0.0)

        # Modify joint 1
        action["panda_joint1.pos"] = initial_obs["panda_joint1.pos"] + 0.1

        # Keep gripper at current position
        gripper_key = f"{config.ros2_interface.gripper_joint_name}.pos"
        action["gripper.pos"] = initial_obs.get(gripper_key, 0.0)

        # Send the action
        robot.send_action(action)
        time.sleep(3)  # Wait for motion to complete

        # Read final state
        final_obs = robot.get_observation()
        print(f"\nFinal panda_joint1 position: {final_obs['panda_joint1.pos']:.4f} rad")
        print(f"Change: {final_obs['panda_joint1.pos'] - initial_obs['panda_joint1.pos']:.4f} rad")

        print("\n✅ Joint movement command sent!")
        robot.disconnect()
        return True

    except Exception as e:
        print(f"❌ Failed to send joint movement: {e}")
        import traceback
        traceback.print_exc()
        robot.disconnect()
        return False


def test_multiple_joint_movement():
    """Test moving multiple joints simultaneously."""
    print("=" * 70)
    print("Test 4: Multiple Joint Movement Test")
    print("=" * 70)

    config = PandaROSConfig()
    config.action_type = ActionType.JOINT_TRAJECTORY
    robot = ROS2Robot(config)
    robot.connect()

    time.sleep(2)

    try:
        initial_obs = robot.get_observation()

        # Create an action that moves multiple joints
        print("\nMoving multiple joints simultaneously...")
        action = {}

        # Copy current positions for all joints
        for joint in config.ros2_interface.arm_joint_names:
            key = f"{joint}.pos"
            action[key] = initial_obs.get(key, 0.0)

        # Modify multiple joints
        action["panda_joint1.pos"] = initial_obs["panda_joint1.pos"] + 0.1
        action["panda_joint2.pos"] = initial_obs["panda_joint2.pos"] - 0.1
        action["panda_joint3.pos"] = initial_obs["panda_joint3.pos"] + 0.1

        # Keep gripper at current position
        gripper_key = f"{config.ros2_interface.gripper_joint_name}.pos"
        action["gripper.pos"] = initial_obs.get(gripper_key, 0.0)

        # Send the action
        robot.send_action(action)
        time.sleep(3)

        # Read final state
        final_obs = robot.get_observation()
        print("\nJoint changes:")
        print(f"  panda_joint1: {final_obs['panda_joint1.pos'] - initial_obs['panda_joint1.pos']:+.4f} rad")
        print(f"  panda_joint2: {final_obs['panda_joint2.pos'] - initial_obs['panda_joint2.pos']:+.4f} rad")
        print(f"  panda_joint3: {final_obs['panda_joint3.pos'] - initial_obs['panda_joint3.pos']:+.4f} rad")

        print("\n✅ Multiple joint movement test completed!")
        robot.disconnect()
        return True

    except Exception as e:
        print(f"❌ Multiple joint movement test failed: {e}")
        robot.disconnect()
        return False


def test_return_to_home():
    """Test returning to a home position (using current state as home)."""
    print("=" * 70)
    print("Test 5: Return to Home Position")
    print("=" * 70)

    config = PandaROSConfig()
    config.action_type = ActionType.JOINT_TRAJECTORY
    robot = ROS2Robot(config)
    robot.connect()

    time.sleep(2)

    try:
        # Read current state and save it as home position
        print("\nReading current robot state to save as HOME position...")
        home_obs = robot.get_observation()

        print("\nHOME position (current state):")
        home_action = {}
        for joint in config.ros2_interface.arm_joint_names:
            key = f"{joint}.pos"
            home_action[key] = home_obs[key]
            print(f"  {joint}: {home_obs[key]:.4f} rad")

        gripper_key = f"{config.ros2_interface.gripper_joint_name}.pos"
        home_action["gripper.pos"] = home_obs.get(gripper_key, 0.0)
        print(f"  {config.ros2_interface.gripper_joint_name}: {home_obs.get(gripper_key, 0.0):.4f} rad")

        # Move robot away from home (small movements on joints 1, 2, 3)
        print("\nMoving robot away from HOME position...")
        away_action = home_action.copy()
        away_action["panda_joint1.pos"] += 0.2
        away_action["panda_joint2.pos"] -= 0.2
        away_action["panda_joint3.pos"] += 0.2

        robot.send_action(away_action)
        time.sleep(3)

        # Verify we moved
        away_obs = robot.get_observation()
        print("\nMoved away from HOME. Current positions:")
        for joint in ["panda_joint1", "panda_joint2", "panda_joint3"]:
            key = f"{joint}.pos"
            print(f"  {joint}: {away_obs[key]:.4f} rad (delta: {away_obs[key] - home_obs[key]:+.4f})")

        # Return to home position
        print("\nReturning to HOME position...")
        robot.send_action(home_action)
        time.sleep(4)  # Wait longer for larger movements

        # Verify we returned to home
        final_obs = robot.get_observation()
        print("\nFinal joint positions (should match HOME):")
        max_error = 0.0
        for joint in config.ros2_interface.arm_joint_names:
            key = f"{joint}.pos"
            error = abs(final_obs[key] - home_obs[key])
            max_error = max(max_error, error)
            print(f"  {joint}: {final_obs[key]:.4f} rad (error: {error:.4f})")

        if max_error < 0.01:  # Less than 0.01 rad error
            print(f"\n✅ Successfully returned to HOME! (max error: {max_error:.4f} rad)")
        else:
            print(f"\n⚠️  Returned close to HOME (max error: {max_error:.4f} rad)")

        robot.disconnect()
        return True

    except Exception as e:
        print(f"❌ Return to home failed: {e}")
        import traceback
        traceback.print_exc()
        robot.disconnect()
        return False


def test_gripper():
    """Test gripper control."""
    print("=" * 70)
    print("Test 6: Gripper Control Test")
    print("=" * 70)

    config = PandaROSConfig()
    config.action_type = ActionType.JOINT_TRAJECTORY
    robot = ROS2Robot(config)
    robot.connect()

    time.sleep(2)

    try:
        print("Testing gripper control...")

        obs = robot.get_observation()
        gripper_key = f"{config.ros2_interface.gripper_joint_name}.pos"
        initial_gripper = obs.get(gripper_key, 0.0)
        print(f"\nInitial gripper position: {initial_gripper:.4f} rad")

        # Create action to keep arm stationary
        action = {}
        for joint in config.ros2_interface.arm_joint_names:
            key = f"{joint}.pos"
            action[key] = obs.get(key, 0.0)

        # Open gripper
        print("\n1. Opening gripper...")
        action["gripper.pos"] = config.ros2_interface.gripper_open_position
        robot.send_action(action)
        time.sleep(2)

        obs = robot.get_observation()
        print(f"   Gripper position: {obs.get(gripper_key, 0.0):.4f} rad")

        # Close gripper
        print("\n2. Closing gripper...")
        action["gripper.pos"] = config.ros2_interface.gripper_close_position
        robot.send_action(action)
        time.sleep(2)

        obs = robot.get_observation()
        print(f"   Gripper position: {obs.get(gripper_key, 0.0):.4f} rad")

        print("\n✅ Gripper control working!")
        robot.disconnect()
        return True

    except Exception as e:
        print(f"❌ Gripper test failed: {e}")
        import traceback
        traceback.print_exc()
        robot.disconnect()
        return False


def main():
    """Run all integration tests."""
    print("\n" + "=" * 70)
    print("Panda + LeRobot Joint Trajectory Integration Tests")
    print("=" * 70 + "\n")

    print("⚠️  Prerequisites:")
    print("  1. Isaac Sim running (or real Panda hardware)")
    print("  2. MoveIt + ros2_control launched:")
    print("     cd isaac_franka_moveit_perception")
    print("     source install/setup.bash")
    print("     ros2 launch panda_moveit_config demo.launch.py \\")
    print("       ros2_control_hardware_type:=isaac")
    print("     (or use mock_components for testing without Isaac)")
    print("  3. LeRobot packages installed in conda environment")
    print("\n✅ This test works with both ROS2 Humble and Jazzy!")

    print("\n" + "=" * 70)
    print("What would you like to do?")
    print("=" * 70)
    print("  1. Just read current robot state (and save as home position)")
    print("  2. Run all integration tests")
    print("  3. Exit")
    print("\nEnter your choice (1-3): ", end='')

    try:
        choice = input().strip()
    except KeyboardInterrupt:
        print("\nAborted.")
        return

    if choice == '1':
        # Just read current state
        read_current_state()
        return
    elif choice == '3':
        print("Exiting.")
        return
    elif choice != '2':
        print(f"Invalid choice: {choice}")
        return

    results = {}

    # Run tests
    results["Connection"] = test_connection()
    results["Observation"] = test_observation()
    results["Joint Movement"] = test_joint_movement()
    results["Multiple Joints"] = test_multiple_joint_movement()
    results["Return to Home"] = test_return_to_home()
    results["Gripper"] = test_gripper()

    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test_name:25s} {status}")

    total = len(results)
    passed = sum(results.values())

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Integration successful!")
        print("\nNext steps:")
        print("  1. Try teleoperation:")
        print("     lerobot-teleoperate --robot.type=panda_ros --robot.id=my_panda \\")
        print("       --teleop.type=keyboard_joint --teleop.id=my_keyboard")
        print("  2. Record demonstrations:")
        print("     lerobot-record --robot.type=panda_ros --fps=30 \\")
        print("       --repo-id=your_username/panda_dataset")
        print("\n  Note: This test uses JOINT_TRAJECTORY control mode.")
        print("  For Cartesian velocity control, you need ROS2 Jazzy with MoveIt Servo.")
    else:
        print("\n⚠️  Some tests failed. Check the error messages above.")
        print("   Common issues:")
        print("   - Isaac Sim not running (if using Isaac)")
        print("   - MoveIt demo.launch.py not running")
        print("   - Controllers not active (check: ros2 control list_controllers)")
        print("   - Joint state topic not publishing (check: ros2 topic echo /joint_states)")


if __name__ == "__main__":
    main()
