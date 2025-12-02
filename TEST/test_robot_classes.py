#!/usr/bin/env python3
"""
Test that robot classes can be instantiated from configs.
"""

from lerobot_robot_ros import PandaROSConfig, PandaROSPositionConfig
from lerobot.robots.utils import make_robot_from_config

def test_robot_creation():
    print("=" * 60)
    print("Testing Robot Class Instantiation")
    print("=" * 60)

    # Test PandaROS (Joint Trajectory)
    print("\n1. Testing PandaROS (Joint Trajectory Control):")
    config1 = PandaROSConfig(id="test_panda")
    try:
        robot1 = make_robot_from_config(config1)
        print(f"   ✓ Created robot: {robot1.__class__.__name__}")
        print(f"   ✓ Robot type: {type(robot1)}")
        print(f"   ✓ Has cameras: {list(robot1.cameras.keys())}")
    except Exception as e:
        print(f"   ✗ Failed to create robot: {e}")

    # Test PandaROSPosition (Joint Position - Fast)
    print("\n2. Testing PandaROSPosition (Fast Position Control):")
    config2 = PandaROSPositionConfig(id="test_panda_position")
    try:
        robot2 = make_robot_from_config(config2)
        print(f"   ✓ Created robot: {robot2.__class__.__name__}")
        print(f"   ✓ Robot type: {type(robot2)}")
        print(f"   ✓ Has cameras: {list(robot2.cameras.keys())}")
    except Exception as e:
        print(f"   ✗ Failed to create robot: {e}")

    print("\n" + "=" * 60)
    print("Robot instantiation test completed!")
    print("=" * 60)

if __name__ == "__main__":
    test_robot_creation()
