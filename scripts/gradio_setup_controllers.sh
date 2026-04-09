#!/bin/bash

# This script is used to ensure that cartesian_twist_controller and move_to_home_lerobot controllers 
# are started when starting gradio.

# Set these to your remote controller computer's SSH info
REMOTE_USER="franka"
REMOTE_HOST="192.168.1.2"
REMOTE_SSH="$REMOTE_USER@$REMOTE_HOST"
ROBOT_IP="192.168.1.101"

# Path to ROS2 setup.bash on remote
ROS2_SETUP="/home/franka/franka_ros2_i2r/install/setup.bash"

# Stop cartesian controller on remote
function stop_controllers() {
    echo "Stopping move_to_home_lerobot and cartesian_twist_controller on $REMOTE_SSH..."
    ssh $REMOTE_SSH "pgrep -f 'move_to_home_lerobot' && pkill -SIGINT -f 'move_to_home_lerobot' || echo 'No move_to_home_lerobot running'"
    ssh $REMOTE_SSH "pgrep -f 'cartesian_twist_controller' && pkill -SIGINT -f 'cartesian_twist_controller' || echo 'No cartesian_twist_controller running'"
    ssh $REMOTE_SSH "pgrep -f 'ros2 run' && pkill -SIGINT -f 'ros2 run' || echo 'No ros2 run process running'"
    echo "Waiting for Franka hardware lock to clear..."
    sleep 3
}

# Start move_to_home controller on remote
function start_controllers() {
    echo "Starting move_to_home_lerobot controller on $REMOTE_SSH..."
    ssh $REMOTE_SSH "source $ROS2_SETUP && ros2 launch franka_bringup move_to_home_lerobot.launch.py robot_ip:=$ROBOT_IP"
    sleep 5
}

# Execute option 3: Return robot to home/start position (one step)
stop_controllers
start_controllers
echo "controllers started"
