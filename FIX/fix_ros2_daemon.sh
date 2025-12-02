#!/bin/bash
# Fix ROS2 daemon issues

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   ROS2 Daemon Fix                                              ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Check if --kill-nodes flag is provided
KILL_NODES=false
if [[ "$1" == "--kill-nodes" ]] || [[ "$1" == "-k" ]]; then
    KILL_NODES=true
fi

# Source ROS2
source /opt/ros/humble/setup.bash

# Stop daemon first if killing nodes (prevents daemon from keeping node references)
if [ "$KILL_NODES" = true ]; then
    echo "0. Stopping ROS2 daemon first..."
    ros2 daemon stop 2>/dev/null || echo "   (No daemon running)"
    sleep 1
    echo ""
fi

# Optionally kill running ROS2 nodes
if [ "$KILL_NODES" = true ]; then
    echo "1. Killing running ROS2 nodes..."
    
    # Kill tmux sessions that might be running ROS2 nodes
    if tmux has-session -t "moveit" 2>/dev/null; then
        tmux kill-session -t "moveit" 2>/dev/null && echo "   ✓ Killed tmux session 'moveit'"
    fi
    if tmux has-session -t "moveit_servo_demo" 2>/dev/null; then
        tmux kill-session -t "moveit_servo_demo" 2>/dev/null && echo "   ✓ Killed tmux session 'moveit_servo_demo'"
    fi
    
    # Kill launch processes
    pkill -f "ros2.*launch.*perception_pipeline" 2>/dev/null && echo "   ✓ Killed perception_pipeline launch"
    pkill -f "ros2.*launch.*servo_launch" 2>/dev/null && echo "   ✓ Killed servo_launch"
    pkill -f "ros2.*launch" 2>/dev/null && echo "   ✓ Killed other ros2 launch processes"
    
    # Kill specific ROS2 nodes (these are the actual executables spawned by launch files)
    pkill -f "move_group" 2>/dev/null && echo "   ✓ Killed move_group"
    pkill -f "robot_state_publisher" 2>/dev/null && echo "   ✓ Killed robot_state_publisher"
    pkill -f "joint_state_publisher" 2>/dev/null && echo "   ✓ Killed joint_state_publisher"
    pkill -f "controller_manager" 2>/dev/null && echo "   ✓ Killed controller_manager"
    pkill -f "servo_node" 2>/dev/null && echo "   ✓ Killed servo_node"
    pkill -f "spacenav_node" 2>/dev/null && echo "   ✓ Killed spacenav_node"
    pkill -f "[r]viz" 2>/dev/null && echo "   ✓ Killed rviz"
    pkill -f "ros2_control_node" 2>/dev/null && echo "   ✓ Killed ros2_control_node"
    
    # Kill any remaining ros2 processes
    pkill -f "^ros2 " 2>/dev/null && echo "   ✓ Killed remaining ros2 processes"
    
    # Give processes time to terminate
    sleep 3
    
    # Force kill any remaining ROS2-related processes
    pkill -9 -f "move_group" 2>/dev/null
    pkill -9 -f "robot_state_publisher" 2>/dev/null
    pkill -9 -f "ros2_control" 2>/dev/null
    
    # Wait a bit more for cleanup
    sleep 1
    
    # Check if any ROS2 processes are still running
    REMAINING=$(ps aux | grep -E "(move_group|robot_state_publisher|ros2_control|servo_node|perception_pipeline)" | grep -v grep | wc -l)
    if [ "$REMAINING" -gt 0 ]; then
        echo "   ⚠️  Warning: $REMAINING ROS2-related process(es) may still be running"
        echo "   Run 'ps aux | grep ros2' to check manually"
    else
        echo "   ✓ All ROS2 nodes killed"
    fi
    echo ""
fi

# Stop any existing daemon (if not already stopped above)
if [ "$KILL_NODES" = false ]; then
    echo "1. Stopping ROS2 daemon..."
    ros2 daemon stop 2>/dev/null || echo "   (No daemon running)"
    sleep 1
    echo ""
fi

# Start daemon
echo "2. Starting ROS2 daemon..."
ros2 daemon start

# Wait for daemon to initialize
sleep 2

# Test
echo "3. Testing ROS2..."
if ros2 topic list > /dev/null 2>&1; then
    echo "   ✅ ROS2 is working!"
    echo ""
    TOPIC_COUNT=$(ros2 topic list 2>/dev/null | wc -l)
    if [ "$TOPIC_COUNT" -gt 0 ]; then
        echo "📋 Available topics ($TOPIC_COUNT total):"
        ros2 topic list | head -10
        if [ "$TOPIC_COUNT" -gt 10 ]; then
            echo "   ... and $((TOPIC_COUNT - 10)) more"
        fi
        echo ""
        echo "ℹ️  Note: If you see MoveIt topics, MoveIt nodes are still running."
        echo "   To kill all ROS2 nodes first, run: $0 --kill-nodes"
    else
        echo "   (No topics available - no nodes running)"
    fi
else
    echo "   ❌ Still having issues"
    echo ""
    echo "💡 Try these steps:"
    echo "   1. Close all terminals"
    echo "   2. In a fresh terminal, run: source /opt/ros/humble/setup.bash"
    echo "   3. Run: ros2 daemon start"
    echo "   4. Try: ros2 topic list again"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║   Fix Complete                                                 ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

