#!/usr/bin/env bash
# Evaluate an AIBOT2 policy by publishing predicted hand poses to /control_poses_target.
#
# This matches AIBOT2 VR data collection:
#   action left/right pose -> geometry_msgs/msg/PoseArray -> /control_poses_target
#
# Usage:
#   ./eval_aibot2_control_poses_target.sh /path/to/pretrained_model
#   LEROBOT_POLICY_PATH=/path/to/pretrained_model ./eval_aibot2_control_poses_target.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/../.."

if [ -z "${ROS_DOMAIN_ID:-}" ]; then
    echo "Sourcing ROS2 environment..."
    source "${HOME}/ros2_alpha2_source.sh"
    source /opt/ros/humble/setup.bash
fi

if [ -n "${VIRTUAL_ENV:-}" ]; then
    echo "Using existing virtual environment: ${VIRTUAL_ENV}"
elif [ -f "${PROJECT_ROOT}/.venv/bin/activate" ]; then
    source "${PROJECT_ROOT}/.venv/bin/activate"
    echo "Activated .venv at ${PROJECT_ROOT}/.venv"
fi

export PYTHONPATH="${PROJECT_ROOT}/ros2/lerobot_robot_ros:${PROJECT_ROOT}/ros2/lerobot_teleoperator_devices:${PYTHONPATH:-}"

POLICY_PATH="${1:-${LEROBOT_POLICY_PATH:-}}"
if [ -z "${POLICY_PATH}" ]; then
    echo "Usage: $0 /path/to/pretrained_model" >&2
    echo "Or set LEROBOT_POLICY_PATH=/path/to/pretrained_model" >&2
    exit 1
fi
if [ "$#" -gt 0 ]; then
    shift
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
EVAL_DATASET_ROOT="${LEROBOT_EVAL_DATASET_ROOT:-${HOME}/lerobot_datasets/eval_Aibot2_control_poses_${timestamp}}"
EVAL_DATASET_REPO_ID="${LEROBOT_EVAL_DATASET_REPO_ID:-${HF_USER:-ases200q2}/eval_Aibot2_control_poses_${timestamp}}"
SINGLE_TASK="${LEROBOT_SINGLE_TASK:-Pick object from table}"
ROBOT_ID="${LEROBOT_ROBOT_ID:-my_aibot2}"
NUM_EVAL_EPISODES="${LEROBOT_EVAL_NUM_EPISODES:-1}"
EPISODE_TIME_S="${LEROBOT_EVAL_EPISODE_TIME_S:-60}"
RESET_TIME_S="${LEROBOT_EVAL_RESET_TIME_S:-0}"
DATASET_FPS="${LEROBOT_DATASET_FPS:-25}"
DISPLAY_DATA="${LEROBOT_DISPLAY_DATA:-false}"
DATASET_PUSH="${LEROBOT_EVAL_PUSH:-false}"
DATASET_PRIVATE="${LEROBOT_DATASET_PRIVATE:-false}"
RECORD_DATASET="${LEROBOT_EVAL_RECORD_DATASET:-false}"
DATASET_VIDEO="${LEROBOT_DATASET_VIDEO:-true}"
NUM_IMAGE_WRITER_PROCESSES="${LEROBOT_NUM_IMAGE_WRITER_PROCESSES:-1}"
NUM_IMAGE_WRITER_THREADS="${LEROBOT_NUM_IMAGE_WRITER_THREADS:-8}"
VIDEO_ENCODING_BATCH_SIZE="${LEROBOT_VIDEO_ENCODING_BATCH_SIZE:-1}"
CONTROL_POSES_TARGET_TOPIC="${LEROBOT_CONTROL_POSES_TARGET_TOPIC:-/control_poses_target}"
CONTROL_POSES_TARGET_FRAME_ID="${LEROBOT_CONTROL_POSES_TARGET_FRAME_ID:-base_link}"
GRIPPER_OPEN_POSITION="${LEROBOT_GRIPPER_OPEN_POSITION:-0.8}"
GRIPPER_CLOSE_POSITION="${LEROBOT_GRIPPER_CLOSE_POSITION:-0}"
ROBOT_NORMALIZE_GRIPPER_OBSERVATION="${LEROBOT_NORMALIZE_GRIPPER_OBSERVATION:-false}"

if [ "${RESET_TIME_S}" != "0" ]; then
    echo "LEROBOT_EVAL_RESET_TIME_S must be 0 for this no-teleop eval script." >&2
    echo "Reset the scene manually between separate runs, or add a reset teleop path first." >&2
    exit 1
fi

echo ""
echo "=== AIBOT2 Policy Evaluation ==="
echo "  Policy:     ${POLICY_PATH}"
echo "  Robot:      aibot2"
echo "  Output:     ${CONTROL_POSES_TARGET_TOPIC} (PoseArray)"
echo "  Frame:      ${CONTROL_POSES_TARGET_FRAME_ID}"
echo "  Grip obs:   normalized=${ROBOT_NORMALIZE_GRIPPER_OBSERVATION} (action is always 0=open,1=closed)"
echo "  Episodes:   ${NUM_EVAL_EPISODES}"
echo "  FPS:        ${DATASET_FPS}"
echo "==============================="
echo ""

exec lerobot-record \
  --robot.discover_packages_path=lerobot_robot_ros \
  --robot.type=aibot2 \
  --robot.id="${ROBOT_ID}" \
  --robot.execute_actions=true \
  --robot.action_output_mode=control_poses_target \
  --robot.normalize_gripper_observation="${ROBOT_NORMALIZE_GRIPPER_OBSERVATION}" \
  --robot.control_poses_target_topic="${CONTROL_POSES_TARGET_TOPIC}" \
  --robot.control_poses_target_frame_id="${CONTROL_POSES_TARGET_FRAME_ID}" \
  --robot.left_gripper_open_position="${GRIPPER_OPEN_POSITION}" \
  --robot.left_gripper_close_position="${GRIPPER_CLOSE_POSITION}" \
  --robot.right_gripper_open_position="${GRIPPER_OPEN_POSITION}" \
  --robot.right_gripper_close_position="${GRIPPER_CLOSE_POSITION}" \
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
