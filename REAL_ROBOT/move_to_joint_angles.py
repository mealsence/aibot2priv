#!/usr/bin/env python3
"""
Move Real Robot to Specific Joint Angles

This script moves a REAL Franka Panda robot to specific joint angles.
Adapted from the Isaac Sim version for use with franka_ros2.

Network Setup:
    Robot IP:     192.168.1.101
    Control PC:   192.168.1.2   (runs franka_ros2 bringup)
    Workstation:  this machine  (runs this script)

Prerequisites:
    On control PC (192.168.1.2):
        ros2 launch franka_bringup franka.launch.py robot_ip:=192.168.1.101

Usage:
    python move_to_joint_angles.py                  # Move to target angles (with confirmation)
    python move_to_joint_angles.py --check-topics   # Check available ROS2 topics
    python move_to_joint_angles.py --dry-run        # Check everything without moving
    python move_to_joint_angles.py --no-confirm     # Skip confirmation prompt
    python move_to_joint_angles.py --duration 5     # Custom movement duration (seconds)
"""

import argparse
import sys
import time
from typing import Dict, List

from real_robot_control import (
    _arm_controller,
    get_current_arm_position,
    check_franka_running,
    check_available_topics,
    cleanup,
    PANDA_JOINT_NAMES,
    PANDA_JOINT_LIMITS,
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
    franka_topics = [t for t in topics if 'franka' in t.lower() or 'panda' in t.lower()]
    joint_topics = [t for t in topics if 'joint' in t.lower()]
    controller_topics = [t for t in topics if 'controller' in t.lower()]
    other_topics = [t for t in topics if t not in franka_topics + joint_topics + controller_topics]

    if franka_topics:
        print("\n🤖 Franka/Panda Topics:")
        for t in sorted(franka_topics):
            print(f"   {t}")

    if joint_topics:
        print("\n📊 Joint Topics:")
        for t in sorted(set(joint_topics) - set(franka_topics)):
            print(f"   {t}")

    if controller_topics:
        print("\n🎮 Controller Topics:")
        for t in sorted(set(controller_topics) - set(franka_topics) - set(joint_topics)):
            print(f"   {t}")

    # Run checks
    print("\n" + "=" * 60)
    print("🔍 Connectivity Checks:")
    checks = check_franka_running()
    for check, status in checks.items():
        icon = "✅" if status else "❌"
        print(f"   {icon} {check}")

    print("=" * 60)
    return checks.get('joint_states', False)


def move_to_specific_joint_angles(
    joint_angles: List[float],
    duration_sec: float = 3.0,
    dry_run: bool = False
) -> Dict:
    """
    Move the real robot arm to specific joint angles.

    Args:
        joint_angles: List of 7 joint angles in radians
        duration_sec: Time in seconds to complete the movement
        dry_run: If True, validate everything but don't actually move
    """
    print(f"🎯 {'[DRY RUN] ' if dry_run else ''}Moving robot arm to specific joint angles...")
    print(f"📍 Target joint angles (rad): {[f'{angle:.3f}' for angle in joint_angles]}")

    # Convert to degrees for easier reading
    import math
    joint_angles_deg = [angle * 180.0 / math.pi for angle in joint_angles]
    print(f"📍 Target joint angles (deg): {[f'{angle:.1f}' for angle in joint_angles_deg]}")

    try:
        # Validate joint angles
        if len(joint_angles) != 7:
            return {"success": False, "error": f"Expected 7 joint angles, got {len(joint_angles)}"}

        # Validate against Panda joint limits
        validation = _arm_controller.validate_joint_angles(joint_angles)
        if not validation['valid']:
            print("\n❌ JOINT LIMIT VIOLATIONS:")
            for w in validation['warnings']:
                print(f"   ❌ {w}")
            return {"success": False, "error": "Joint angles exceed Panda limits"}
        else:
            print("✅ All joint angles within Panda limits")

        # Get current position for comparison
        current_result = get_current_arm_position()
        if current_result.get('success'):
            current_angles = current_result.get('joint_angles', [0.0] * 7)
            print(f"📍 Current joint angles (rad): {[f'{angle:.3f}' for angle in current_angles]}")

            # Calculate movement distance
            movement_distance = sum([abs(t - c) for t, c in zip(joint_angles, current_angles)])
            max_single_joint_move = max([abs(t - c) for t, c in zip(joint_angles, current_angles)])
            print(f"📏 Total joint movement: {movement_distance:.3f} rad")
            print(f"📏 Max single joint movement: {max_single_joint_move:.3f} rad ({max_single_joint_move * 180 / math.pi:.1f}°)")

            # Safety warning for large movements
            if max_single_joint_move > 1.5:  # > ~86 degrees
                print("⚠️ WARNING: Large joint movement detected! Moving slowly is recommended.")
                if duration_sec < 5.0:
                    print(f"   Increasing duration from {duration_sec:.1f}s to 5.0s for safety")
                    duration_sec = max(duration_sec, 5.0)
        else:
            print("⚠️ Could not read current joint position (will proceed with caution)")

        if dry_run:
            print("\n🏁 [DRY RUN] All checks passed. Would execute movement here.")
            return {
                "success": True,
                "action": "dry_run",
                "message": "Dry run completed - all checks passed, no movement executed",
                "target_angles": joint_angles,
            }

        # Execute movement
        print(f"\n🚀 Executing movement over {duration_sec:.1f} seconds...")
        success = _arm_controller.send_joint_command(joint_angles, duration_sec=duration_sec)

        if success:
            print("✅ Movement command completed")
            print("⏳ Waiting for robot to settle...")
            time.sleep(1.0)

            # Verify final position
            final_result = get_current_arm_position()
            if final_result.get('success'):
                final_angles = final_result.get('joint_angles', [0.0] * 7)
                print(f"📍 Final joint angles (rad): {[f'{angle:.3f}' for angle in final_angles]}")

                errors = [abs(t - f) for t, f in zip(joint_angles, final_angles)]
                max_error = max(errors)
                avg_error = sum(errors) / len(errors)

                print(f"📊 Position errors — Max: {max_error:.4f} rad, Avg: {avg_error:.4f} rad")

                return {
                    "success": True,
                    "action": "moved_to_target",
                    "message": f"Robot arm moved to target position (max error: {max_error:.4f} rad)",
                    "target_angles": joint_angles,
                    "final_angles": final_angles,
                    "max_error": max_error,
                    "avg_error": avg_error,
                }
            else:
                return {
                    "success": True,
                    "action": "moved_to_target",
                    "message": "Movement command sent (could not verify final position)",
                    "target_angles": joint_angles,
                }
        else:
            return {
                "success": False,
                "error": "Movement command failed — check controller output for details",
            }

    except Exception as e:
        return {"success": False, "error": f"Failed to move robot: {str(e)}"}


def main():
    parser = argparse.ArgumentParser(
        description="Move real Franka Panda robot to specific joint angles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python move_to_joint_angles.py                   # Move with confirmation
  python move_to_joint_angles.py --check-topics    # Diagnostics only
  python move_to_joint_angles.py --dry-run         # Validate without moving
  python move_to_joint_angles.py --no-confirm      # Skip confirmation
  python move_to_joint_angles.py --duration 5      # Slower movement

Network Setup:
  Robot IP:     192.168.1.101
  Control PC:   192.168.1.2
  Prerequisite: ros2 launch franka_bringup franka.launch.py robot_ip:=192.168.1.101
        """
    )
    parser.add_argument('--check-topics', action='store_true',
                       help='Only check available topics and exit')
    parser.add_argument('--dry-run', action='store_true',
                       help='Validate everything but do not move the robot')
    parser.add_argument('--no-confirm', action='store_true',
                       help='Skip user confirmation before moving')
    parser.add_argument('--duration', type=float, default=8.0,
                       help='Movement duration in seconds (default: 8.0, slower = safer)')
    parser.add_argument('--joints', type=float, nargs=7, metavar='J',
                       help='Custom target joint angles (7 values in radians)')

    args = parser.parse_args()

    print("🤖 Real Robot Joint Angle Movement Script")
    print("=" * 60)
    print(f"   Robot IP:   192.168.1.101")
    print(f"   Control PC: 192.168.1.2")
    print("=" * 60)

    # Check topics mode
    if args.check_topics:
        print_topics_report()
        return

    # Target joint angles
    if args.joints:
        target_joint_angles = args.joints
        print(f"\n📋 Using custom joint angles: {[f'{a:.3f}' for a in target_joint_angles]}")
    else:
        target_joint_angles = [-0.159, 0.302, -0.093, -2.255, 0.047, 2.555, 0.498]
        print(f"\n📋 Using default target joint angles:")
        print(f"   {[f'{a:.3f}' for a in target_joint_angles]}")

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

    print("✅ Pre-flight checks passed")

    # Confirmation prompt
    if not args.dry_run and not args.no_confirm:
        print("\n" + "=" * 60)
        print("⚠️  REAL ROBOT MOVEMENT WARNING")
        print("=" * 60)
        print(f"Target angles: {[f'{a:.3f}' for a in target_joint_angles]}")
        print(f"Duration:      {args.duration:.1f} seconds")
        print("")
        print("The robot WILL MOVE. Ensure the workspace is clear.")
        print("=" * 60)

        try:
            response = input("\nProceed? (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                print("❌ Aborted by user")
                return
        except (KeyboardInterrupt, EOFError):
            print("\n❌ Aborted")
            return

    try:
        # Execute movement
        result = move_to_specific_joint_angles(
            target_joint_angles,
            duration_sec=args.duration,
            dry_run=args.dry_run
        )

        # Print result
        print("\n" + "=" * 60)
        print("📋 MOVEMENT RESULT")
        print("=" * 60)

        if result.get('success'):
            print(f"✅ Status: SUCCESS")
            print(f"🎯 Action: {result.get('action')}")
            print(f"💬 Message: {result.get('message')}")

            if 'target_angles' in result:
                print(f"📍 Target: {[f'{a:.3f}' for a in result['target_angles']]}")
            if 'final_angles' in result:
                print(f"📍 Final:  {[f'{a:.3f}' for a in result['final_angles']]}")
            if 'max_error' in result:
                print(f"📊 Max Error: {result['max_error']:.4f} rad")
                print(f"📊 Avg Error: {result['avg_error']:.4f} rad")
        else:
            print(f"❌ Status: FAILED")
            print(f"💬 Error: {result.get('error')}")

        print("=" * 60)

    except KeyboardInterrupt:
        print("\n👋 Interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        try:
            cleanup()
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")


if __name__ == "__main__":
    main()
