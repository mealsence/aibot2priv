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

DATASET_BASE_ROOT="${LEROBOT_DATASET_ROOT:-${HOME}/lerobot_datasets/spacemouse-ee-teleop}"
RESUME_INPUT="${LEROBOT_RESUME:-false}"

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

DATASET_REPO_ID="${LEROBOT_DATASET_REPO_ID:-ases200q2/Isaac_Panda_SpaceMouse_EE}"
SINGLE_TASK="${LEROBOT_SINGLE_TASK:-Pick cube from table}"
ROBOT_ID="${LEROBOT_ROBOT_ID:-my_panda_follower}"
TELEOP_ID="${LEROBOT_TELEOP_ID:-my_spacemouse_leader}"
NUM_EPISODES="${LEROBOT_NUM_EPISODES:-50}"
EPISODE_TIME_S="${LEROBOT_EPISODE_TIME_S:-60}"
RESET_TIME_S="${LEROBOT_RESET_TIME_S:-60}"
DATASET_FPS="${LEROBOT_DATASET_FPS:-30}"
DISPLAY_DATA="${LEROBOT_DISPLAY_DATA:-true}"
DATASET_PUSH="${LEROBOT_DATASET_PUSH:-true}"
DATASET_PRIVATE="${LEROBOT_DATASET_PRIVATE:-false}"
DATASET_VIDEO="${LEROBOT_DATASET_VIDEO:-true}"

# Robot type - use panda_ros for camera support with trajectory control
ROBOT_TYPE="${LEROBOT_ROBOT_TYPE:-panda_ros}"

# Camera configuration (only used if ROBOT_TYPE includes camera support like panda_ros)
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
  --display_data="${DISPLAY_DATA}" \
  --resume="${DATASET_RESUME}" \
  "$@"

