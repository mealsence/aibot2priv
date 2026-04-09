#!/usr/bin/env python3
"""
Test Script for Joint Movement

This script tests the joint movement functionality by moving the robot
to the specified joint angles and then back to home position.

Usage:
    python test_joint_movement.py
"""

import time
from move_to_joint_angles import move_to_specific_joint_angles
from gripper_control_module import control_arm_home_position, get_current_arm_position, cleanup


def test_joint_movement():
    """Test moving to specific joint angles and back to home"""
    print("🧪 Testing Robot Joint Movement")
    print("=" * 60)
    
    # Target joint angles from the task
    target_angles = [-0.159, 0.302, -0.093, -2.255, 0.047, 2.555, 0.498]
    
    try:
        # Step 1: Get initial position
        print("\n📍 Step 1: Getting initial robot position...")
        initial_result = get_current_arm_position()
        if initial_result.get('success'):
            print(f"✅ Initial position: {initial_result.get('formatted', 'N/A')}")
        else:
            print(f"⚠️ Could not get initial position: {initial_result.get('error', 'Unknown error')}")
        
        # Step 2: Move to target joint angles
        print("\n🎯 Step 2: Moving to target joint angles...")
        print(f"   Target: {[f'{a:.3f}' for a in target_angles]}")
        
        move_result = move_to_specific_joint_angles(target_angles, duration_sec=4)
        
        if move_result.get('success'):
            print("✅ Successfully moved to target position")
            if 'max_error' in move_result:
                print(f"📊 Position accuracy - Max error: {move_result['max_error']:.4f} rad")
        else:
            print(f"❌ Failed to move to target position: {move_result.get('error')}")
            return False
        
        # Wait at target position
        print("\n⏳ Step 3: Waiting at target position for 2 seconds...")
        time.sleep(2)
        
        # Step 4: Move back to home position
        print("\n🏠 Step 4: Moving back to home position...")
        home_result = control_arm_home_position()
        
        if home_result.get('success'):
            print("✅ Successfully returned to home position")
        else:
            print(f"❌ Failed to return to home position: {home_result.get('error')}")
            return False
        
        # Step 5: Final position verification
        print("\n📍 Step 5: Verifying final position...")
        final_result = get_current_arm_position()
        if final_result.get('success'):
            print(f"✅ Final position: {final_result.get('formatted', 'N/A')}")
        else:
            print(f"⚠️ Could not get final position: {final_result.get('error', 'Unknown error')}")
        
        print("\n🎉 Test completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False


def main():
    """Main test function"""
    try:
        success = test_joint_movement()
        
        print("\n" + "=" * 60)
        print("📋 TEST SUMMARY")
        print("=" * 60)
        
        if success:
            print("✅ All tests PASSED")
            print("🤖 Robot joint movement is working correctly")
        else:
            print("❌ Some tests FAILED")
            print("🔧 Please check the robot configuration and MoveIt setup")
        
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n👋 Test interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error during test: {e}")
    finally:
        # Cleanup resources
        try:
            cleanup()
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")


if __name__ == "__main__":
    main()
