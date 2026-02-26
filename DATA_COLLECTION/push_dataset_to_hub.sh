#!/usr/bin/env bash
# Push a local LeRobot dataset to Hugging Face Hub.
#
# Usage:
#   ./push_dataset_to_hub.sh [DATASET_ROOT] [REPO_ID]
#
# Examples:
#   ./push_dataset_to_hub.sh
#     Uses LEROBOT_DATASET_ROOT and LEROBOT_DATASET_REPO_ID from env, or defaults
#
#   ./push_dataset_to_hub.sh ~/lerobot_datasets/Real_Panda_CartesianVel_SpaceMouse_20260226-132513
#     Pushes that folder to default repo (ases200q2/Real_Panda_CartesianVel_SpaceMouse)
#
#   ./push_dataset_to_hub.sh ~/lerobot_datasets/my_dataset myuser/my_dataset
#     Pushes to custom repo
#
# Prerequisites:
#   - huggingface-cli login   (or HF_TOKEN env var)
#   - Dataset must have valid meta/info.json with repo_id

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."

# Activate env
if [ -n "${VIRTUAL_ENV:-}" ]; then
    : # already active
elif [ -f "${PROJECT_ROOT}/.venv/bin/activate" ]; then
    source "${PROJECT_ROOT}/.venv/bin/activate"
fi

DATASET_ROOT="${1:-${LEROBOT_DATASET_ROOT:-}}"
REPO_ID="${2:-${LEROBOT_DATASET_REPO_ID:-ases200q2/Real_Panda_CartesianVel_SpaceMouse}}"

if [ -z "${DATASET_ROOT}" ]; then
    # Find most recent Real_Panda dataset
    BASE="${HOME}/lerobot_datasets"
    if [ -d "${BASE}" ]; then
        LATEST=$(ls -td "${BASE}"/Real_Panda_CartesianVel_SpaceMouse* 2>/dev/null | head -1)
        if [ -n "${LATEST}" ]; then
            DATASET_ROOT="${LATEST}"
            echo "Using most recent dataset: ${DATASET_ROOT}"
        fi
    fi
fi

if [ -z "${DATASET_ROOT}" ] || [ ! -d "${DATASET_ROOT}" ]; then
    echo "Usage: $0 [DATASET_ROOT] [REPO_ID]" >&2
    echo "" >&2
    echo "DATASET_ROOT: Path to dataset (e.g. ~/lerobot_datasets/Real_Panda_CartesianVel_SpaceMouse_20260226-132513)" >&2
    echo "REPO_ID: HuggingFace repo (default: ases200q2/Real_Panda_CartesianVel_SpaceMouse)" >&2
    echo "" >&2
    echo "Or set LEROBOT_DATASET_ROOT and LEROBOT_DATASET_REPO_ID" >&2
    exit 1
fi

echo "Pushing dataset to Hugging Face Hub..."
echo "  Root: ${DATASET_ROOT}"
echo "  Repo: ${REPO_ID}"
echo ""

python - "$DATASET_ROOT" "$REPO_ID" <<'PY'
import sys
from lerobot.datasets.lerobot_dataset import LeRobotDataset

dataset_root = sys.argv[1]
repo_id = sys.argv[2]

ds = LeRobotDataset(repo_id=repo_id, root=dataset_root)
ds.push_to_hub()

print(f"\nDone! View at: https://huggingface.co/datasets/{repo_id}")
PY
