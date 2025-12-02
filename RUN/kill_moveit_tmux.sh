#!/bin/sh

# Kill processes launched by launch_moveit_tmux.sh and close the tmux session.
# Usage: ./kill_moveit_tmux.sh [session_name]

SESSION_NAME="${1:-moveit}"

# Stop ROS processes started by the launch script
pkill -f "ros2.*perception_pipeline" 2>/dev/null
pkill -f "ros2.*servo_launch" 2>/dev/null
pkill -f "spacenav_node" 2>/dev/null
pkill -f "watch.*ros2 topic" 2>/dev/null
pkill -f "[r]viz" 2>/dev/null

# Terminate the tmux session if it exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    tmux kill-session -t "$SESSION_NAME"
else
    echo "tmux session '$SESSION_NAME' not found; processes were still killed."
fi

