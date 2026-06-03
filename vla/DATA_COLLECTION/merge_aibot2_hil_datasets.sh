#!/usr/bin/env bash
# Merge a base AIBOT2 dataset with human-in-the-loop correction episodes.
#
# Usage:
#   ./merge_aibot2_hil_datasets.sh BASE_REPO_ID HIL_REPO_ID [OUTPUT_REPO_ID]
#
# When the HIL dataset was saved to a custom local folder, pass its root:
#   LEROBOT_HIL_DATASET_ROOT=~/lerobot_datasets/Aibot2_hil_20260526-120000 \
#   ./merge_aibot2_hil_datasets.sh BASE_REPO_ID HIL_REPO_ID OUTPUT_REPO_ID
#
# Examples:
#   ./merge_aibot2_hil_datasets.sh \
#     ases200q2/Aibot2_combined_pick_object_datasets_updatad_2026_05_28_15fps \
#     ases200q2/Aibot2_hil_20260526-120000 \
#     ases200q2/Aibot2_combined_with_hil_v1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/../.."

if [ -n "${VIRTUAL_ENV:-}" ]; then
    echo "Using existing virtual environment: ${VIRTUAL_ENV}"
elif [ -f "${PROJECT_ROOT}/.venv/bin/activate" ]; then
    source "${PROJECT_ROOT}/.venv/bin/activate"
fi

BASE_REPO_ID="${1:-${LEROBOT_BASE_DATASET_REPO_ID:-}}"
HIL_REPO_ID="${2:-${LEROBOT_HIL_DATASET_REPO_ID:-}}"
OUTPUT_REPO_ID="${3:-${LEROBOT_MERGED_DATASET_REPO_ID:-}}"
PUSH_TO_HUB="${LEROBOT_DATASET_PUSH:-true}"

if [ -z "${BASE_REPO_ID}" ] || [ -z "${HIL_REPO_ID}" ]; then
    echo "Usage: $0 BASE_REPO_ID HIL_REPO_ID [OUTPUT_REPO_ID]" >&2
    exit 1
fi

CMD=(
    python "${SCRIPT_DIR}/merge_aibot2_hil_datasets.py"
    "${BASE_REPO_ID}"
    "${HIL_REPO_ID}"
)

if [ -n "${OUTPUT_REPO_ID}" ]; then
    CMD+=("${OUTPUT_REPO_ID}")
fi
if [ -n "${LEROBOT_BASE_DATASET_ROOT:-}" ]; then
    CMD+=(--base-root "${LEROBOT_BASE_DATASET_ROOT}")
fi
if [ -n "${LEROBOT_HIL_DATASET_ROOT:-}" ]; then
    CMD+=(--hil-root "${LEROBOT_HIL_DATASET_ROOT}")
fi
if [ -n "${LEROBOT_DATASET_ROOT:-}" ]; then
    CMD+=(--output-root "${LEROBOT_DATASET_ROOT}")
fi
if [ "${PUSH_TO_HUB}" = "true" ]; then
    CMD+=(--push-to-hub)
fi

echo ""
echo "=== Merge AIBOT2 HIL Dataset ==="
echo "  Base:   ${BASE_REPO_ID}"
echo "  HIL:    ${HIL_REPO_ID}"
echo "  Output: ${OUTPUT_REPO_ID:-<auto>}"
echo "================================"
echo ""

exec "${CMD[@]}"
