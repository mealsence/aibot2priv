#!/bin/bash

# script to switch between cartesian_twist_controller and move_to_home_lerobot 

# Set these to your remote controller computer's SSH info
REMOTE_USER="franka"
REMOTE_HOST="192.168.1.2"
REMOTE_SSH="$REMOTE_USER@$REMOTE_HOST"
ROBOT_IP="192.168.1.101"

# Path to ROS2 setup.bash on remote
ROS2_SETUP="/home/franka/franka_ros2_i2r/install/setup.bash"

# activate cartesian controller and deactivates move_to_home on remote
function activate_cartesian_controller() {
    echo "Activating cartesian_twist_controller on $REMOTE_SSH..."
    ssh $REMOTE_SSH "source $ROS2_SETUP && ros2 control switch_controllers --deactivate move_to_home_lerobot --activate cartesian_twist_controller"
    sleep 3
}

# activate move_to_home controller and deactivates cartesian controller on remote
function activate_move_to_home() {
    echo "Activating move_to_home_lerobot controller on $REMOTE_SSH..."
    ssh $REMOTE_SSH "source $ROS2_SETUP && ros2 control switch_controllers --deactivate cartesian_twist_controller --activate move_to_home_lerobot"
    sleep 3
}


# --- Main script logic based on argument ---
if [ $# -eq 0 ]; then
    echo "Usage: $0 {cartesian|home}"
    exit 1
fi

case $1 in
    cartesian)
        activate_cartesian_controller
        echo "Cartesian controller activated. Resume teleoperation."
        ;;
    home)
        activate_move_to_home
        echo "Move-to-home controller activated. Robot returning to home."
        ;;
    *)
        echo "Invalid argument: $1"
        echo "Usage: $0 {cartesian|home}"
        exit 1
        ;;
esac
