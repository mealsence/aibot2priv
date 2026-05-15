#!/usr/bin/env bash
# Train policies on datasets collected by DATA_COLLECTION/record_aibot2.sh.
#
# Usage:
#   ./train_aibot2.sh                    # default policy: act
#   ./train_aibot2.sh smolvla            # set policy type
#   LEROBOT_DATASET_REPO_ID=user/ds ./train_aibot2.sh diffusion

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VLA_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${VLA_ROOT}"

activate_python_env() {
    if [ -n "${CONDA_PREFIX:-}" ]; then
        echo "[info] Using existing conda environment: ${CONDA_DEFAULT_ENV:-${CONDA_PREFIX}}"
        return
    fi

    if [ -n "${VIRTUAL_ENV:-}" ]; then
        echo "[info] Using existing virtual environment: ${VIRTUAL_ENV}"
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
            if conda env list | awk '{print $1}' | rg -x "${env_name}" >/dev/null 2>&1; then
                conda activate "${env_name}"
                echo "[info] Activated conda environment: ${env_name}"
                return
            fi
        done
    fi

    if [ -f "${PROJECT_ROOT}/.venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "${PROJECT_ROOT}/.venv/bin/activate"
        echo "[info] Activated virtual environment at ${PROJECT_ROOT}/.venv"
        return
    fi

    if [ -f "${VLA_ROOT}/.venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "${VLA_ROOT}/.venv/bin/activate"
        echo "[info] Activated virtual environment at ${VLA_ROOT}/.venv"
        return
    fi

    echo "[error] No matching conda env or .venv found. Please create one of: lerobot-org, lerobot-ros-isaac, lerobot-ros" >&2
    exit 1
}

activate_python_env

POLICY_TYPE="${1:-act}"
SUPPORTED_POLICIES=("act" "smolvla" "diffusion" "tdmpc" "vqbet" "pi0" "pi05" "groot" "sac" "vla0_smol" "wall_x" "wallx")

if [[ ! " ${SUPPORTED_POLICIES[*]} " =~ " ${POLICY_TYPE} " ]]; then
    echo "[error] Unsupported policy type: ${POLICY_TYPE}" >&2
    echo "[info] Supported policies: ${SUPPORTED_POLICIES[*]}" >&2
    echo "[info] Usage: $0 [policy_type]" >&2
    echo "[info] Example: $0 smolvla" >&2
    exit 1
fi

TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
DATASET_REPO_ID="${LEROBOT_DATASET_REPO_ID:-ases200q2/Aibot2_pick_object_from_table_v6}"
MODEL_REPO_ID="${LEROBOT_MODEL_REPO_ID:-${HF_USER:-ases200q2}/Aibot2_pick_object_from_table_v6_${POLICY_TYPE}_${TIMESTAMP}}"
OUTPUT_DIR="${LEROBOT_OUTPUT_DIR:-outputs/train/${MODEL_REPO_ID//\//_}}"
JOB_NAME="${LEROBOT_JOB_NAME:-${MODEL_REPO_ID//\//_}}"
BATCH_SIZE="${LEROBOT_BATCH_SIZE:-32}"
STEPS="${LEROBOT_STEPS:-80000}"
SAVE_FREQ="${LEROBOT_SAVE_FREQ:-10000}"
NUM_WORKERS="${LEROBOT_NUM_WORKERS:-4}"
WANDB_ENABLE="${LEROBOT_WANDB_ENABLE:-true}"
PUSH_TO_HUB="${LEROBOT_PUSH_TO_HUB:-true}"
DEVICE="${LEROBOT_DEVICE:-cuda}"
DATASET_STREAMING="${LEROBOT_DATASET_STREAMING:-false}"
VIDEO_BACKEND="${LEROBOT_VIDEO_BACKEND:-pyav}"

export PYTORCH_ALLOC_CONF="${PYTORCH_ALLOC_CONF:-expandable_segments:True}"

if [[ "${POLICY_TYPE}" == "pi05" ]]; then
    TRAIN_CMD=(
        python "${SCRIPT_DIR}/train_pi05_8bit.py"
    )
else
    TRAIN_CMD=(
        lerobot-train
    )
fi

TRAIN_CMD+=(
    --dataset.repo_id="${DATASET_REPO_ID}"
    --dataset.streaming="${DATASET_STREAMING}"
    --dataset.video_backend="${VIDEO_BACKEND}"
    --output_dir="${OUTPUT_DIR}"
    --job_name="${JOB_NAME}"
    --policy.device="${DEVICE}"
    --wandb.enable="${WANDB_ENABLE}"
    --policy.push_to_hub="${PUSH_TO_HUB}"
    --policy.repo_id="${MODEL_REPO_ID}"
    --batch_size="${BATCH_SIZE}"
    --steps="${STEPS}"
    --save_freq="${SAVE_FREQ}"
    --num_workers="${NUM_WORKERS}"
)

if [[ "${POLICY_TYPE}" == "smolvla" ]]; then
    TRAIN_CMD+=(--policy.type=smolvla)
elif [[ "${POLICY_TYPE}" == "pi05" ]]; then
    TRAIN_CMD+=(--policy.type=pi05)
    TRAIN_CMD+=(--policy.pretrained_path="${LEROBOT_PI05_PRETRAINED_PATH:-lerobot/pi05_base}")
    TRAIN_CMD+=(--policy.compile_model=true)
    TRAIN_CMD+=(--policy.gradient_checkpointing=true)
    TRAIN_CMD+=(--policy.dtype=bfloat16)
    TRAIN_CMD+=(--use_policy_training_preset=false)
    TRAIN_CMD+=(--optimizer.type=adamw_8bit)
    TRAIN_CMD+=(--optimizer.lr="${LEROBOT_PI05_LR:-2.5e-5}")
    TRAIN_CMD+=(--optimizer.betas="${LEROBOT_PI05_BETAS:-[0.9, 0.95]}")
    TRAIN_CMD+=(--optimizer.weight_decay="${LEROBOT_PI05_WEIGHT_DECAY:-0.01}")
    TRAIN_CMD+=(--optimizer.grad_clip_norm="${LEROBOT_PI05_GRAD_CLIP_NORM:-1.0}")
    TRAIN_CMD+=(--scheduler.type=cosine_decay_with_warmup)
    TRAIN_CMD+=(--scheduler.peak_lr="${LEROBOT_PI05_PEAK_LR:-2.5e-5}")
    TRAIN_CMD+=(--scheduler.decay_lr="${LEROBOT_PI05_DECAY_LR:-2.5e-6}")
    TRAIN_CMD+=(--scheduler.num_warmup_steps="${LEROBOT_PI05_WARMUP_STEPS:-1000}")
    TRAIN_CMD+=(--scheduler.num_decay_steps="${LEROBOT_PI05_DECAY_STEPS:-30000}")
elif [[ "${POLICY_TYPE}" == "pi0" ]]; then
    TRAIN_CMD+=(--policy.type=pi0)
    TRAIN_CMD+=(--policy.pretrained_path="${LEROBOT_PI0_PRETRAINED_PATH:-lerobot/pi0_base}")
    TRAIN_CMD+=(--policy.compile_model=true)
    TRAIN_CMD+=(--policy.gradient_checkpointing=true)
    TRAIN_CMD+=(--policy.dtype=bfloat16)
else
    TRAIN_CMD+=(--policy.type="${POLICY_TYPE}")
fi

echo ""
echo "=== AIBOT2 Training ==="
echo "  Policy:     ${POLICY_TYPE}"
echo "  Dataset:    ${DATASET_REPO_ID}"
echo "  Model repo: ${MODEL_REPO_ID}"
echo "  Output dir: ${OUTPUT_DIR}"
echo "  Device:     ${DEVICE}"
echo "  Batch size: ${BATCH_SIZE}"
echo "  Steps:      ${STEPS}"
echo "======================="
echo ""

"${TRAIN_CMD[@]}" "${@:2}"
