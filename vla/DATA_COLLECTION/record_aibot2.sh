#!/usr/bin/env bash
# Record dataset with aibot2 dual-arm robot and push to Hugging Face.
#
# Usage:
#   ./record_aibot2.sh                          # use defaults
#   LEROBOT_NUM_EPISODES=5 ./record_aibot2.sh   # override via env
#
# Prerequisites:
#   - Robot running (ROS_DOMAIN_ID=90)
#   - source ~/ros2_alpha2_source.sh
#   - huggingface-cli login (for push)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/../.."

# ---------- ROS2 environment ----------
if [ -z "${ROS_DOMAIN_ID:-}" ]; then
    echo "Sourcing ROS2 environment..."
    source "${HOME}/ros2_alpha2_source.sh"
    source /opt/ros/humble/setup.bash
fi

# ---------- Python environment ----------
if [ -n "${VIRTUAL_ENV:-}" ]; then
    echo "Using existing virtual environment: ${VIRTUAL_ENV}"
elif [ -f "${PROJECT_ROOT}/.venv/bin/activate" ]; then
    source "${PROJECT_ROOT}/.venv/bin/activate"
    echo "Activated .venv at ${PROJECT_ROOT}/.venv"
fi

# Ensure local LeRobot ROS packages are importable even when only some of them
# are installed editable in the active Python environment.
export PYTHONPATH="${PROJECT_ROOT}/ros2/lerobot_robot_ros:${PROJECT_ROOT}/ros2/lerobot_teleoperator_devices:${PYTHONPATH:-}"

# ---------- Dataset settings ----------
DATASET_REPO_ID="${LEROBOT_DATASET_REPO_ID:-ases200q2/Aibot2_pick_object_from_table_v4}"
DATASET_ROOT="${LEROBOT_DATASET_ROOT:-${HOME}/lerobot_datasets/Aibot2_pick_object_from_table_v4}"
SINGLE_TASK="${LEROBOT_SINGLE_TASK:-Pick object from table}"
NUM_EPISODES="${LEROBOT_NUM_EPISODES:-50}"
EPISODE_TIME_S="${LEROBOT_EPISODE_TIME_S:-60}"
RESET_TIME_S="${LEROBOT_RESET_TIME_S:-60}"
DATASET_FPS="${LEROBOT_DATASET_FPS:-25}"
DATASET_PUSH="${LEROBOT_DATASET_PUSH:-true}"
DATASET_PRIVATE="${LEROBOT_DATASET_PRIVATE:-false}"
DATASET_VIDEO="${LEROBOT_DATASET_VIDEO:-true}"
DISPLAY_DATA="${LEROBOT_DISPLAY_DATA:-false}"

# ---------- VR teleop settings ----------
# VR/internal driver publishes and executes both target poses; LeRobot records
# those poses as actions but does not re-publish robot commands.
TELEOP_ID="${LEROBOT_TELEOP_ID:-my_aibot2_vr}"
TELEOP_TARGET_TOPIC="${LEROBOT_TELEOP_TARGET_TOPIC:-/control_poses_target}"
TELEOP_MESSAGE_TYPE="${LEROBOT_TELEOP_MESSAGE_TYPE:-geometry_msgs/msg/PoseArray}"
TELEOP_LEFT_POSE_INDEX="${LEROBOT_TELEOP_LEFT_POSE_INDEX:-0}"
TELEOP_RIGHT_POSE_INDEX="${LEROBOT_TELEOP_RIGHT_POSE_INDEX:-1}"
TELEOP_GRIPPER_JOINT_STATE_TOPIC="${LEROBOT_TELEOP_GRIPPER_JOINT_STATE_TOPIC:-/joint_states}"
TELEOP_LEFT_GRIPPER_JOINT="${LEROBOT_TELEOP_LEFT_GRIPPER_JOINT:-2FEG_l_Joint1}"
TELEOP_RIGHT_GRIPPER_JOINT="${LEROBOT_TELEOP_RIGHT_GRIPPER_JOINT:-2FEG_r_Joint1}"
TELEOP_GRIPPER_OPEN_VALUE="${LEROBOT_TELEOP_GRIPPER_OPEN_VALUE:-0.8}"
TELEOP_GRIPPER_CLOSE_VALUE="${LEROBOT_TELEOP_GRIPPER_CLOSE_VALUE:-0}"
TELEOP_REQUIRE_INITIAL_TARGET="${LEROBOT_TELEOP_REQUIRE_INITIAL_TARGET:-true}"

