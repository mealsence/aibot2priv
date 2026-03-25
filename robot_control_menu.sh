#!/bin/bash
# TODO: UPDATE THIS SCRIPT TO USE CONTROLLER_SWTCHING INSTEAD OF STOPPING AND STARTING CONTROLLER

# Set these to your remote controller computer's SSH info
REMOTE_USER="franka"
REMOTE_HOST="192.168.1.2"
REMOTE_SSH="$REMOTE_USER@$REMOTE_HOST"
ROBOT_IP="192.168.1.101"
#TELEOP_CMD="lerobot-teleoperate --robot.discover_packages_path=lerobot_robot_ros --teleop.discover_packages_path=lerobot_teleoperator_devices --robot.type=panda_ros_cartesian --robot.id=my_panda_follower --teleop.type=spacemouse_cartesian_vel_panda --teleop.id=my_spacemouse_leader --display_data=false"

cartesian_controller_pid=""
teleop_pid=""
move_to_start_pid=""
cartesian_controller_ssh_pid=""
move_to_start_ssh_pid=""



# Path to ROS2 setup.bash on remote
ROS2_SETUP="/home/franka/franka_ros2_i2r/install/setup.bash"

# Start cartesian controller on remote
function start_cartesian_controller() {
    echo "Starting cartesian_twist_controller on $REMOTE_SSH..."
    ssh $REMOTE_SSH "source $ROS2_SETUP && ros2 launch franka_bringup cartesian_twist_controller.launch.py robot_ip:=$ROBOT_IP" &
    cartesian_controller_ssh_pid=$!
    sleep 5
}

# Stop cartesian controller on remote
function stop_cartesian_controller() {
    if [ -n "$cartesian_controller_ssh_pid" ]; then
        echo "Stopping cartesian_twist_controller..."
        
        # 1. Ask remote ROS2 nodes to shut down gracefully first (SIGINT)
        ssh $REMOTE_SSH "pkill -SIGINT -f 'cartesian_twist_controller' || true"
        ssh $REMOTE_SSH "pkill -SIGINT -f 'ros2 run' || true"
        
        # 2. Kill the local SSH process
        kill $cartesian_controller_ssh_pid 2>/dev/null
        cartesian_controller_ssh_pid=""
        
        # 3. Give the hardware time to release the lock
        echo "Waiting for Franka hardware lock to clear..."
        sleep 3 
    else
        echo "Cartesian controller is not marked as running locally."
    fi
}


# Start move_to_home controller on remote
function start_move_to_home() {
    echo "Starting move_to_home_lerobot controller on $REMOTE_SSH..."
    ssh $REMOTE_SSH "source $ROS2_SETUP && ros2 launch franka_bringup move_to_home_lerobot.launch.py robot_ip:=$ROBOT_IP" &
    move_to_home_ssh_pid=$!
    sleep 5
}

# Stop move_to_home controller on remote
function stop_move_to_home() {
    if [ -n "$move_to_home_ssh_pid" ]; then
        echo "Stopping move_to_home_lerobot controller..."
        
        # 1. Send interrupt to remote launch file and nodes
        ssh $REMOTE_SSH "pkill -SIGINT -f 'move_to_home' || true"
        ssh $REMOTE_SSH "pkill -SIGINT -f 'ros2 run' || true"
        
        # 2. Kill local SSH process
        kill $move_to_home_ssh_pid 2>/dev/null
        move_to_home_ssh_pid=""
        
        echo "Waiting for Franka hardware lock to clear..."
        sleep 3
    else
        echo "Move to home controller is not marked as running locally."
    fi
}

function main_menu() {
    while true; do
        echo ""
        echo "==== Robot Control Menu ===="
        echo "1) Start cartesian controller"
        echo "2) Stop cartesian controller"
        echo "3) Return robot to home/start position (one step)"
        echo "4) Stop move_to_home controller"
        echo "5) Exit"
        echo "==========================="
        read -p "Select option: " opt
        case $opt in
            1)
                start_cartesian_controller
                ;;
            2)
                stop_cartesian_controller
                ;;
            3)
                # Single return to home option
                stop_cartesian_controller
                start_move_to_home
                #echo "Waiting 4 seconds for home position..."
                #sleep 4
                stop_move_to_home
                start_cartesian_controller
                echo "Robot returned to home, cartesian controller resumed. Resume teleoperation."
            ;;
            4)
                stop_move_to_home
            ;;
            5)
                stop_cartesian_controller
                stop_move_to_home
                echo "Exiting."
                exit 0
            ;;
            *)
                echo "Invalid option."
                ;;
        esac
    done
}

main_menu
