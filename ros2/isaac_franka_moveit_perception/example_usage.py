#!/usr/bin/env python3
"""
Example usage of the gripper control module in other repositories

This demonstrates how to import and use the standalone gripper control module.
"""

# Import the gripper control function
from gripper_control_module import control_gripper, control_arm_home_position, cleanup
from time import sleep


def main():
    """Example of using the gripper control in an LLM-controlled system"""
    
    print("🤖 LLM-controlled Robot System Example")
    print("=" * 40)
    
    try:
        # Example 1: Move arm to home position
        print("\n1. Moving arm to home position...")
        result = control_arm_home_position()
        print(f"   Result: {result}")
        
        sleep(4)
        # Example 2: Simple gripper control
        print("\n2. Opening gripper...")
        result = control_gripper("open")
        print(f"   Result: {result}")
        
        sleep(4)
        # Example 3: Closing gripper with default force
        print("\n3. Closing gripper...")
        result = control_gripper("close")
        print(f"   Result: {result}")
        
        sleep(4)
        # Example 4: Grasping with specific force
        print("\n4. Grasping with custom force...")
        result = control_gripper("grasp", 0.7)
        print(f"   Result: {result}")
        
        sleep(4)
        # Example 5: Error handling
        print("\n5. Testing error handling...")
        result = control_gripper("invalid_action")
        print(f"   Result: {result}")
        
        print("\n✅ All examples completed!")
        
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
    finally:
        # Always cleanup ROS2 resources
        print("\n🧹 Cleaning up...")
        cleanup()


if __name__ == "__main__":
    main()
