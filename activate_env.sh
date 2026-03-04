#!/bin/bash
# =============================================================================
# LeRobot ROS Agent - Environment Activation Script
# =============================================================================
# Usage: source activate_env.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source ROS2 Humble
if [[ -f "/opt/ros/humble/setup.bash" ]]; then
    source /opt/ros/humble/setup.bash
    echo "✅ ROS2 Humble sourced"
fi

# Source local ROS2 workspace (if built)
if [[ -f "$SCRIPT_DIR/isaac_franka_moveit_perception/install/setup.bash" ]]; then
    source "$SCRIPT_DIR/isaac_franka_moveit_perception/install/setup.bash"
    echo "✅ Local ROS2 workspace sourced"
fi

# Activate Python virtual environment
if [[ -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
    echo "✅ Python virtual environment activated"
else
    echo "⚠️  Virtual environment not found. Run INSTALL/setup_with_uv.sh first."
fi

echo ""
echo "Environment ready! You can now run:"
echo "  python gradio_agent/demo_tool_calling.py --preload-policy"
