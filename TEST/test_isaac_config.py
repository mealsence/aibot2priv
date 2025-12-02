#!/usr/bin/env python3
"""
Test script to verify the PandaROS configurations.
"""

from lerobot_robot_ros import PandaROSConfig, PandaROSPositionConfig

def test_configs():
    print("=" * 60)
    print("Testing Panda Robot Configurations")
    print("=" * 60)

    # Test PandaROSConfig (trajectory control)
    print("\n1. Testing PandaROSConfig (trajectory control):")
    config1 = PandaROSConfig()
    print(f"   Robot type: panda_ros")
    print(f"   Action type: {config1.action_type}")
    print(f"   Cameras: {list(config1.cameras.keys())}")
    if config1.cameras:
        cam = config1.cameras["camera_1"]
        print(f"   Camera config:")
        print(f"     - Type: {cam.type}")
        print(f"     - Topic: {cam.topic}")
        print(f"     - Resolution: {cam.width}x{cam.height}")
        print(f"     - FPS: {cam.fps}")
        print(f"   ✓ PandaROSConfig loaded successfully!")
    else:
        print("   ✗ No cameras configured!")

    # Test PandaROSPositionConfig (fast position control)
    print("\n2. Testing PandaROSPositionConfig (fast position control):")
    config2 = PandaROSPositionConfig()
    print(f"   Robot type: panda_ros_position")
    print(f"   Action type: {config2.action_type}")
    print(f"   Cameras: {list(config2.cameras.keys())}")
    if config2.cameras:
        cam = config2.cameras["camera_1"]
        print(f"   Camera config:")
        print(f"     - Type: {cam.type}")
        print(f"     - Topic: {cam.topic}")
        print(f"     - Resolution: {cam.width}x{cam.height}")
        print(f"     - FPS: {cam.fps}")
        print(f"   ✓ PandaROSPositionConfig loaded successfully!")
    else:
        print("   ✗ No cameras configured!")

    print("\n" + "=" * 60)
    print("Configuration test completed!")
    print("=" * 60)

if __name__ == "__main__":
    test_configs()
