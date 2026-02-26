#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

activate_python_env() {
    if [ -n "${CONDA_PREFIX:-}" ]; then
        echo "Using existing conda environment: ${CONDA_DEFAULT_ENV:-${CONDA_PREFIX}}"
        return
    fi

    if [ -n "${VIRTUAL_ENV:-}" ]; then
        echo "Using existing virtual environment: ${VIRTUAL_ENV}"
        return
    fi

    if command -v conda >/dev/null 2>&1; then
        local conda_base
        conda_base="$(conda info --base)"
        # shellcheck disable=SC1090
        source "${conda_base}/etc/profile.d/conda.sh"
        local candidate_envs
        candidate_envs="${LEROBOT_CONDA_ENVS:-lerobot-ros-isaac lerobot-ros}"
        for env_name in ${candidate_envs}; do
            if conda env list | awk '{print $1}' | grep -x "${env_name}" >/dev/null 2>&1; then
                conda activate "${env_name}"
                echo "Activated conda environment: ${env_name}"
                return
            fi
        done
    fi

    if [ -f "${PROJECT_ROOT}/.venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "${PROJECT_ROOT}/.venv/bin/activate"
        echo "Activated virtual environment at ${PROJECT_ROOT}/.venv"
        return
    fi

    echo "Warning: No matching conda env or .venv found. Continuing with system Python." >&2
}

print_usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Launch RealSense to ROS2 camera publisher for data collection.

Options:
    --config FILE       Path to YAML camera configuration file
    --cameras JSON      JSON string with camera configuration
    --no-auto-detect    Disable auto-detection of cameras
    --width WIDTH       Default camera width (default: 640)
    --height HEIGHT     Default camera height (default: 480)
    --fps FPS           Default camera FPS (default: 30)
    -h, --help          Show this help message

Environment Variables:
    LEROBOT_REALSENSE_CONFIG_FILE      Path to YAML config file
    LEROBOT_REALSENSE_CAMERAS          JSON camera configuration
    LEROBOT_REALSENSE_AUTO_DETECT      Auto-detect cameras (default: true)
    LEROBOT_REALSENSE_DEFAULT_WIDTH    Default width (default: 640)
    LEROBOT_REALSENSE_DEFAULT_HEIGHT   Default height (default: 480)
    LEROBOT_REALSENSE_DEFAULT_FPS      Default FPS (default: 30)

Examples:
    # Auto-detect all cameras
    $(basename "$0")

    # Use custom configuration file
    $(basename "$0") --config REAL_ROBOT/camera_config.yaml

    # Manual camera specification
    $(basename "$0") --cameras '{"camera_1": {"serial": "12345678"}}'

    # Use custom resolution
    $(basename "$0") --width 1280 --height 720

EOF
}

# Parse arguments
CONFIG_FILE=""
CAMERAS_JSON=""
NO_AUTO_DETECT=""
WIDTH=""
HEIGHT=""
FPS=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --cameras)
            CAMERAS_JSON="$2"
            shift 2
            ;;
        --no-auto-detect)
            NO_AUTO_DETECT="--no-auto-detect"
            shift
            ;;
        --width)
            WIDTH="$2"
            shift 2
            ;;
        --height)
            HEIGHT="$2"
            shift 2
            ;;
        --fps)
            FPS="$2"
            shift 2
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            echo "Error: Unknown option: $1" >&2
            print_usage
            exit 1
            ;;
    esac
done

# Activate Python environment
activate_python_env

# Check if pyrealsense2 is installed
echo "Checking dependencies..."
if ! python -c "import pyrealsense2" 2>/dev/null; then
    echo "Error: pyrealsense2 not installed!" >&2
    echo "Install with: pip install pyrealsense2" >&2
    exit 1
fi

if ! python -c "import rclpy" 2>/dev/null; then
    echo "Error: rclpy (ROS2) not installed!" >&2
    echo "Install ROS2 Humble: https://docs.ros.org/en/humble/Installation.html" >&2
    exit 1
fi

echo "✅ Dependencies OK"

# Check for RealSense cameras if auto-detect is enabled
if [[ -z "$NO_AUTO_DETECT" ]]; then
    echo ""
    echo "Detecting RealSense cameras..."
    if command -v lerobot-find-cameras >/dev/null 2>&1; then
        lerobot-find-cameras realsense || echo "No RealSense cameras detected or lerobot-find-cameras not available"
    else
        echo "Note: lerobot-find-cameras not found. Will rely on pyrealsense2 detection."
    fi
fi

# Build command
CMD_ARGS=()

if [[ -n "$CONFIG_FILE" ]]; then
    CMD_ARGS+=(--config "$CONFIG_FILE")
fi

if [[ -n "$CAMERAS_JSON" ]]; then
    CMD_ARGS+=(--cameras "$CAMERAS_JSON")
fi

if [[ -n "$NO_AUTO_DETECT" ]]; then
    CMD_ARGS+=("$NO_AUTO_DETECT")
fi

if [[ -n "$WIDTH" ]]; then
    CMD_ARGS+=(--width "$WIDTH")
fi

if [[ -n "$HEIGHT" ]]; then
    CMD_ARGS+=(--height "$HEIGHT")
fi

if [[ -n "$FPS" ]]; then
    CMD_ARGS+=(--fps "$FPS")
fi

# Launch publisher
echo ""
echo "Launching RealSense to ROS2 publisher..."
echo "Press Ctrl+C to stop"
echo ""

exec python "${SCRIPT_DIR}/realsense_ros2_publisher.py" "${CMD_ARGS[@]}"
