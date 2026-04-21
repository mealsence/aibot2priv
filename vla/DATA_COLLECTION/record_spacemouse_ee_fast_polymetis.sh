#!/usr/bin/env bash
# Record SpaceMouse end-effector teleop data with the Polymetis Franka backend.
#
# Prerequisites:
#   1. On the robot PC / NUC, start the Polymetis hardware services:
#        launch_robot.py robot_client=franka_hardware
#        launch_gripper.py gripper=franka_hand
#   2. If using zerorpc mode (default), also start:
#        python -m REAL_ROBOT.polymetis.server --controller-host localhost
#   3. On the workstation, start the SpaceMouse driver:
#        ros2 run spacenav spacenav_node
#   4. Make sure an OpenCV camera source is available on the workstation
#      (default: camera index 0, configurable with LEROBOT_CAMERA_SOURCE).
#
# Notes:
#   - This script wraps REAL_ROBOT/polymetis/examples/collect_data.py.
#   - Camera input is OpenCV-based here, not ROS image topics.
#   - Resume mode is not supported by the current Polymetis recorder wrapper.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

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
        candidate_envs="${LEROBOT_CONDA_ENVS:-lerobot-ros lerobot-ros-isaac polymetis}"
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

source_ros_env() {
    if [ -n "${ROS_DISTRO:-}" ]; then
        echo "Using existing ROS environment: ${ROS_DISTRO}"
        return
    fi

    if [ -f /opt/ros/humble/setup.bash ]; then
        # shellcheck disable=SC1091
        source /opt/ros/humble/setup.bash
        echo "Sourced ROS environment: /opt/ros/humble"
    fi
}

validate_bool() {
    case "$1" in
        true|false) ;;
        *)
            echo "Invalid boolean value: $1 (expected true or false)" >&2
            exit 1
            ;;
    esac
}

append_flag_if_true() {
    local value="$1"
    local flag="$2"
    if [ "${value}" = "true" ]; then
        CMD+=("${flag}")
    fi
}

activate_python_env
source_ros_env

DATASET_BASE_ROOT="${LEROBOT_DATASET_ROOT:-${HOME}/lerobot_datasets/Real_Panda_Polymetis_SpaceMouse_EE_Fast}"
RESUME_INPUT="${LEROBOT_RESUME:-false}"
validate_bool "${RESUME_INPUT}"

if [ "${RESUME_INPUT}" = "true" ]; then
    echo "LEROBOT_RESUME=true is not supported by REAL_ROBOT/polymetis/examples/collect_data.py yet." >&2
    exit 1
fi

if [ -d "${DATASET_BASE_ROOT}" ]; then
    timestamp="$(date +%Y%m%d-%H%M%S)"
    DATASET_ROOT="${DATASET_BASE_ROOT}_${timestamp}"
    echo "Dataset root ${DATASET_BASE_ROOT} exists; using fresh directory ${DATASET_ROOT}."
else
    DATASET_ROOT="${DATASET_BASE_ROOT}"
fi

DATASET_REPO_ID="${LEROBOT_DATASET_REPO_ID:-ases200q2/Real_Panda_Polymetis_SpaceMouse_EE_Fast}"
SINGLE_TASK="${LEROBOT_SINGLE_TASK:-Pick cube from table}"
NUM_EPISODES="${LEROBOT_NUM_EPISODES:-10}"
EPISODE_TIME_S="${LEROBOT_EPISODE_TIME_S:-60}"
RESET_TIME_S="${LEROBOT_RESET_TIME_S:-30}"
DATASET_FPS="${LEROBOT_DATASET_FPS:-30}"
DISPLAY_DATA="${LEROBOT_DISPLAY_DATA:-false}"
PLAY_SOUNDS="${LEROBOT_PLAY_SOUNDS:-false}"
DATASET_PUSH="${LEROBOT_DATASET_PUSH:-false}"
validate_bool "${DISPLAY_DATA}"
validate_bool "${PLAY_SOUNDS}"
validate_bool "${DATASET_PUSH}"

POLYMETIS_DIRECT="${LEROBOT_POLYMETIS_DIRECT:-false}"
validate_bool "${POLYMETIS_DIRECT}"
POLYMETIS_SERVER_HOST="${LEROBOT_POLYMETIS_SERVER_HOST:-192.168.1.2}"
POLYMETIS_SERVER_PORT="${LEROBOT_POLYMETIS_SERVER_PORT:-4242}"
POLYMETIS_CONTROLLER_HOST="${LEROBOT_POLYMETIS_CONTROLLER_HOST:-localhost}"

JOY_TOPIC="${LEROBOT_JOY_TOPIC:-/spacenav/joy}"
TELEOP_LINEAR_STEP_M="${LEROBOT_TELEOP_LINEAR_STEP_M:-0.01}"
MAX_RELATIVE_TARGET="${LEROBOT_MAX_RELATIVE_TARGET:-0.05}"

CAMERA_SOURCE="${LEROBOT_CAMERA_SOURCE:-0}"
CAMERA_NAME="${LEROBOT_CAMERA_NAME:-cam_left_wrist}"
CAMERA_WIDTH="${LEROBOT_CAMERA_WIDTH:-640}"
CAMERA_HEIGHT="${LEROBOT_CAMERA_HEIGHT:-480}"
CAMERA_FPS="${LEROBOT_CAMERA_FPS:-30}"

CMD=(
    python
    "${PROJECT_ROOT}/REAL_ROBOT/polymetis/examples/collect_data.py"
    --repo-id "${DATASET_REPO_ID}"
    --root "${DATASET_ROOT}"
    --task "${SINGLE_TASK}"
    --episodes "${NUM_EPISODES}"
    --fps "${DATASET_FPS}"
    --episode-length "${EPISODE_TIME_S}"
    --reset-seconds "${RESET_TIME_S}"
    --teleop spacemouse_ee_panda
    --joy-topic "${JOY_TOPIC}"
    --linear-step-m "${TELEOP_LINEAR_STEP_M}"
    --camera "${CAMERA_SOURCE}"
    --camera-name "${CAMERA_NAME}"
    --width "${CAMERA_WIDTH}"
    --height "${CAMERA_HEIGHT}"
    --max-relative-target "${MAX_RELATIVE_TARGET}"
)

if [ "${POLYMETIS_DIRECT}" = "true" ]; then
    CMD+=(--direct --controller-host "${POLYMETIS_CONTROLLER_HOST}")
else
    CMD+=(--server-host "${POLYMETIS_SERVER_HOST}" --server-port "${POLYMETIS_SERVER_PORT}")
fi

append_flag_if_true "${DISPLAY_DATA}" --display-data
append_flag_if_true "${PLAY_SOUNDS}" --play-sounds
append_flag_if_true "${DATASET_PUSH}" --push-to-hub

echo "Recording with Polymetis SpaceMouse EE teleop"
echo "  Dataset root:   ${DATASET_ROOT}"
echo "  Dataset repo:   ${DATASET_REPO_ID}"
echo "  Episodes:       ${NUM_EPISODES}"
echo "  FPS:            ${DATASET_FPS}"
echo "  Camera source:  ${CAMERA_SOURCE}"
echo "  Joy topic:      ${JOY_TOPIC}"
if [ "${POLYMETIS_DIRECT}" = "true" ]; then
    echo "  Mode:           direct"
    echo "  Controller host:${POLYMETIS_CONTROLLER_HOST}"
else
    echo "  Mode:           zerorpc"
    echo "  Server:         ${POLYMETIS_SERVER_HOST}:${POLYMETIS_SERVER_PORT}"
fi

exec "${CMD[@]}" "$@"
