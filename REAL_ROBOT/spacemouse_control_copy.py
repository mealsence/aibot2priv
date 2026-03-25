#!/usr/bin/env python3
"""
Simple SpaceMouse Control for Real Franka Panda Robot

SpaceMouse teleoperation for the real robot. Subscribes to Joy messages from
the SpaceMouse (spacenav), converts end-effector deltas to joint commands via
IK, and sends them to the real robot.

Based on the simulation implementation in lerobot_teleoperator_devices:
  - spacemouse_ee_panda.py (Joy → delta_x, delta_y, delta_z)
  - processors/delta_to_joints.py (IK via placo)

Prerequisites:
  1. SpaceMouse driver running:
     ros2 run spacenav spacenav_node --ros-args -r /spacenav/joy:=/joy
     (or use default /spacenav/joy with --joy-topic /spacenav/joy)
  2. Franka robot running on control PC:
     ros2 launch franka_bringup franka.launch.py robot_ip:=192.168.1.101

Usage:
  cd REAL_ROBOT && python spacemouse_control.py
  python spacemouse_control.py --joy-topic /joy
  python spacemouse_control.py --linear-step 0.005  # finer control
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

# Add repo root for imports
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import Joy

# Real robot control (same folder)
from real_robot_control import (
    _arm_controller,
    get_current_arm_position,
    check_franka_running,
    cleanup,
)


def _resolve_urdf() -> str:
    """Resolve Panda URDF path, handling package:// in mesh references."""
    urdf_path = REPO_ROOT / "isaac_franka_moveit_perception" / "src" / "panda_description" / "urdf" / "panda.urdf"
    if not urdf_path.exists():
        raise FileNotFoundError(f"URDF not found: {urdf_path}")

    urdf_text = urdf_path.read_text()
    if "package://" not in urdf_text:
        return str(urdf_path)

    # Resolve package://panda_description/ to absolute path
    panda_desc = REPO_ROOT / "isaac_franka_moveit_perception" / "src" / "panda_description"
    urdf_text = urdf_text.replace(
        "package://panda_description/",
        f"{panda_desc.as_posix()}/",
    )
    cache_dir = REPO_ROOT / "lerobot_teleoperator_devices" / "lerobot_teleoperator_devices" / "processors" / "_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    resolved_path = cache_dir / "panda_resolved.urdf"
    resolved_path.write_text(urdf_text)
    return str(resolved_path)


def _load_kinematics():
    """Load RobotKinematics from lerobot (requires placo)."""
    try:
        from lerobot.model.kinematics import RobotKinematics
    except ImportError as e:
        raise ImportError(
            "lerobot with placo is required for IK. Install with:\n"
            "  pip install lerobot[placo-dep]\n"
            "  or: pip install placo"
        ) from e

    urdf_path = _resolve_urdf()
    joint_names = [
        "panda_joint1", "panda_joint2", "panda_joint3",
        "panda_joint4", "panda_joint5", "panda_joint6", "panda_joint7",
    ]
    return RobotKinematics(
        urdf_path=urdf_path,
        target_frame_name="panda_hand",
        joint_names=joint_names,
    )


# SpaceMouse config (same as spacemouse_ee_panda)
DEAD_ZONE = 0.05
LINEAR_STEP_M = 0.01
INVERT_X = True
INVERT_Y = False
INVERT_Z = False
WORKSPACE_MIN = (-0.6, -0.6, 0.0)
WORKSPACE_MAX = (0.6, 0.6, 0.8)
POSITION_WEIGHT = 1.0
ORIENTATION_WEIGHT = 0.1


def apply_deadzone(value: float, threshold: float) -> float:
    return 0.0 if abs(value) < threshold else value


def joy_to_delta(axes: list, linear_step: float, dead_zone: float) -> tuple[float, float, float]:
    """Convert Joy axes to (delta_x, delta_y, delta_z) in meters."""
    if len(axes) < 3:
        return 0.0, 0.0, 0.0
    axes = list(axes) + [0.0] * (6 - len(axes))
    orig_x, orig_y, orig_z = axes[:3]

    mapped_x = -orig_y if INVERT_Y else orig_y
    mapped_y = -orig_x if INVERT_X else orig_x
    mapped_z = orig_z if not INVERT_Z else -orig_z

    mapped_x = apply_deadzone(mapped_x, dead_zone)
    mapped_y = apply_deadzone(mapped_y, dead_zone)
    mapped_z = apply_deadzone(mapped_z, dead_zone)

    delta_x = mapped_x * linear_step
    delta_y = mapped_y * linear_step
    delta_z = mapped_z * linear_step
    return delta_x, delta_y, delta_z


