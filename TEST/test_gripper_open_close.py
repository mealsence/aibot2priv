#!/usr/bin/env python3
"""
Simple script to open and close the gripper.

This script demonstrates basic gripper control by opening and closing the gripper
with a delay between actions.
"""

import sys
import time
from pathlib import Path

# Add the isaac_franka_moveit_perception directory to the path
sys.path.insert(0, str(Path(__file__).parent / "isaac_franka_moveit_perception"))

from gripper_control_module import control_gripper, cleanup


def main():
    """Open and close the gripper with delays."""
    print("=" * 60)
    print("Gripper Open/Close Test Script")
    print("=" * 60)
    
    try:
        # Open the gripper
        print("\n1. Opening gripper...")
        result = control_gripper("open")
        print(f"   Result: {result}")
        
        if result.get("success"):
            print("   ✅ Gripper opened successfully")
        else:
            print(f"   ❌ Failed to open gripper: {result.get('error', 'Unknown error')}")
            return
        
        # Wait a bit so you can see the gripper open
        print("\n   ⏳ Waiting 3 seconds...")
        time.sleep(3)
        
        # Close the gripper
        print("\n2. Closing gripper...")
        result = control_gripper("close", force=0.5)
        print(f"   Result: {result}")
        
        if result.get("success"):
            print("   ✅ Gripper closed successfully")
        else:
            print(f"   ❌ Failed to close gripper: {result.get('error', 'Unknown error')}")
            return
        
        # Wait a bit so you can see the gripper close
        print("\n   ⏳ Waiting 3 seconds...")
        time.sleep(3)
        
        print("\n" + "=" * 60)
        print("✅ Test completed successfully!")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Always cleanup ROS2 resources
        print("\n🧹 Cleaning up ROS2 resources...")
        cleanup()
        print("✅ Cleanup complete")


if __name__ == "__main__":
    main()

