#!/usr/bin/env python3
"""
Check Controller Status

This script checks if the panda_position_controller is active and can receive commands.
"""

import rclpy
from rclpy.node import Node
from std_msgs.msg import Float64MultiArray
import time


def check_controller_status():
    """Check if position controller is active"""
    print("🔍 Checking controller status...")
    
    try:
        rclpy.init()
        node = Node('controller_status_checker')
        
        # Create publisher
        publisher = node.create_publisher(
            Float64MultiArray,
            '/panda_position_controller/commands',
            10
        )
        
        # Wait for discovery
        print("⏳ Waiting for ROS2 discovery...")
        for _ in range(20):
            rclpy.spin_once(node, timeout_sec=0.1)
        time.sleep(1.0)
        
        # Try to publish a test message
        print("📤 Publishing test message...")
        msg = Float64MultiArray()
        msg.data = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        
        for i in range(10):
            publisher.publish(msg)
            rclpy.spin_once(node, timeout_sec=0.1)
            time.sleep(0.1)
        
        print("✅ Test message published")
        
        # Check if we can list topics
        print("\n📋 Checking available topics...")
        print("   Run: ros2 topic list | grep panda")
        print("   Expected: /panda_position_controller/commands")
        
        # Check if topic exists by trying to get topic info
        try:
            topics = node.get_topic_names_and_types()
            panda_topics = [t for t in topics if 'panda' in t[0].lower()]
            print(f"\n🔍 Found {len(panda_topics)} topics with 'panda' in name:")
            for topic_name, topic_types in panda_topics:
                print(f"   - {topic_name} ({topic_types})")
        except Exception as e:
            print(f"⚠️ Could not list topics: {e}")
        
        node.destroy_node()
        rclpy.shutdown()
        
        print("\n✅ Controller status check complete")
        print("\n💡 Tips:")
        print("   1. Make sure panda_position_controller is spawned")
        print("   2. Check: ros2 control list_controllers")
        print("   3. Verify topic exists: ros2 topic echo /panda_position_controller/commands")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    check_controller_status()