def joy_to_gripper(buttons: list, last_gripper_trigger: float) -> tuple[float | None, float]:
    """
    Button 0: close (0.0), Button 1: open (1.0).
    Returns (gripper_cmd or None, timestamp of trigger).
    Uses last_gripper_trigger to debounce (min 0.3s between gripper commands).
    """
    if len(buttons) < 2:
        return None, last_gripper_trigger
    now = time.time()
    if now - last_gripper_trigger < 0.3:
        return None, last_gripper_trigger
    if buttons[0] == 1:
        return 0.0, now
    if buttons[1] == 1:
        return 1.0, now
    return None, last_gripper_trigger


class SpaceMouseControlNode(Node):
    """ROS2 node: subscribes to Joy, runs control loop, sends joint commands."""

    def __init__(self, joy_topic: str, linear_step: float, use_gripper: bool):
        super().__init__("spacemouse_control_real")
        self.joy_topic = joy_topic
        self.linear_step = linear_step
        self.use_gripper = use_gripper
        self._latest_joy: Joy | None = None
        self._joy_lock = threading.Lock()
        self._last_gripper_trigger = 0.0

        self.create_subscription(Joy, joy_topic, self._joy_callback, 10)
        self.get_logger().info(f"Subscribed to {joy_topic}")

    def _joy_callback(self, msg: Joy) -> None:
        with self._joy_lock:
            self._latest_joy = msg

    def get_delta_and_gripper(self) -> tuple[float, float, float, float | None]:
        with self._joy_lock:
            if self._latest_joy is None:
                return 0.0, 0.0, 0.0, None
            delta = joy_to_delta(
                self._latest_joy.axes,
                self.linear_step,
                DEAD_ZONE,
            )
            if self.use_gripper:
                gripper, self._last_gripper_trigger = joy_to_gripper(
                    self._latest_joy.buttons, self._last_gripper_trigger
                )
            else:
                gripper = None
            return (*delta, gripper)


def run_control_loop(
    node: SpaceMouseControlNode,
    kinematics,
    linear_step: float,
    use_gripper: bool,
    control_hz: float,
    dry_run: bool,
) -> None:
    """Main control loop: delta → IK → joint command.

    Key design decisions (matching the working simulation pipeline):
    - Always FK from REAL robot joints each iteration (no drift if commands drop)
    - Publish position-only JointTrajectory to topic (not action interface)
    - No time_from_start/velocities/accelerations (controller handles interpolation)
    """
    import numpy as np

    dt = 1.0 / control_hz
    iteration = 0
    cmds_sent = 0
    t_start = time.time()

    print(f"   Control rate: {control_hz:.0f} Hz, linear step: {linear_step:.4f} m")

    # Grab the initial orientation and position before the loop starts
    initial_positions = _arm_controller.current_joint_positions
    initial_pose = kinematics.forward_kinematics(np.rad2deg(np.array(initial_positions[:7])))
    fixed_target_orientation = initial_pose[:3, :3].copy() # Keep rotation constant
    desired_translation = initial_pose[:3, 3].copy()

    while rclpy.ok():
        loop_start = time.time()
        iteration += 1

        delta_x, delta_y, delta_z, gripper_cmd = node.get_delta_and_gripper()

        # Read current joint positions (updated by executor callback)
        current_positions = _arm_controller.current_joint_positions
        if current_positions is None:
            if iteration % 30 == 0:
                print("⏳ Waiting for joint state data...")
            time.sleep(dt)
            continue

        joint_obs_rad = np.array(current_positions[:7]) 
        joint_obs_deg = np.rad2deg(joint_obs_rad)

        # FK from REAL robot joints each iteration (safe, no drift)
        current_pose = kinematics.forward_kinematics(joint_obs_deg)

        # Apply spacemouse delta to current EE position
        delta_vector = np.array([delta_x, delta_y, delta_z], dtype=float)

        # Skip IK if no movement requested (save compute)
        if np.linalg.norm(delta_vector) < 1e-7 and gripper_cmd is None:
            time.sleep(dt)
            continue
        # if iteration % 10 == 0:
        #     print(f"current pose: \n{current_pose}")
        # desired_pose = current_pose.copy()
        # if iteration % 10 == 0:
        #     print(f"delta vector: \n{delta_vector}")
        # desired_translation = desired_pose[:3, 3] + delta_vector
        # if iteration % 10 == 0:
        #     print(f"desired after delta: \n{desired_translation}")
        desired_translation += delta_vector
        desired_translation = np.clip(
            desired_translation,
            np.array(WORKSPACE_MIN),
            np.array(WORKSPACE_MAX),
        )

        # Construct a fresh 4x4 matrix from our desired states.
        desired_pose = np.eye(4)
        desired_pose[:3, 3] = desired_translation
        desired_pose[:3, :3] = fixed_target_orientation

        # if iteration % 10 == 0:
        #     print(f"desired before overwrite: \n{desired_pose}")
        # INJECT THE FIX HERE: 
        # Overwrite the drifting current orientation with your fixed initial orientation
        # desired_pose[:3, :3] = fixed_target_orientation
        # if iteration % 10 == 0:
        #     print(f"desired after overwrite: \n{desired_pose}")

        # IK: solve for joint angles that reach desired EE pose
        q_target_deg = kinematics.inverse_kinematics(
            joint_obs_deg,
            desired_pose,
            position_weight=POSITION_WEIGHT,
            orientation_weight=ORIENTATION_WEIGHT,
        )
        q_target_rad = np.deg2rad(q_target_deg[:7])

        # Send command (non-blocking topic publish, matching sim approach)
        if not dry_run:
            sent = _arm_controller.publish_joint_command(list(q_target_rad))
            if sent:
                cmds_sent += 1

            if use_gripper and gripper_cmd is not None:
                from real_robot_control import control_gripper
                action = "close" if gripper_cmd < 0.5 else "open"
                control_gripper(action)

        # Periodic status (every 5 seconds)
        if iteration % int(control_hz * 5) == 0:
            elapsed = time.time() - t_start
            ee_pos = current_pose[:3, 3]
            print(
                f"📊 [{elapsed:.0f}s] cmds={cmds_sent}, "
                f"EE=({ee_pos[0]:.3f}, {ee_pos[1]:.3f}, {ee_pos[2]:.3f}), "
                f"delta=({delta_x:.4f}, {delta_y:.4f}, {delta_z:.4f})"
            )

        # Maintain control rate
        loop_elapsed = time.time() - loop_start
        sleep_time = dt - loop_elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)


