#!/usr/bin/env bash
# Data collection for real Franka Panda using Cartesian velocity control.
#
# Prerequisites (run in separate terminals before this script):
#   1. ros2 run spacenav spacenav_node              # SpaceMouse driver
#   2. ros2 launch franka_ros2 <your_launch>.launch.py  # Franka bringup with cartesian_twist_controller
#   3. ./REAL_ROBOT/launch_realsense_camera.sh       # RealSense camera (publishes to /rgb/camera_1)
#
# The robot is controlled via /cartesian_twist_controller/cmd_vel (same as spacemouse_cartesian_vel.py).
# Dataset stores: obs={joint positions, camera}, action={vx, vy, vz, gripper.pos}
#
# Key environment variables:
#   LEROBOT_DATASET_ROOT      - where to save the dataset (default: ~/lerobot_datasets/...)
#   LEROBOT_DATASET_REPO_ID   - HuggingFace repo id (default: ases200q2/...)
#   LEROBOT_SINGLE_TASK       - task description string
#   LEROBOT_NUM_EPISODES      - number of episodes to record (default: 50)
#   LEROBOT_EPISODE_TIME_S    - seconds per episode (default: 60)
#   LEROBOT_RESET_TIME_S      - reset time between episodes (default: 60)
#   LEROBOT_DATASET_FPS       - recording framerate (default: 30)
#   LEROBOT_RESUME            - true to resume existing dataset (default: false)
#   LEROBOT_DATASET_PUSH      - true to push to HuggingFace hub (default: false)
#   LEROBOT_CAMERA_TOPIC      - ROS topic for camera (default: /rgb/camera_1)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."

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

#/home/student/lerobot_datasets/Real_Panda_CartesianVel_Screwdriver_3_20260305-151000/
DATASET_BASE_ROOT="${LEROBOT_DATASET_ROOT:-${HOME}/lerobot_datasets/test_new/}"
RESUME_INPUT="${LEROBOT_RESUME:-false}"

case "${RESUME_INPUT}" in
    true|false) ;;
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

DATASET_REPO_ID="${LEROBOT_DATASET_REPO_ID:-TInkybala/PickCubeVLA0}"
SINGLE_TASK="${LEROBOT_SINGLE_TASK:-Pick up cube}"
ROBOT_ID="${LEROBOT_ROBOT_ID:-my_panda_real}"
TELEOP_ID="${LEROBOT_TELEOP_ID:-my_spacemouse_leader}"
NUM_EPISODES="${LEROBOT_NUM_EPISODES:-25}"
EPISODE_TIME_S="${LEROBOT_EPISODE_TIME_S:-60}"
RESET_TIME_S="${LEROBOT_RESET_TIME_S:-60}"
DATASET_FPS="${LEROBOT_DATASET_FPS:-30}"
DISPLAY_DATA="${LEROBOT_DISPLAY_DATA:-false}"
DATASET_PUSH="${LEROBOT_DATASET_PUSH:-false}"
DATASET_PRIVATE="${LEROBOT_DATASET_PRIVATE:-false}"
DATASET_VIDEO="${LEROBOT_DATASET_VIDEO:-true}"
NUM_IMAGE_WRITER_PROCESSES="${LEROBOT_NUM_IMAGE_WRITER_PROCESSES:-1}"
NUM_IMAGE_WRITER_THREADS="${LEROBOT_NUM_IMAGE_WRITER_THREADS:-4}"
VIDEO_ENCODING_BATCH_SIZE="${LEROBOT_VIDEO_ENCODING_BATCH_SIZE:-1}"

# SpaceMouse sensitivity (matching spacemouse_cartesian_vel.py defaults)
TELEOP_LINEAR_SCALE="${LEROBOT_TELEOP_LINEAR_SCALE:-0.05}"
TELEOP_DEAD_ZONE="${LEROBOT_TELEOP_DEAD_ZONE:-0.1}"

exec lerobot-record \
  --robot.discover_packages_path=lerobot_robot_ros \
  --teleop.discover_packages_path=lerobot_teleoperator_devices \
  --robot.type=panda_ros_cartesian \
  --robot.id="${ROBOT_ID}" \
  --teleop.type=spacemouse_cartesian_vel_panda \
  --teleop.id="${TELEOP_ID}" \
  --teleop.linear_scale="${TELEOP_LINEAR_SCALE}" \
  --teleop.dead_zone="${TELEOP_DEAD_ZONE}" \
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
