# --- Start/Stop BOTH Controllers ---
function start_both_controllers() {
    echo "Starting both controllers using gradio_setup_controllers.sh in a new tmux session..."
    tmux new-session -d -s gradio_controllers './gradio_setup_controllers.sh'
    echo "Controllers started in tmux session 'gradio_controllers'."
}

function stop_both_controllers() {
    echo "Stopping both controllers on $REMOTE_SSH..."
    ssh $REMOTE_SSH "pgrep -f 'cartesian_twist_controller' && pkill -SIGINT -f 'cartesian_twist_controller' || echo 'No cartesian_twist_controller running'"
    ssh $REMOTE_SSH "pgrep -f 'move_to_home_lerobot' && pkill -SIGINT -f 'move_to_home_lerobot' || echo 'No move_to_home_lerobot running'"
    ssh $REMOTE_SSH "pgrep -f 'ros2 run' && pkill -SIGINT -f 'ros2 run' || echo 'No ros2 run process running'"
    echo "Waiting for Franka hardware lock to clear..."
    sleep 3
}
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




# --- Switch Controllers (using switch_controllers.sh) ---
function switch_to_cartesian_controller() {
    echo "Switching to cartesian_twist_controller on $REMOTE_SSH..."
    ./switch_controllers.sh cartesian
}

function switch_to_move_to_home() {
    echo "Switching to move_to_home_lerobot controller on $REMOTE_SSH..."
    ./switch_controllers.sh home
}

function main_menu() {
    while true; do
        echo ""
        echo "==== Robot Control Menu ===="
        echo "1) Start both controllers (launch both)"
        echo "2) Stop both controllers (kill both)"
        echo "3) Switch to cartesian controller (For Teleoperation)"
        echo "4) Switch to move_to_home controller (move robot to start position)"
        echo "5) Exit"
        echo "==========================="
        read -p "Select option: " opt
        case $opt in
            1)
                start_both_controllers
                ;;
            2)
                stop_both_controllers
                ;;
            3)
                switch_to_cartesian_controller
                ;;
            4)
                switch_to_move_to_home
                ;;
            5)
                stop_both_controllers
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
