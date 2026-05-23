#!/usr/bin/env bash
# Train Pi0.5 on:
#   ases200q2/Aibot2_pick_object_from_table_and_put_it_inside_the_box_v1_rosbag
#
# This script is for dataset-only finetuning (no simulator env eval).
# It disables eval by default and uses MEAN_STD normalization mapping for
# datasets that do not yet include pi05 quantile stats.
#
# Usage:
#   ./vla/TRAIN/train_pi05_aibot2.sh
#
# Optional env overrides:
#   OUTPUT_DIR=./my_run
#   REPO_ID=pi05_aibot2_pick_box_v1
#   HF_USER=ases200q2
#   PRETRAINED=lerobot/pi05_base
#   STEPS=20000
#   BATCH_SIZE=32
#   SAVE_FREQ=5000
#   SEED=1000
#   RESUME=false
#   WANDB=true
#   WANDB_PROJECT=lerobot_Aibot2_pick_box_v1
#   DTYPE=bfloat16
#   USE_PI05_QUANTILES=0   # set to 1 only if dataset has q01/q99 stats
#
# Args after script are forwarded to lerobot-train.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VLA_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUTPUT_ROOT="${VLA_ROOT}/outputs"

DATASET_REPO_ID="${DATASET_REPO_ID:-ases200q2/Aibot2_combined_pick_object_datasets_15fps}"
DATASET_NAME="${DATASET_REPO_ID##*/}"
HF_USER="${HF_USER:-ases200q2}"
TIMESTAMP="$(date +%Y%m%d_%H%M)"

OUTPUT_DIR="${OUTPUT_DIR:-$OUTPUT_ROOT/train/lerobot_${DATASET_NAME}_pi05_${TIMESTAMP}}"
REPO_ID="${REPO_ID:-lerobot_${DATASET_NAME}_pi05_${TIMESTAMP}}"
PRETRAINED="${PRETRAINED:-lerobot/pi05_base}"
STEPS="${STEPS:-20000}"
BATCH_SIZE="${BATCH_SIZE:-16}"
SAVE_FREQ="${SAVE_FREQ:-5000}"
SEED="${SEED:-1000}"
RESUME="${RESUME:-false}"
WANDB="${WANDB:-true}"
WANDB_PROJECT="${WANDB_PROJECT:-lerobot_${DATASET_NAME}}"
DTYPE="${DTYPE:-bfloat16}"
USE_PI05_QUANTILES="${USE_PI05_QUANTILES:-0}"
PUSH_TO_HUB="${PUSH_TO_HUB:-true}"

if [[ "${USE_PI05_QUANTILES}" == "1" ]]; then
  NORM_FLAGS=()
else
  # Recommended for pi05 when q01/q99 stats are not available in the dataset.
  NORM_FLAGS=(--policy.normalization_mapping='{"VISUAL":"IDENTITY","STATE":"MEAN_STD","ACTION":"MEAN_STD"}')
fi

activate_python_env() {
  if [[ -n "${CONDA_PREFIX:-}" || -n "${VIRTUAL_ENV:-}" ]]; then
    return
  fi

  if [[ -f "${PROJECT_ROOT}/.venv/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source "${PROJECT_ROOT}/.venv/bin/activate"
    echo "[info] Activated virtual environment at ${PROJECT_ROOT}/.venv"
    return
  fi

  echo "[error] No .venv found at ${PROJECT_ROOT}/.venv" >&2
  exit 1
}

activate_python_env
export PYTORCH_ALLOC_CONF="${PYTORCH_ALLOC_CONF:-expandable_segments:True}"

ensure_pi05_transformers() {
  if python -c "from transformers.models.siglip import check; raise SystemExit(0 if check.check_whether_transformers_replace_is_installed_correctly() else 1)" 2>/dev/null; then
    return
  fi

  echo "[info] Installing patched transformers required for pi05..."
  if command -v uv >/dev/null 2>&1; then
    uv pip install --index-strategy unsafe-best-match \
      "transformers @ git+https://github.com/huggingface/transformers.git@fix/lerobot_openpi"
  else
    pip install \
      "transformers @ git+https://github.com/huggingface/transformers.git@fix/lerobot_openpi"
  fi
}

ensure_pi05_transformers

cd "${VLA_ROOT}"

lerobot-train \
  --policy.type=pi05 \
  --policy.repo_id="${HF_USER}/${REPO_ID}" \
  --policy.pretrained_path="${PRETRAINED}" \
  --policy.push_to_hub="${PUSH_TO_HUB}" \
  --policy.dtype="${DTYPE}" \
  --policy.compile_model=true \
  --policy.gradient_checkpointing=true \
  --policy.freeze_vision_encoder=false \
  --policy.train_expert_only=false \
  --policy.device=cuda \
  "${NORM_FLAGS[@]}" \
  --dataset.repo_id="${DATASET_REPO_ID}" \
  --output_dir="${OUTPUT_DIR}" \
  --job_name="${REPO_ID}" \
  --steps="${STEPS}" \
  --batch_size="${BATCH_SIZE}" \
  --seed="${SEED}" \
  --resume="${RESUME}" \
  --eval_freq=0 \
  --save_freq="${SAVE_FREQ}" \
  --wandb.enable="${WANDB}" \
  --wandb.project="${WANDB_PROJECT}" \
  "$@"
