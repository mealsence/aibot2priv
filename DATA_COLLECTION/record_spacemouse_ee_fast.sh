#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"

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

activate_python_env

DATASET_BASE_ROOT="${LEROBOT_DATASET_ROOT:-${HOME}/lerobot_datasets/Isaac_Panda_PickCube_SpaceMouse_EE_fast_100episodes}"
RESUME_INPUT="${LEROBOT_RESUME:-true}"

case "${RESUME_INPUT}" in
    true|false)
        ;;
    *)
        echo "Invalid LEROBOT_RESUME value: ${RESUME_INPUT}. Expected true or false." >&2
        exit 1
        ;;
esac

if [ "${RESUME_INPUT}" = "true" ]; then
    if [ ! -d "${DATASET_BASE_ROOT}" ]; then
        echo "Requested resume but dataset root ${DATASET_BASE_ROOT} does not exist." >&2
        exit 1
    fi
    DATASET_ROOT="${DATASET_BASE_ROOT}"
    DATASET_RESUME="true"
    echo "Resuming dataset in ${DATASET_ROOT}."
else
    if [ -d "${DATASET_BASE_ROOT}" ]; then
        timestamp="$(date +%Y%m%d-%H%M%S)"
        DATASET_ROOT="${DATASET_BASE_ROOT}_${timestamp}"
        echo "Dataset root ${DATASET_BASE_ROOT} exists; using fresh directory ${DATASET_ROOT}."
    else
        DATASET_ROOT="${DATASET_BASE_ROOT}"
    fi
    DATASET_RESUME="false"
fi

DATASET_REPO_ID="${LEROBOT_DATASET_REPO_ID:-ases200q2/Isaac_Panda_PickCube_SpaceMouse_EE_fast_100episodes}"
SINGLE_TASK="${LEROBOT_SINGLE_TASK:-Pick cube from table}"
ROBOT_ID="${LEROBOT_ROBOT_ID:-my_panda_follower}"
TELEOP_ID="${LEROBOT_TELEOP_ID:-my_spacemouse_leader}"
NUM_EPISODES="${LEROBOT_NUM_EPISODES:-10}"
EPISODE_TIME_S="${LEROBOT_EPISODE_TIME_S:-60}"
RESET_TIME_S="${LEROBOT_RESET_TIME_S:-60}"
DATASET_FPS="${LEROBOT_DATASET_FPS:-30}"
DISPLAY_DATA="${LEROBOT_DISPLAY_DATA:-false}"
DATASET_PUSH="${LEROBOT_DATASET_PUSH:-true}"
DATASET_PRIVATE="${LEROBOT_DATASET_PRIVATE:-false}"
DATASET_VIDEO="${LEROBOT_DATASET_VIDEO:-true}"
# Performance optimization: Image writer settings
# If robot slows down during episodes, try:
# - Increase threads if queue builds up: LEROBOT_NUM_IMAGE_WRITER_THREADS=6
# - Decrease threads if CPU overloaded: LEROBOT_NUM_IMAGE_WRITER_THREADS=2
# - Use processes if threads insufficient: LEROBOT_NUM_IMAGE_WRITER_PROCESSES=1
NUM_IMAGE_WRITER_PROCESSES="${LEROBOT_NUM_IMAGE_WRITER_PROCESSES:-1}"
NUM_IMAGE_WRITER_THREADS="${LEROBOT_NUM_IMAGE_WRITER_THREADS:-8}"
# Video encoding batch size: 1 = encode after each episode (default), >1 = batch encode
# For better performance, use batch encoding (e.g., 5-10) but requires more disk space
VIDEO_ENCODING_BATCH_SIZE="${LEROBOT_VIDEO_ENCODING_BATCH_SIZE:-1}"

# Robot type - use panda_ros_position for ultra-low latency direct position control
ROBOT_TYPE="${LEROBOT_ROBOT_TYPE:-panda_ros_position}"

# SpaceMouse sensitivity configuration
# Adjust these to control SpaceMouse responsiveness:
# - linear_step_m: Movement step size in meters (default: 0.01 = 1cm per tick)
#   Higher = faster/more sensitive movement (e.g., 0.02 = 2cm, 0.005 = 5mm)
# - dead_zone: Minimum input threshold to ignore small movements (default: 0.05 = 5%)
#   Lower = more sensitive to small movements (e.g., 0.02), Higher = more stable (e.g., 0.1)
# - gripper_step: Gripper movement step size (default: 0.0025 = 2.5mm per tick)
TELEOP_LINEAR_STEP_M="${LEROBOT_TELEOP_LINEAR_STEP_M:-0.01}"
TELEOP_DEAD_ZONE="${LEROBOT_TELEOP_DEAD_ZONE:-0.01}"
TELEOP_GRIPPER_STEP="${LEROBOT_TELEOP_GRIPPER_STEP:-0.001}"

# Camera configuration (only used if ROBOT_TYPE includes camera support like panda_ros_position)
# Default: 640×480 (VGA) - standard resolution used across LeRobot datasets
# These can be customized via environment variables:
# LEROBOT_CAMERA_TOPIC (default: /rgb/camera_1)
# LEROBOT_CAMERA_WIDTH (default: 640)
# LEROBOT_CAMERA_HEIGHT (default: 480)
# LEROBOT_CAMERA_FPS (default: 30)

exec lerobot-record \
  --robot.type="${ROBOT_TYPE}" \
  --robot.id="${ROBOT_ID}" \
  --teleop.type=spacemouse_ee_panda \
  --teleop.id="${TELEOP_ID}" \
  --teleop.linear_step_m="${TELEOP_LINEAR_STEP_M}" \
  --teleop.dead_zone="${TELEOP_DEAD_ZONE}" \
  --teleop.gripper_step="${TELEOP_GRIPPER_STEP}" \
  --dataset.root="${DATASET_ROOT}" \
  --dataset.repo_id="${DATASET_REPO_ID}" \
  --dataset.single_task="${SINGLE_TASK}" \
  --dataset.num_episodes="${NUM_EPISODES}" \
  --dataset.episode_time_s="${EPISODE_TIME_S}" \
  --dataset.reset_time_s="${RESET_TIME_S}" \
  --dataset.fps="${DATASET_FPS}" \
  --dataset.video="${DATASET_VIDEO}" \
  --dataset.push_to_hub="${DATASET_PUSH}" \
  --dataset.private="${DATASET_PRIVATE}" \
  --dataset.num_image_writer_processes="${NUM_IMAGE_WRITER_PROCESSES}" \
  --dataset.num_image_writer_threads_per_camera="${NUM_IMAGE_WRITER_THREADS}" \
  --dataset.video_encoding_batch_size="${VIDEO_ENCODING_BATCH_SIZE}" \
  --display_data="${DISPLAY_DATA}" \
  --resume="${DATASET_RESUME}" \
  "$@"