def main():
    parser = argparse.ArgumentParser(
        description="SpaceMouse control for real Franka Panda",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Prerequisites:
  1. ros2 run spacenav spacenav_node --ros-args -r /spacenav/joy:=/joy
  2. ros2 launch franka_bringup franka.launch.py robot_ip:=192.168.1.101
        """,
    )
    parser.add_argument(
        "--joy-topic",
        default="/spacenav/joy",
        help="Joy topic from SpaceMouse (default: /spacenav/joy)",
    )
    parser.add_argument(
        "--linear-step",
        type=float,
        default=0.003,
        help="Meters per full SpaceMouse deflection (default: 0.01)",
    )
    parser.add_argument(
        "--no-gripper",
        action="store_true",
        help="Disable gripper control (buttons)",
    )
    parser.add_argument(
        "--control-hz",
        type=float,
        default=30.0,
        help="Control loop rate (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands only, do not move robot",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Check SpaceMouse and robot connectivity, then exit",
    )
    args = parser.parse_args()

    print("🖱️  SpaceMouse Control for Real Franka Panda")
    print("=" * 60)

    # Pre-flight checks (uses subprocess, no rclpy needed yet)
    print("\n🔍 Pre-flight checks...")
    checks = check_franka_running()
    if not checks.get("joint_states"):
        print("❌ Joint states not found. Is franka_ros2 running on the control PC?")
        sys.exit(1)
    print("✅ Franka robot: OK")

    # Load kinematics
    print("🔧 Loading IK (placo)...")
    try:
        kinematics = _load_kinematics()
        print("✅ IK loaded")
    except Exception as e:
        print(f"❌ {e}")
        sys.exit(1)

    if args.check_only:
        print("\n✅ All checks passed. Run without --check-only to start control.")
        return

    # Initialize arm controller (will init rclpy and create node)
    if not _arm_controller._ensure_ros_init():
        print("❌ Failed to initialize arm controller")
        sys.exit(1)
    executor = SingleThreadedExecutor()
    executor.add_node(_arm_controller.node)

    # Create SpaceMouse node
    node = SpaceMouseControlNode(
        joy_topic=args.joy_topic,
        linear_step=args.linear_step,
        use_gripper=not args.no_gripper,
    )
    executor.add_node(node)

    # Run executor in background
    def spin():
        try:
            executor.spin()
        except Exception:
            pass

    exec_thread = threading.Thread(target=spin, daemon=True)
    exec_thread.start()
    time.sleep(0.5)

    print("\n" + "=" * 60)
    print("🖱️  SpaceMouse control ACTIVE")
    print("   Move the SpaceMouse to control the end-effector.")
    if not args.no_gripper:
        print("   Button 0: close gripper, Button 1: open gripper")
    print("   Press Ctrl+C to stop.")
    print("=" * 60)

    try:
        run_control_loop(
            node=node,
            kinematics=kinematics,
            linear_step=args.linear_step,
            use_gripper=not args.no_gripper,
            control_hz=args.control_hz,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        print("\n👋 Stopped by user")
    finally:
        executor.shutdown()
        node.destroy_node()
        cleanup()


if __name__ == "__main__":
    main()
