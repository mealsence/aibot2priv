#!/bin/sh

# Kill all ROS2 nodes and processes
# Usage: ./kill_all_ros2.sh

echo "Killing all ROS2 processes..."

# Kill ROS2 daemon first
pkill -f "ros2 daemon" 2>/dev/null

# Kill all ros2 launch processes
pkill -f "ros2 launch" 2>/dev/null

# Kill all ros2 run processes
pkill -f "ros2 run" 2>/dev/null

# Kill common ROS2 nodes
pkill -f "perception_pipeline" 2>/dev/null
pkill -f "spacenav_node" 2>/dev/null
pkill -f "moveit" 2>/dev/null
pkill -f "panda" 2>/dev/null
pkill -f "servo" 2>/dev/null
pkill -f "rviz" 2>/dev/null

# Kill any remaining ROS2 processes
pkill -f "[r]os2" 2>/dev/null

# Kill robot_state_publisher and joint_state_publisher
pkill -f "robot_state_publisher" 2>/dev/null
pkill -f "joint_state_publisher" 2>/dev/null

# Kill gazebo/isaac sim related processes if any
pkill -f "isaac" 2>/dev/null
pkill -f "gazebo" 2>/dev/null

# Give processes a moment to terminate gracefully
sleep 1

# Force kill any remaining ROS2 processes if needed
pkill -9 -f "[r]os2" 2>/dev/null

echo "All ROS2 processes killed."



