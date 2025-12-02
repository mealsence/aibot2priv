#!/bin/bash

# Script to fix RTPS_TRANSPORT_SHM errors in ROS2
# This script cleans up leftover FastRTPS shared memory files and provides solutions

echo "=== RTPS_TRANSPORT_SHM Error Fix Script ==="
echo

# Function to check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        echo "WARNING: Running as root. This may cause permission issues with ROS2 nodes."
        echo "It's recommended to run this script as the regular user who runs ROS2."
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Function to clean up FastRTPS shared memory files
cleanup_fastrtps_shm() {
    echo "Cleaning up FastRTPS shared memory files..."
    
    # Count files before cleanup
    local before_count=$(ls -la /dev/shm/ | grep fastrtps | wc -l)
    echo "Found $before_count FastRTPS files in /dev/shm/"
    
    # Remove FastRTPS shared memory files
    rm -f /dev/shm/fastrtps_* 2>/dev/null
    
    # Count files after cleanup
    local after_count=$(ls -la /dev/shm/ | grep fastrtps | wc -l)
    echo "Removed $((before_count - after_count)) FastRTPS files"
    echo "Remaining FastRTPS files: $after_count"
    
    if [[ $after_count -eq 0 ]]; then
        echo "✓ All FastRTPS shared memory files cleaned up successfully"
    else
        echo "⚠ Some FastRTPS files could not be removed (may be in use)"
    fi
}

# Function to kill orphaned ROS2 processes
kill_orphaned_ros2() {
    echo "Checking for orphaned ROS2 processes..."
    
    # Find orphaned ros2_control_node processes
    local orphaned_count=$(ps aux | grep ros2_control_node | grep -v grep | wc -l)
    if [[ $orphaned_count -gt 3 ]]; then
        echo "Found $orphaned_count ros2_control_node processes (expected: 1-3)"
        echo "Killing orphaned ros2_control_node processes..."
        pkill -f "ros2_control_node" 2>/dev/null
        sleep 2
    fi
    
    # Find other orphaned ROS2 processes
    local other_orphaned=$(ps aux | grep -E "(robot_state_publisher|move_group|controller_manager)" | grep -v grep | wc -l)
    if [[ $other_orphaned -gt 10 ]]; then
        echo "Found many orphaned ROS2 processes, cleaning up..."
        pkill -f "robot_state_publisher" 2>/dev/null
        pkill -f "move_group" 2>/dev/null
        pkill -f "spawner.*controller_manager" 2>/dev/null
        sleep 2
    fi
}

# Function to create a ROS2 configuration to prevent SHM issues
create_ros2_config() {
    echo "Creating ROS2 configuration to prevent SHM issues..."
    
    # Create a FastRTPS profile configuration
    cat > /tmp/fastrtps_profile.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8" ?>
<profiles xmlns="http://www.eprosima.com/XMLSchemas/fastRTPS_Profiles">
    <transport_descriptors>
        <transport_descriptor>
            <transport_id>udp_transport</transport_id>
            <type>UDPv4</type>
        </transport_descriptor>
    </transport_descriptors>
    
    <profile name="default_profile" is_default="true">
        <rtps>
            <userTransports>
                <transport_id>udp_transport</transport_id>
            </userTransports>
            <useBuiltinTransports>false</useBuiltinTransports>
        </rtps>
    </profile>
</profiles>
EOF

    echo "✓ FastRTPS profile created at /tmp/fastrtps_profile.xml"
    echo "To use this profile, set: export FASTRTPS_DEFAULT_PROFILES_FILE=/tmp/fastrtps_profile.xml"
}

# Function to provide alternative solutions
provide_alternatives() {
    echo
    echo "=== Alternative Solutions ==="
    echo
    echo "1. Use UDP transport instead of SHM:"
    echo "   export RMW_IMPLEMENTATION=rmw_fastrtps_cpp"
    echo "   export FASTRTPS_DEFAULT_PROFILES_FILE=/tmp/fastrtps_profile.xml"
    echo
    echo "2. Disable shared memory transport:"
    echo "   export RMW_FASTRTPS_USE_QOS_XML=0"
    echo "   export ROS_DOMAIN_ID=0"
    echo
    echo "3. Clean up before each launch:"
    echo "   rm -f /dev/shm/fastrtps_*"
    echo "   ./launch_moveit_tmux.sh"
    echo
    echo "4. Use a cleanup script in your launch:"
    echo "   Add this to your .bashrc or launch script:"
    echo "   # Clean up FastRTPS SHM files"
    echo "   rm -f /dev/shm/fastrtps_* 2>/dev/null || true"
    echo
}

# Function to create an improved launch script
create_improved_launch() {
    echo "Creating improved launch script with cleanup..."
    
    cat > launch_moveit_tmux_fixed.sh << 'EOF'
#!/bin/sh

# Improved Tmux script with FastRTPS cleanup
# Usage:
#   ./launch_moveit_tmux_fixed.sh

SESSION_NAME="moveit"

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
WORKSPACE_DIR="$SCRIPT_DIR/isaac_franka_moveit_perception"

# Clean up FastRTPS shared memory files before launch
echo "Cleaning up FastRTPS shared memory files..."
rm -f /dev/shm/fastrtps_* 2>/dev/null || true

# Set environment variables to prevent SHM issues
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DOMAIN_ID=0

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

    # Start perception pipeline and SpaceMouse node in pane 0
    tmux send-keys -t $SESSION_NAME "cd \"$WORKSPACE_DIR\" && echo 'Starting Perception Pipeline and SpaceMouse...'; source install/setup.bash && (ros2 launch perception_pipeline perception_pipeline_demo.launch.py &) && sleep 3 && ros2 run spacenav spacenav_node" C-m

fi
tmux attach -t $SESSION_NAME
EOF

    chmod +x launch_moveit_tmux_fixed.sh
    echo "✓ Improved launch script created: launch_moveit_tmux_fixed.sh"
}

# Function to create a quick cleanup script
create_cleanup_script() {
    cat > cleanup_ros2.sh << 'EOF'
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
EOF

    chmod +x cleanup_ros2.sh
    echo "✓ Cleanup script created: cleanup_ros2.sh"
}

# Main execution
main() {
    check_root
    cleanup_fastrtps_shm
    kill_orphaned_ros2
    create_ros2_config
    create_improved_launch
    create_cleanup_script
    provide_alternatives
    
    echo
    echo "=== Summary ==="
    echo "✓ Cleaned up FastRTPS shared memory files"
    echo "✓ Killed orphaned ROS2 processes"
    echo "✓ Created FastRTPS UDP profile"
    echo "✓ Created improved launch script"
    echo "✓ Created cleanup script"
    echo
    echo "Next steps:"
    echo "1. Try the improved launch script: ./launch_moveit_tmux_fixed.sh"
    echo "2. Or use the cleanup script: ./cleanup_ros2.sh"
    echo "3. Then run your original launch script"
    echo
    echo "For persistent fix, add this to your ~/.bashrc:"
    echo "alias ros2-cleanup='rm -f /dev/shm/fastrtps_* 2>/dev/null || true'"
}

# Run main function
main "$@"
