#!/usr/bin/env bash
# Evaluation script for Real Panda Cartesian Velocity policies.
# Trained on ases200q2/Real_Panda_CartesianVel_SpaceMouse with ACT.
#
# Prerequisites (run in separate terminals before this script):
#   1. ros2 run spacenav spacenav_node                    # SpaceMouse driver
#   2. ros2 launch franka_bringup cartesian_twist_controller.launch.py robot_ip:=<IP>
#   3. ./REAL_ROBOT/launch_realsense_camera.sh           # RealSense (publishes to /rgb/camera_1)
#
# Usage:
#   ./eval_real_panda_cartesian_vel.sh [policy_path]
#   ./eval_real_panda_cartesian_vel.sh outputs/train/act_Real_Panda_CartesianVel_SpaceMouse_v2/checkpoints/020000/pretrained_model
#   LEROBOT_POLICY_PATH=path/to/model ./eval_real_panda_cartesian_vel.sh

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
        candidate_envs="${LEROBOT_CONDA_ENVS:-lerobot-org lerobot-ros-isaac lerobot-ros}"
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

# ============================================================================
# POLICY CONFIGURATION
# ============================================================================

# Policy path - can be:
# 1. Command-line argument
# 2. LEROBOT_POLICY_PATH environment variable
# 3. HuggingFace Hub (e.g., ases200q2/Real_Panda_CartesianVel_SpaceMouse_policy)
# 4. Default: latest local checkpoint matching *Real_Panda_CartesianVel*act*

if [ -n "${1:-}" ]; then
    POLICY_PATH="$1"
    shift
    echo "Using policy path from command-line argument: ${POLICY_PATH}"
fi

if [ -z "${POLICY_PATH:-}" ]; then
    if [ -n "${LEROBOT_POLICY_PATH:-}" ]; then
        POLICY_PATH="${LEROBOT_POLICY_PATH}"
        echo "Using policy path from LEROBOT_POLICY_PATH: ${POLICY_PATH}"
    else
        TRAIN_OUTPUT_DIR="${PROJECT_ROOT}/outputs/train"
        HF_USER="${HF_USER:-ases200q2}"

        if [ -d "${TRAIN_OUTPUT_DIR}" ]; then
            # Find most recent dir matching *Real_Panda_CartesianVel*act* or act_Real_Panda*
            LATEST_TRAIN_DIR=$(find "${TRAIN_OUTPUT_DIR}" -maxdepth 1 -type d \( -name "*Real_Panda_CartesianVel*act*" -o -name "act_Real_Panda*" \) -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)
            if [ -n "${LATEST_TRAIN_DIR}" ]; then
                if [ -d "${LATEST_TRAIN_DIR}/checkpoints/last/pretrained_model" ]; then
                    POLICY_PATH="${LATEST_TRAIN_DIR}/checkpoints/last/pretrained_model"
                elif [ -d "${LATEST_TRAIN_DIR}/checkpoints/020000/pretrained_model" ]; then
                    POLICY_PATH="${LATEST_TRAIN_DIR}/checkpoints/020000/pretrained_model"
                else
                    CKPT=$(find "${LATEST_TRAIN_DIR}/checkpoints" -maxdepth 1 -type d -name "[0-9]*" 2>/dev/null | sort -V | tail -1)
                    if [ -n "${CKPT}" ] && [ -d "${CKPT}/pretrained_model" ]; then
                        POLICY_PATH="${CKPT}/pretrained_model"
                    fi
                fi
                if [ -n "${POLICY_PATH:-}" ]; then
                    echo "Found local checkpoint: ${POLICY_PATH}"
                fi
            fi
        fi

        if [ -z "${POLICY_PATH:-}" ]; then
            POLICY_PATH="${HF_USER}/Real_Panda_CartesianVel_SpaceMouse_policy"
            echo "No local checkpoint found. Using HuggingFace Hub: ${POLICY_PATH}"
        fi
    fi
fi

# ============================================================================
# EVALUATION DATASET CONFIGURATION
# ============================================================================

timestamp="$(date +%Y%m%d-%H%M%S)"
EVAL_DATASET_BASE_ROOT="${LEROBOT_EVAL_DATASET_ROOT:-${HOME}/lerobot_datasets/eval_Real_Panda_CartesianVel_ACT}"
EVAL_DATASET_ROOT="${EVAL_DATASET_BASE_ROOT}_${timestamp}"
EVAL_DATASET_REPO_ID="${LEROBOT_EVAL_DATASET_REPO_ID:-${HF_USER:-ases200q2}/eval_Real_Panda_CartesianVel_ACT_${timestamp}}"
echo "Evaluation dataset will be saved to: ${EVAL_DATASET_ROOT}"

# ============================================================================
# EVALUATION PARAMETERS (Real Panda Cartesian Velocity)
# ============================================================================

