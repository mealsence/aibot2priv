#!/bin/sh

# Tmux script to start Perception Pipeline, MoveIt Servo and SpaceMouse
# Usage:
#   ./launch_servo_tmux.sh              # Launch Perception Pipeline + MoveIt Servo
#   ./launch_servo_tmux.sh --with-spacemouse  # Launch Perception Pipeline + MoveIt Servo + SpaceMouse

SESSION_NAME="moveit_servo_demo"

# Check if --with-spacemouse flag is provided
WITH_SPACEMOUSE=false
if [ "$1" = "--with-spacemouse" ]; then
    WITH_SPACEMOUSE=true
fi

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

tmux has-session -t $SESSION_NAME 2>/dev/null
if [ $? != 0 ]; then
    # create a new session
    tmux new-session -s $SESSION_NAME -n $SESSION_NAME -d
    
    # use mouse in Ubuntu/tmux
    tmux set -g mouse on

    # Highlight active window
    tmux set-window-option -g window-status-current-bg green

    # history limit
    tmux set -g history-limit 10000

    # Set status bar
    tmux set -g status-bg black
    tmux set -g status-fg white 
    tmux set -g mouse-utf8 off

    tmux set-window-option -g window-status-current-bg yellow

    tmux setw -g mode-keys vi
    tmux bind-key -t vi-copy 'v' begin-selection
    tmux bind-key -t vi-copy 'y' copy-pipe "xclip -sel clip -i"

    # Start perception pipeline in the main window (left pane, larger)
    tmux send-keys -t $SESSION_NAME "echo 'Starting Perception Pipeline...'; source install/setup.bash && ros2 launch perception_pipeline perception_pipeline_demo.launch.py" C-m
    
    # Split horizontally (left 60%, right 40%)
    tmux split-window -h -t $SESSION_NAME
    
    # In the top-right pane, start MoveIt Servo
    tmux send-keys -t $SESSION_NAME "sleep 5; echo 'Starting MoveIt Servo...'; source install/setup.bash && ros2 launch panda_moveit_config servo_launch.py ros2_control_hardware_type:=isaac" C-m
    
    # Split the right pane vertically
    tmux split-window -v -t $SESSION_NAME
    
    # In the middle-right pane, enable Servo after a delay
    tmux send-keys -t $SESSION_NAME "sleep 13; echo 'Enabling MoveIt Servo...'; source install/setup.bash && ros2 service call /servo_node/start_servo std_srvs/srv/Trigger && echo 'Servo enabled!'" C-m
    
    # Split the right pane vertically again (bottom pane)
    tmux split-window -v -t $SESSION_NAME
    
    if [ "$WITH_SPACEMOUSE" = true ]; then
        # In the bottom-right pane, start SpaceMouse node
        tmux send-keys -t $SESSION_NAME "sleep 3; echo 'Starting SpaceMouse node...'; ros2 run spacenav spacenav_node" C-m
    else
        # In the bottom-right pane, create monitoring
        tmux send-keys -t $SESSION_NAME "sleep 2; echo 'Monitoring ROS topics...'; watch -n 1 'ros2 topic list | head -20'" C-m
    fi
    
    # Set layout to main-horizontal (left pane gets more space)
    tmux select-layout main-horizontal
    
    # Select the perception pipeline pane (left) to make it active
    tmux select-pane -t $SESSION_NAME:0.0

    # Create a kill_tmux window
    tmux new-window -n kill_tmux -t $SESSION_NAME
    
    # Split kill window
    tmux split-window -v -t $SESSION_NAME:kill_tmux
    
    # Create kill commands
    tmux send-keys -t $SESSION_NAME:kill_tmux.0 'echo "Killing all processes..."; pkill -f "ros2.*perception_pipeline"; pkill -f "ros2.*servo_launch"; pkill -f "spacenav_node"; pkill -f "watch.*ros2 topic"; echo "Processes killed. Press Enter to kill tmux session..."; read' C-m
    tmux send-keys -t $SESSION_NAME:kill_tmux.1 'tmux kill-session -t '"$SESSION_NAME" C-m
    
    tmux select-layout -t $SESSION_NAME:kill_tmux tiled

    # Return to main window
    tmux select-window -t $SESSION_NAME:$SESSION_NAME

fi
tmux attach -t $SESSION_NAME

