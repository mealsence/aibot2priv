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

echo "[info] Training policy type: ${POLICY_TYPE}"

# Set PyTorch CUDA allocator to reduce memory fragmentation
export PYTORCH_ALLOC_CONF=expandable_segments:True

# Generate timestamp for unique model identification
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Set model repo ID with timestamp and policy type
MODEL_REPO_ID="${HF_USER:-ases200q2}/Isaac_panda_pick_cube_${POLICY_TYPE}_${TIMESTAMP}"

# Determine training command based on policy type
# PI05 uses custom script with 8-bit optimizer for memory efficiency
if [[ "${POLICY_TYPE}" == "pi05" ]]; then
  TRAIN_CMD=(
    python "${SCRIPT_DIR}/train_pi05_8bit.py"
  )
else
  TRAIN_CMD=(
    lerobot-train
  )
fi

# Add common training arguments
TRAIN_CMD+=(
  --dataset.repo_id="ases200q2/Isaac_Panda_PickCube_SpaceMouse_EE_50eps"
  --dataset.streaming=false
  --dataset.video_backend=pyav
  --output_dir="outputs/train/${MODEL_REPO_ID//\//_}"
  --job_name="panda_pick_cube_${POLICY_TYPE}"
  --policy.device=cuda
  --wandb.enable=true
  --policy.push_to_hub=true
  --policy.repo_id="${MODEL_REPO_ID}"
  --batch_size=8
  --steps=3000
)

# Add policy-specific configuration
if [[ "${POLICY_TYPE}" == "smolvla" ]]; then
  # SmolVLA can use pretrained base model or train from scratch
  # Using --policy.type=smolvla for training from scratch
  # Alternatively, use --policy.path=lerobot/smolvla_base for finetuning
  TRAIN_CMD+=(--policy.type=smolvla)
  # Optionally use pretrained base (uncomment to use):
  # TRAIN_CMD+=(--policy.path=lerobot/smolvla_base)
elif [[ "${POLICY_TYPE}" == "pi05" ]]; then
  # PI05: Fine-tuning from pretrained base model (recommended)
  # Uses custom training script with 8-bit AdamW optimizer for memory efficiency
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
  # Reduce num_workers to save system memory
  TRAIN_CMD+=(--num_workers=2)
elif [[ "${POLICY_TYPE}" == "pi0" ]]; then
  # PI0: Fine-tuning from pretrained base model (recommended)
  # Use --policy.pretrained_path=lerobot/pi0_base for fine-tuning
  TRAIN_CMD+=(--policy.type=pi0)
  TRAIN_CMD+=(--policy.pretrained_path=lerobot/pi0_base)
  # Additional PI0-specific optimizations
  TRAIN_CMD+=(--policy.compile_model=true)
  TRAIN_CMD+=(--policy.gradient_checkpointing=true)
  TRAIN_CMD+=(--policy.dtype=bfloat16)
  # To train from scratch instead, comment out the pretrained_path line above
else
  TRAIN_CMD+=(--policy.type="${POLICY_TYPE}")
fi

# Train using settings from docs/source/il_sim.mdx (lines 127-133)
# Using streaming mode to avoid loading entire dataset into memory
# Reduced batch size and num_workers to minimize memory usage
echo "[info] Running training command..."
echo "[info] Model repository ID: ${MODEL_REPO_ID}"
if [[ "${POLICY_TYPE}" == "pi05" ]]; then
  echo "[info] PI05 memory optimizations: gradient_checkpointing, dtype=bfloat16, compile_model, adamw_8bit optimizer"
fi
if [[ "${POLICY_TYPE}" == "pi0" ]]; then
  echo "[info] PI0 memory optimizations: gradient_checkpointing, dtype=bfloat16, compile_model"
fi
"${TRAIN_CMD[@]}"
