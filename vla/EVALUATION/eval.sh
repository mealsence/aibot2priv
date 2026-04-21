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
# 1. Command-line argument (e.g., "./eval.sh ases200q2/Isaac_panda_pick_cube_smolvla_20251117_222404")
# 2. Environment variable (e.g., LEROBOT_POLICY_PATH="path/to/model")
# 3. HuggingFace Hub model (e.g., "ases200q2/Isaac_panda_pick_cube_act_20250116_120000")
# 4. Local checkpoint path (e.g., "outputs/train/.../checkpoints/last/pretrained_model")
# 5. Policy type keyword (e.g., "act", "smolvla") - will use default path for that type
#
# Default: Construct from HF_USER and look for latest trained model

# List of known policy type keywords (not valid paths)
POLICY_TYPE_KEYWORDS="act smolvla diffusion tdmpc vqbet pi0 pi05"

if [ -n "${1:-}" ]; then
    # Check if the argument is a policy type keyword
    if echo "${POLICY_TYPE_KEYWORDS}" | grep -qw "${1}"; then
        echo "Detected policy type keyword: ${1}"
        echo "Using default policy path for ${1} policy type"
        # Don't set POLICY_PATH here, let it fall through to default logic
        shift  # Remove the keyword so "$@" passes remaining args to lerobot-record
    else
        # Treat as actual policy path
        POLICY_PATH="$1"
        shift  # Remove first argument so "$@" passes remaining args to lerobot-record
        echo "Using policy path from command-line argument: ${POLICY_PATH}"
    fi
fi

if [ -z "${POLICY_PATH:-}" ]; then
    if [ -n "${LEROBOT_POLICY_PATH:-}" ]; then
        POLICY_PATH="${LEROBOT_POLICY_PATH}"
        echo "Using policy path from LEROBOT_POLICY_PATH: ${POLICY_PATH}"
    else
        # Try to find the most recent training output
        HF_USER="${HF_USER:-ases200q2}"

        # Look for the most recent training directory
        TRAIN_OUTPUT_DIR="${PROJECT_ROOT}/outputs/train"

        if [ -d "${TRAIN_OUTPUT_DIR}" ]; then
            # Find the most recently modified training directory
            LATEST_TRAIN_DIR=$(find "${TRAIN_OUTPUT_DIR}" -maxdepth 1 -type d -name "*Isaac_panda_pick_cube_act_*" -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)

            if [ -n "${LATEST_TRAIN_DIR}" ] && [ -d "${LATEST_TRAIN_DIR}/checkpoints/last/pretrained_model" ]; then
                POLICY_PATH="${LATEST_TRAIN_DIR}/checkpoints/last/pretrained_model"
                echo "Found local checkpoint: ${POLICY_PATH}"
            else
                # Fall back to HuggingFace Hub - use most recent model pattern
                POLICY_PATH="${HF_USER}/Isaac_panda_pick_cube_act_20251116_101319"
                echo "No local checkpoint found. Will try HuggingFace Hub: ${POLICY_PATH}"
                echo "Note: lerobot-record will search for the latest matching model on the Hub"
            fi
        else
            # No local training outputs, try HuggingFace Hub
            POLICY_PATH="${HF_USER}/Isaac_panda_pick_cube_act_20251116_101319"
            echo "No training outputs found locally. Will try HuggingFace Hub: ${POLICY_PATH}"
        fi
    fi
fi

# ============================================================================
# EVALUATION DATASET CONFIGURATION
# ============================================================================

# Detect policy type from POLICY_PATH (e.g., "pi05" from "ases200q2/Isaac_panda_pick_cube_pi05_20251126_104013")
# Default to "unknown" if not detected
DETECTED_POLICY_TYPE="unknown"
for policy_type in ${POLICY_TYPE_KEYWORDS}; do
    if echo "${POLICY_PATH}" | grep -qi "_${policy_type}_\|_${policy_type}$\|/${policy_type}_\|/${policy_type}$"; then
        DETECTED_POLICY_TYPE="${policy_type}"
        break
    fi
done
# Convert to uppercase for display
DETECTED_POLICY_TYPE_UPPER=$(echo "${DETECTED_POLICY_TYPE}" | tr '[:lower:]' '[:upper:]')
echo "Detected policy type: ${DETECTED_POLICY_TYPE_UPPER}"

# Evaluation dataset storage location and settings
EVAL_DATASET_BASE_ROOT="${LEROBOT_EVAL_DATASET_ROOT:-${HOME}/lerobot_datasets/eval_Isaac_Panda_PickCube_${DETECTED_POLICY_TYPE_UPPER}}"

# Create timestamped evaluation directory to avoid overwriting previous results
timestamp="$(date +%Y%m%d-%H%M%S)"
EVAL_DATASET_ROOT="${EVAL_DATASET_BASE_ROOT}_${timestamp}"
echo "Evaluation dataset will be saved to: ${EVAL_DATASET_ROOT}"

# Evaluation dataset repository ID (for local storage only, not pushed to Hub)
EVAL_DATASET_REPO_ID="${LEROBOT_EVAL_DATASET_REPO_ID:-${HF_USER:-ases200q2}/eval_Isaac_Panda_PickCube_${DETECTED_POLICY_TYPE_UPPER}_${timestamp}}"

