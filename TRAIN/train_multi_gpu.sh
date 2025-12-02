#!/usr/bin/env bash
set -euo pipefail

# Resolve repository root (parent of this script's directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Activate conda environment
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
            if conda env list | awk '{print $1}' | grep -x "${env_name}" >/dev/null 2>&1; then
                conda activate "${env_name}"
                echo "[info] Activated conda environment: ${env_name}"
                return
            fi
        done
    fi

    if [ -f "${REPO_ROOT}/.venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "${REPO_ROOT}/.venv/bin/activate"
        echo "[info] Activated virtual environment at ${REPO_ROOT}/.venv"
        return
    fi

    echo "[error] No matching conda env or .venv found. Please create one of: lerobot-org, lerobot-ros-isaac, lerobot-ros" >&2
    exit 1
}

activate_python_env

# Parse command-line arguments
POLICY_TYPE="${1:-act}"
SUPPORTED_POLICIES=("act" "smolvla" "diffusion" "tdmpc" "vqbet" "pi0" "pi05" "groot" "sac")

# Validate policy type
if [[ ! " ${SUPPORTED_POLICIES[*]} " =~ " ${POLICY_TYPE} " ]]; then
  echo "[error] Unsupported policy type: ${POLICY_TYPE}" >&2
  echo "[info] Supported policies: ${SUPPORTED_POLICIES[*]}" >&2
  echo "[info] Usage: $0 [policy_type]" >&2
  echo "[info] Example: $0 smolvla" >&2
  exit 1
fi

echo "[info] Training policy type: ${POLICY_TYPE} with multi-GPU support"

# Generate timestamp for unique model identification
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Set model repo ID with timestamp and policy type
MODEL_REPO_ID="${HF_USER:-ases200q2}/Isaac_panda_pick_cube_${POLICY_TYPE}_multi_gpu_${TIMESTAMP}"

# Set unique output directory and job name using timestamp and policy type
OUTPUT_DIR="outputs/train/${POLICY_TYPE}_multi_gpu_${TIMESTAMP}"
JOB_NAME="${POLICY_TYPE}_multi_gpu_${TIMESTAMP}"

# Set PyTorch CUDA allocator to reduce memory fragmentation
export PYTORCH_ALLOC_CONF=expandable_segments:True

# Build base training command for multi-GPU training
# Start with accelerate launch arguments
ACCELERATE_ARGS=(
  accelerate launch
  --multi_gpu
  --num_processes=2
)

# Add mixed precision for pi05 to reduce memory usage
if [[ "${POLICY_TYPE}" == "pi05" ]] || [[ "${POLICY_TYPE}" == "pi0" ]]; then
  ACCELERATE_ARGS+=(--mixed_precision=bf16)
fi

# Determine training script based on policy type
# PI05 uses custom script with 8-bit optimizer for memory efficiency
if [[ "${POLICY_TYPE}" == "pi05" ]]; then
  TRAIN_SCRIPT="${SCRIPT_DIR}/train_pi05_8bit.py"
else
  TRAIN_SCRIPT="$(which lerobot-train)"
fi

TRAIN_CMD=(
  "${ACCELERATE_ARGS[@]}"
  "${TRAIN_SCRIPT}"
  --dataset.repo_id="${HF_USER:-ases200q2}/Isaac_Panda_PickCube_SpaceMouse_EE_50eps"
  --dataset.video_backend=pyav
  --policy.repo_id="${MODEL_REPO_ID}"
  --output_dir="${OUTPUT_DIR}"
  --job_name="${JOB_NAME}"
  --wandb.enable=true
  --policy.device=cuda
  --policy.push_to_hub=true
  --num_workers=4
  --batch_size=16
  --steps=5000
)

# Add policy-specific configuration
if [[ "${POLICY_TYPE}" == "smolvla" ]]; then
  # SmolVLA can use pretrained base model or train from scratch
  TRAIN_CMD+=(--policy.type=smolvla)
elif [[ "${POLICY_TYPE}" == "pi05" ]]; then
  # PI05: Fine-tuning from pretrained base model with 8-bit optimizer
  TRAIN_CMD+=(--policy.type=pi05)
  TRAIN_CMD+=(--policy.pretrained_path=lerobot/pi05_base)
  # Memory optimizations
  TRAIN_CMD+=(--policy.compile_model=true)
  TRAIN_CMD+=(--policy.gradient_checkpointing=true)
  TRAIN_CMD+=(--policy.dtype=bfloat16)
  # Use 8-bit AdamW optimizer (registered by train_pi05_8bit.py)
  TRAIN_CMD+=(--use_policy_training_preset=false)
  TRAIN_CMD+=(--optimizer.type=adamw_8bit)
  TRAIN_CMD+=(--optimizer.lr=2.5e-5)
  TRAIN_CMD+=(--optimizer.betas="[0.9, 0.95]")
  TRAIN_CMD+=(--optimizer.weight_decay=0.01)
  TRAIN_CMD+=(--optimizer.grad_clip_norm=1.0)
  TRAIN_CMD+=(--scheduler.type=cosine_decay_with_warmup)
  TRAIN_CMD+=(--scheduler.peak_lr=2.5e-5)
  TRAIN_CMD+=(--scheduler.decay_lr=2.5e-6)
  TRAIN_CMD+=(--scheduler.num_warmup_steps=1000)
  TRAIN_CMD+=(--scheduler.num_decay_steps=30000)
elif [[ "${POLICY_TYPE}" == "pi0" ]]; then
  # PI0: Fine-tuning from pretrained base model
  TRAIN_CMD+=(--policy.type=pi0)
  TRAIN_CMD+=(--policy.pretrained_path=lerobot/pi0_base)
  TRAIN_CMD+=(--policy.compile_model=true)
  TRAIN_CMD+=(--policy.gradient_checkpointing=true)
  TRAIN_CMD+=(--policy.dtype=bfloat16)
else
  TRAIN_CMD+=(--policy.type="${POLICY_TYPE}")
fi

# Train using multi-GPU acceleration
echo "[info] Running multi-GPU training command..."
echo "[info] Number of processes: 2"
echo "[info] Number of machines: 1 (default)"
if [[ "${POLICY_TYPE}" == "pi05" ]] || [[ "${POLICY_TYPE}" == "pi0" ]]; then
  echo "[info] Mixed precision: bf16 (enabled for memory optimization)"
fi
echo "[info] Model repository ID: ${MODEL_REPO_ID}"
echo "[info] Output directory: ${OUTPUT_DIR}"
echo "[info] Job name: ${JOB_NAME}"
if [[ "${POLICY_TYPE}" == "pi05" ]]; then
  echo "[info] PI05 memory optimizations: gradient_checkpointing, dtype=bfloat16, compile_model, adamw_8bit optimizer"
fi
"${TRAIN_CMD[@]}"
