#!/usr/bin/env python3
"""
Test script for ROS2Camera implementation.
Tests subscribing to Isaac Sim camera topics and reading frames.
"""

import time
import threading
import rclpy
from rclpy.executors import SingleThreadedExecutor
from lerobot_robot_ros.ros2_camera import ROS2Camera, ROS2CameraConfig
from lerobot.cameras.configs import ColorMode

def test_ros2_camera():
    """Test ROS2Camera with Isaac Sim."""

    print("=" * 60)
    print("Testing ROS2Camera with Isaac Sim")
    print("=" * 60)

    # Create camera configuration (640×480 - standard LeRobot resolution)
    config = ROS2CameraConfig(
        topic="/rgb/camera_1",
        width=640,
        height=480,
        fps=30,
        color_mode=ColorMode.RGB
    )

    print(f"\nCamera configuration:")
    print(f"  Topic: {config.topic}")
    print(f"  Resolution: {config.width}x{config.height}")
    print(f"  FPS: {config.fps}")
    print(f"  Color mode: {config.color_mode}")

    # Create camera instance
    camera = ROS2Camera(config)
    print(f"\nCreated camera: {camera}")

    # Connect to camera
    print("\nConnecting to camera...")
    try:
        camera.connect(warmup=False)  # Don't wait for warmup yet
        print("✓ Camera connected successfully!")
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        return

    # Create executor and spin camera node in background thread
    print("\nStarting executor thread...")
    executor = SingleThreadedExecutor()
    executor.add_node(camera.node)
    executor_thread = threading.Thread(target=executor.spin, daemon=True)
    executor_thread.start()
    print("✓ Executor started")

    # Wait for first frame
    print("\nWaiting for first frame...")
    time.sleep(1.0)  # Give time for callbacks to process

    # Test synchronous read
    print("\nTesting synchronous read...")
    try:
        frame = camera.read()
        print(f"✓ Read frame: shape={frame.shape}, dtype={frame.dtype}")
        print(f"  Frame stats: min={frame.min()}, max={frame.max()}, mean={frame.mean():.1f}")
    except Exception as e:
        print(f"✗ Failed to read: {e}")

    # Test asynchronous read multiple times
    print("\nTesting asynchronous read (10 frames)...")
    try:
        for i in range(10):
            start = time.perf_counter()
            frame = camera.async_read(timeout_ms=300)
            dt_ms = (time.perf_counter() - start) * 1000
            print(f"  Frame {i+1}: shape={frame.shape}, read time={dt_ms:.1f}ms")
    except Exception as e:
        print(f"✗ Failed to read: {e}")

    # Disconnect camera
    print("\nDisconnecting camera...")
    try:
        # Clean up executor first
        executor.remove_node(camera.node)
        executor.shutdown()

        # Then disconnect camera
        camera.disconnect()
        print("✓ Camera disconnected successfully!")
    except Exception as e:
        print(f"✗ Failed to disconnect: {e}")

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)

if __name__ == "__main__":
    test_ros2_camera()