# ============================================================================
# EVALUATION PARAMETERS
# ============================================================================

# Number of evaluation episodes to run
NUM_EVAL_EPISODES="${LEROBOT_EVAL_NUM_EPISODES:-10}"

# Task description (should match training data)
SINGLE_TASK="${LEROBOT_SINGLE_TASK:-Pick cube from table}"

# Robot configuration
ROBOT_ID="${LEROBOT_ROBOT_ID:-my_panda_follower}"
ROBOT_TYPE="${LEROBOT_ROBOT_TYPE:-panda_ros_position}"

# Teleoperation configuration (for manual reset between episodes)
TELEOP_TYPE="${LEROBOT_TELEOP_TYPE:-spacemouse_ee_panda}"
TELEOP_ID="${LEROBOT_TELEOP_ID:-my_spacemouse_leader}"

# Episode timing
EPISODE_TIME_S="${LEROBOT_EPISODE_TIME_S:-60}"
RESET_TIME_S="${LEROBOT_RESET_TIME_S:-60}"

# Dataset recording settings
DATASET_FPS="${LEROBOT_DATASET_FPS:-30}"
DISPLAY_DATA="${LEROBOT_DISPLAY_DATA:-true}"
DATASET_VIDEO="${LEROBOT_DATASET_VIDEO:-true}"

# Hub settings (disabled for evaluation - keep data local)
DATASET_PUSH="${LEROBOT_EVAL_PUSH:-false}"
DATASET_PRIVATE="${LEROBOT_DATASET_PRIVATE:-false}"

# Performance optimization: Image writer settings
NUM_IMAGE_WRITER_PROCESSES="${LEROBOT_NUM_IMAGE_WORKER_PROCESSES:-1}"
NUM_IMAGE_WRITER_THREADS="${LEROBOT_NUM_IMAGE_WRITER_THREADS:-8}"
VIDEO_ENCODING_BATCH_SIZE="${LEROBOT_VIDEO_ENCODING_BATCH_SIZE:-1}"

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

echo ""
echo "=========================================="
echo "LeRobot Policy Evaluation"
echo "=========================================="
echo "Policy path:       ${POLICY_PATH}"
echo "Robot type:        ${ROBOT_TYPE}"
echo "Robot ID:          ${ROBOT_ID}"
echo "Teleop type:       ${TELEOP_TYPE}"
echo "Teleop ID:         ${TELEOP_ID}"
echo "Num episodes:      ${NUM_EVAL_EPISODES}"
echo "Episode time:      ${EPISODE_TIME_S}s"
echo "Reset time:        ${RESET_TIME_S}s"
echo "Dataset location:  ${EVAL_DATASET_ROOT}"
echo "Dataset repo ID:   ${EVAL_DATASET_REPO_ID}"
echo "Push to Hub:       ${DATASET_PUSH}"
echo "Display data:      ${DISPLAY_DATA}"
echo "=========================================="
echo ""
echo "IMPORTANT: Before running this script, ensure:"
echo "  1. Isaac Sim is running with ROS2 bridge enabled"
echo "  2. MoveIt + Isaac hardware interface is launched:"
echo "     cd isaac_franka_moveit_perception"
echo "     source install/setup.bash"
echo "     ros2 launch panda_moveit_config demo.launch.py ros2_control_hardware_type:=isaac"
echo "  3. SpaceMouse (or other teleop device) is connected"
echo "  4. Robot is in a safe starting position"
echo ""
echo "During evaluation:"
echo "  - Policy will control the robot during episodes (${EPISODE_TIME_S}s each)"
echo "  - Use SpaceMouse during reset periods (${RESET_TIME_S}s) to:"
echo "    * Reposition objects (cube, etc.)"
echo "    * Move robot back to starting position"
echo "    * Prepare scene for next episode"
echo "=========================================="
echo ""

# Give user a chance to cancel if something looks wrong
sleep 3

# Reduce noisy library HTTP/info logging during evaluation (overridable by env).
export HF_HUB_VERBOSITY="${HF_HUB_VERBOSITY:-error}"
export TRANSFORMERS_VERBOSITY="${TRANSFORMERS_VERBOSITY:-error}"

# ============================================================================
# RUN EVALUATION
# ============================================================================

# NOTE: For Isaac Sim + ROS2 robots, use lerobot-record with --policy.path
# (NOT lerobot-eval, which is only for gym-based simulation environments)
#
# Register ROS2 robot/teleop configs (panda_ros_*, spacemouse_*, etc.). LeRobot's
# auto-discovery only imports PyPI names starting with lerobot_robot_; our packages
# are named lerobot-robot-ros / lerobot-teleoperator-devices, so we must load them explicitly.

# Filter noisy low-value HTTP request spam from httpx/huggingface_hub while
# keeping all other warnings/errors visible.
lerobot-record \
  --robot.discover_packages_path=lerobot_robot_ros \
  --teleop.discover_packages_path=lerobot_teleoperator_devices \
  --robot.type="${ROBOT_TYPE}" \
  --robot.id="${ROBOT_ID}" \
  --teleop.type="${TELEOP_TYPE}" \
  --teleop.id="${TELEOP_ID}" \
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
  "$@" 2>&1 | sed '/_client.py:1025 HTTP Request:/d'