# ---------- Resume logic ----------
RESUME_INPUT="${LEROBOT_RESUME:-false}"
if [ "${RESUME_INPUT}" = "true" ]; then
    if [ ! -d "${DATASET_ROOT}" ]; then
        echo "Requested resume but ${DATASET_ROOT} does not exist." >&2
        exit 1
    fi
    DATASET_RESUME="true"
    echo "Resuming dataset in ${DATASET_ROOT}."
else
    if [ -d "${DATASET_ROOT}" ]; then
        timestamp="$(date +%Y%m%d-%H%M%S)"
        DATASET_ROOT="${DATASET_ROOT}_${timestamp}"
        echo "Dataset root exists; using ${DATASET_ROOT}."
    fi
    DATASET_RESUME="false"
fi

# ---------- Image writer settings ----------
NUM_IMAGE_WRITER_PROCESSES="${LEROBOT_NUM_IMAGE_WRITER_PROCESSES:-1}"
NUM_IMAGE_WRITER_THREADS="${LEROBOT_NUM_IMAGE_WRITER_THREADS:-8}"

# ---------- Camera settings ----------
# Aibot2 records 4 compressed cameras by default; override count to use fewer
export LEROBOT_CAMERA_COUNT="${LEROBOT_CAMERA_COUNT:-4}"
export LEROBOT_CAMERA_1_TOPIC="${LEROBOT_CAMERA_1_TOPIC:-/camera/camera_front/color/image_raw/compressed}"
export LEROBOT_CAMERA_2_TOPIC="${LEROBOT_CAMERA_2_TOPIC:-/camera/camera_left/color/image_raw/compressed}"
export LEROBOT_CAMERA_3_TOPIC="${LEROBOT_CAMERA_3_TOPIC:-/camera/camera_right/color/image_raw/compressed}"
export LEROBOT_CAMERA_4_TOPIC="${LEROBOT_CAMERA_4_TOPIC:-/camera/camera_top/color/image_raw/compressed}"
export LEROBOT_CAMERA_WIDTH="${LEROBOT_CAMERA_WIDTH:-320}"
export LEROBOT_CAMERA_HEIGHT="${LEROBOT_CAMERA_HEIGHT:-240}"
export LEROBOT_CAMERA_FPS="${LEROBOT_CAMERA_FPS:-25}"

echo ""
echo "=== Aibot2 Data Collection ==="
echo "  Robot:      aibot2"
echo "  Dataset:    ${DATASET_REPO_ID}"
echo "  Root:       ${DATASET_ROOT}"
echo "  Episodes:   ${NUM_EPISODES}"
echo "  FPS:        ${DATASET_FPS}"
echo "  Cameras:    ${LEROBOT_CAMERA_COUNT}"
echo "  VR topic:   ${TELEOP_TARGET_TOPIC}"
echo "  Grippers:   ${TELEOP_GRIPPER_JOINT_STATE_TOPIC}"
echo "  Push:       ${DATASET_PUSH}"
echo "==============================="
echo ""

exec lerobot-record \
  --robot.discover_packages_path=lerobot_robot_ros \
  --robot.type=aibot2 \
  --robot.id=my_aibot2 \
  --robot.execute_actions=false \
  --teleop.discover_packages_path=lerobot_teleoperator_devices \
  --teleop.type=vr_aibot2 \
  --teleop.id="${TELEOP_ID}" \
  --teleop.target_topic="${TELEOP_TARGET_TOPIC}" \
  --teleop.message_type="${TELEOP_MESSAGE_TYPE}" \
  --teleop.left_pose_index="${TELEOP_LEFT_POSE_INDEX}" \
  --teleop.right_pose_index="${TELEOP_RIGHT_POSE_INDEX}" \
  --teleop.gripper_joint_state_topic="${TELEOP_GRIPPER_JOINT_STATE_TOPIC}" \
  --teleop.left_gripper_joint_name="${TELEOP_LEFT_GRIPPER_JOINT}" \
  --teleop.right_gripper_joint_name="${TELEOP_RIGHT_GRIPPER_JOINT}" \
  --teleop.gripper_open_value="${TELEOP_GRIPPER_OPEN_VALUE}" \
  --teleop.gripper_close_value="${TELEOP_GRIPPER_CLOSE_VALUE}" \
  --teleop.require_initial_target="${TELEOP_REQUIRE_INITIAL_TARGET}" \
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
  --display_data="${DISPLAY_DATA}" \
  --resume="${DATASET_RESUME}" \
  "$@"
