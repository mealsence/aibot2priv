#!/usr/bin/env bash
# Convert AIBOT2 ROS2 bag folders into a LeRobot dataset.
#
# Usage:
#   ./convert_aibot2_rosbags.sh ~/aibot2/rosbags/2026-05-20 --push-to-hub
#   ./convert_aibot2_rosbags.sh --limit 2 --dry-run
#
# If no bag directory is supplied, the script uses today's folder when it
# exists, otherwise the newest dated folder under ~/aibot2/rosbags.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/../.."

if [[ -f /opt/ros/humble/setup.bash ]]; then
    set +u
    source /opt/ros/humble/setup.bash
    set -u
fi

if [[ -z "${VIRTUAL_ENV:-}" && -f "${PROJECT_ROOT}/.venv/bin/activate" ]]; then
    set +u
    source "${PROJECT_ROOT}/.venv/bin/activate"
    set -u
fi

export PYTHONPATH="${PROJECT_ROOT}/ros2/lerobot_robot_ros:${PROJECT_ROOT}/ros2/lerobot_teleoperator_devices:${PYTHONPATH:-}"

default_bag_dir() {
    local base_dir="${HOME}/aibot2/rosbags"
    local today_dir="${base_dir}/$(date +%F)"
    local latest_dir=""

    if [[ -d "${today_dir}" ]]; then
        printf '%s\n' "${today_dir}"
        return
    fi

    if [[ -d "${base_dir}" ]]; then
        latest_dir="$(find "${base_dir}" -mindepth 1 -maxdepth 1 -type d -name '????-??-??' | sort | tail -n 1 || true)"
    fi

    if [[ -n "${latest_dir}" ]]; then
        printf '%s\n' "${latest_dir}"
    else
        printf '%s\n' "${today_dir}"
    fi
}

if [[ $# -gt 0 && "$1" != -* ]]; then
    BAG_DIR="$1"
    shift
else
    BAG_DIR="${AIBOT2_ROSBAG_DIR:-$(default_bag_dir)}"
fi

exec python "${SCRIPT_DIR}/convert_aibot2_rosbags.py" "${BAG_DIR}" "$@"