NUM_EVAL_EPISODES="${LEROBOT_EVAL_NUM_EPISODES:-10}"
SINGLE_TASK="${LEROBOT_SINGLE_TASK:-Pick up screwdriver}"

# Robot: panda_ros_cartesian (Cartesian velocity control via /cartesian_twist_controller/cmd_vel)
ROBOT_ID="${LEROBOT_ROBOT_ID:-my_panda_real}"
ROBOT_TYPE="${LEROBOT_ROBOT_TYPE:-panda_ros_cartesian}"

# Teleop: spacemouse_cartesian_vel_panda (for reset between episodes)
TELEOP_TYPE="${LEROBOT_TELEOP_TYPE:-spacemouse_cartesian_vel_panda}"
TELEOP_ID="${LEROBOT_TELEOP_ID:-my_spacemouse_leader}"
TELEOP_LINEAR_SCALE="${LEROBOT_TELEOP_LINEAR_SCALE:-0.05}"
TELEOP_DEAD_ZONE="${LEROBOT_TELEOP_DEAD_ZONE:-0.1}"

EPISODE_TIME_S="${LEROBOT_EPISODE_TIME_S:-30}"
RESET_TIME_S="${LEROBOT_RESET_TIME_S:-60}"

DATASET_FPS="${LEROBOT_DATASET_FPS:-30}"
DISPLAY_DATA="${LEROBOT_DISPLAY_DATA:-true}"
DATASET_VIDEO="${LEROBOT_DATASET_VIDEO:-true}"
DATASET_PUSH="${LEROBOT_EVAL_PUSH:-false}"
DATASET_PRIVATE="${LEROBOT_DATASET_PRIVATE:-false}"

NUM_IMAGE_WRITER_PROCESSES="${LEROBOT_NUM_IMAGE_WORKER_PROCESSES:-1}"
NUM_IMAGE_WRITER_THREADS="${LEROBOT_NUM_IMAGE_WRITER_THREADS:-8}"
VIDEO_ENCODING_BATCH_SIZE="${LEROBOT_VIDEO_ENCODING_BATCH_SIZE:-1}"

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

echo ""
echo "=========================================="
echo "Real Panda CartesianVel Policy Evaluation"
echo "=========================================="
echo "Policy path:       ${POLICY_PATH}"
echo "Robot type:       ${ROBOT_TYPE}"
echo "Robot ID:         ${ROBOT_ID}"
echo "Teleop type:      ${TELEOP_TYPE}"
echo "Teleop ID:        ${TELEOP_ID}"
echo "Num episodes:     ${NUM_EVAL_EPISODES}"
echo "Episode time:     ${EPISODE_TIME_S}s"
echo "Reset time:       ${RESET_TIME_S}s"
echo "Dataset location: ${EVAL_DATASET_ROOT}"
echo "Dataset repo ID:  ${EVAL_DATASET_REPO_ID}"
echo "Push to Hub:      ${DATASET_PUSH}"
echo "Display data:     ${DISPLAY_DATA}"
echo "=========================================="
echo ""
echo "IMPORTANT: Before running this script, ensure:"
echo "  1. Franka cartesian_twist_controller is running:"
echo "     ros2 launch franka_bringup cartesian_twist_controller.launch.py robot_ip:=<YOUR_IP>"
echo "  2. SpaceMouse driver is running:"
echo "     ros2 run spacenav spacenav_node"
echo "  3. RealSense camera is publishing to /rgb/camera_1:"
echo "     ./REAL_ROBOT/launch_realsense_camera.sh"
echo "  4. Robot is in a safe starting position"
echo ""
echo "During evaluation:"
echo "  - Policy will control the robot during episodes (${EPISODE_TIME_S}s each)"
echo "  - Use SpaceMouse during reset periods (${RESET_TIME_S}s) to:"
echo "    * Reposition objects"
echo "    * Move robot back to starting position"
echo "    * Prepare scene for next episode"
echo "=========================================="
echo ""

sleep 3

# ============================================================================
# RUN EVALUATION
# ============================================================================

exec lerobot-record \
  --robot.discover_packages_path=lerobot_robot_ros \
  --teleop.discover_packages_path=lerobot_teleoperator_devices \
  --robot.type="${ROBOT_TYPE}" \
  --robot.id="${ROBOT_ID}" \
  --teleop.type="${TELEOP_TYPE}" \
  --teleop.id="${TELEOP_ID}" \
  --teleop.linear_scale="${TELEOP_LINEAR_SCALE}" \
  --teleop.dead_zone="${TELEOP_DEAD_ZONE}" \
  --policy.path="${POLICY_PATH}" \
  --dataset.root="${EVAL_DATASET_ROOT}" \
  --dataset.repo_id="${EVAL_DATASET_REPO_ID}" \
  --dataset.single_task="${SINGLE_TASK}" \
  --dataset.num_episodes="${NUM_EVAL_EPISODES}" \
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
  "$@"
