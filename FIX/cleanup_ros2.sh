#!/bin/bash

# Quick ROS2 cleanup script
echo "Cleaning up ROS2 processes and FastRTPS files..."

# Kill ROS2 processes
pkill -f "ros2" 2>/dev/null || true
pkill -f "isaacsim" 2>/dev/null || true
sleep 2

# Clean up shared memory
rm -f /dev/shm/fastrtps_* 2>/dev/null || true

echo "Cleanup complete!"
