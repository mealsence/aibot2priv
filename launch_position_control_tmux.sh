#!/bin/sh

SESSION_NAME="moveit"

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
WORKSPACE_DIR="$SCRIPT_DIR/isaac_franka_moveit_perception"

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

    # Start LeRobot recording with position control (fast, low-latency) launch file with Isaac Sim in pane 0
    tmux send-keys -t $SESSION_NAME "cd \"$WORKSPACE_DIR\" && echo 'Starting LeRobot recording and SpaceMouse...'; source install/setup.bash && (ros2 launch panda_moveit_config panda_lerobot_record.launch.py ros2_control_hardware_type:=isaac &) && sleep 3 && ros2 run spacenav spacenav_node" C-m

fi
tmux attach -t $SESSION_NAME
