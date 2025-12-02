#!/bin/bash

# =============================================================================
# LeRobot Training and Evaluation Commands
# =============================================================================

set -e  # Exit on any error

# =============================================================================
# DATASET VISUALIZATION
# =============================================================================

echo "=== Dataset Visualization Commands ==="

# Visualize gamepad grasp dataset
visualize_gamepad_dataset() {
    echo "Visualizing gamepad grasp dataset..."
    python -m lerobot.scripts.visualize_dataset_html --repo-id ases200q2/test_gamepad_grasp
}

# Visualize any dataset with custom repo ID
visualize_dataset() {
    if [ $# -eq 0 ]; then
        echo "Usage: visualize_dataset <repo_id>"
        echo "Example: visualize_dataset ases200q2/test_spacemouse_grasp"
        return 1
    fi
    local repo_id=$1
    echo "Visualizing dataset: $repo_id"
    python -m lerobot.scripts.visualize_dataset_html --repo-id "$repo_id"
}

# =============================================================================
# POLICY EVALUATION
# =============================================================================

echo "=== Policy Evaluation Commands ==="

# Evaluate policy with config file
eval_policy_with_config() {
    local config_path=${1:-"lerobot-example-config-files/eval_config_gym_hil.json"}
    echo "Evaluating policy with config: $config_path"
    python -m lerobot.scripts.eval --config_path="$config_path"
}

# Evaluate SmolVLA model on dataset
eval_smolvla_model() {
    local checkpoint=${1:-"ases200q2/PandaPickCubeSpacemouseRandom2_smolvla"}
    local device=${2:-"cuda:0"}
    local num_episodes=${3:-5}
    echo "Evaluating SmolVLA model..."
    echo "Checkpoint: $checkpoint"
    echo "Device: $device"
    echo "Episodes: $num_episodes"
    python EVALUATE/evaluate_smolvla_model.py \
        --checkpoint "$checkpoint" \
        --device "$device" \
        --num-episodes "$num_episodes"
}


# Evaluate SmolVLA model on simulation
eval_smolvla_simulation() {
    local checkpoint=${1:-"ases200q2/PandaPickCubeSpacemouseRandom2_smolvla"}
    local device=${2:-"cuda:0"}
    local num_episodes=${3:-5}
    echo "Evaluating SmolVLA model..."
    echo "Checkpoint: $checkpoint"
    echo "Device: $device"
    echo "Episodes: $num_episodes"
    python EVALUATE/evaluate_smolvla_simulation.py \
        --checkpoint "$checkpoint" \
        --device "$device" \
        --num-episodes "$num_episodes"
}







# Evaluate ACT model in simulation
eval_act_simulation() {
    local checkpoint=${1:-"ases200q2/PandaPickCubeSpacemouseRandom2"}
    local device=${2:-"cuda:0"}
    local num_episodes=${3:-5}
    local dataset=${4:-"ases200q2/PandaPickCubeSpacemouseRandom2"}
    echo "Evaluating ACT model in simulation..."
    echo "Checkpoint: $checkpoint"
    echo "Device: $device"
    echo "Episodes: $num_episodes"
    echo "Dataset: $dataset"
    python EVALUATE/evaluate_act_simulation.py \
        --checkpoint "$checkpoint" \
        --device "$device" \
        --num-episodes "$num_episodes" \
        --dataset "$dataset"
}

# Evaluate ACT model on dataset
eval_act_model() {
    local checkpoint=${1:-"ases200q2/PandaPickCubeSpacemouseRandom2_ACT"}
    local device=${2:-"cuda:0"}
    local num_episodes=${3:-5}
    echo "Evaluating ACT model on dataset..."
    echo "Checkpoint: $checkpoint"
    echo "Device: $device"
    echo "Episodes: $num_episodes"
    python EVALUATE/evaluate_act_model.py \
        --checkpoint "$checkpoint" \
        --device "$device" \
        --num-episodes "$num_episodes"
}

# =============================================================================
# MODEL TRAINING
# =============================================================================

echo "=== Model Training Commands ==="

# Train SmolVLA model
train_smolvla() {
    local dataset_id=${1:-"ases200q2/PandaPickCubeSpacemouseRandom2"}
    local output_dir=${2:-"outputs/train/PandaPickCubeSpacemouseRandom2_smolvla_HM_16102025"}
    local job_name=${3:-"PandaPickCubeSpacemouseRandom2_smolvla_HM_16102025"}
    local steps=${4:-50000}
    local batch_size=${5:-32}
    local repo_id=${6:-"ases200q2/$job_name"}
    
    echo "Training SmolVLA model..."
    echo "Dataset: $dataset_id"
    echo "Output: $output_dir"
    echo "Steps: $steps"
    echo "Batch size: $batch_size"
    
    python -m lerobot.scripts.train \
        --policy.path=lerobot/smolvla_base \
        --dataset.repo_id="$dataset_id" \
        --batch_size="$batch_size" \
        --steps="$steps" \
        --output_dir="$output_dir" \
        --job_name="$job_name" \
        --policy.device=cuda \
        --wandb.enable=true \
        --policy.repo_id="$repo_id"
}

# Train ACT model - Dataset 1
train_act_dataset1() {
    local dataset_id=${1:-"ases200q2/PandaPickCubeSpacemouseRandom1"}
    local output_dir=${2:-"outputs/train/PandaPickCubeSpacemouseRandom1_ACT"}
    local job_name=${3:-"PandaPickCubeSpacemouseRandom1_ACT"}
    local steps=${4:-10000}
    local batch_size=${5:-32}
    
    echo "Training ACT model on dataset: $dataset_id"
    echo "Output: $output_dir"
    echo "Steps: $steps"
    echo "Batch size: $batch_size"
    
    python -m lerobot.scripts.train \
        --dataset.repo_id="$dataset_id" \
        --policy.type=act \
        --output_dir="$output_dir" \
        --job_name="$job_name" \
        --policy.device=cuda \
        --wandb.enable=true \
        --policy.repo_id="$dataset_id" \
        --batch_size="$batch_size" \
        --steps="$steps"
}

# Train ACT model - Dataset 2
train_act_dataset2() {
    local dataset_id=${1:-"ases200q2/PandaPickCubeSpacemouseRandom2"}
    local output_dir=${2:-"outputs/train/PandaPickCubeSpacemouseRandom2_ACT_17102025"}
    local job_name=${3:-"PandaPickCubeSpacemouseRandom2_ACT_17102025"}
    local steps=${4:-50000}
    local batch_size=${5:-32}
    
    echo "Training ACT model on dataset: $dataset_id"
    echo "Output: $output_dir"
    echo "Steps: $steps"
    echo "Batch size: $batch_size"
    
    python -m lerobot.scripts.train \
        --dataset.repo_id="$dataset_id" \
        --policy.type=act \
        --output_dir="$output_dir" \
        --job_name="$job_name" \
        --policy.device=cuda \
        --wandb.enable=true \
        --policy.repo_id="$dataset_id" \
        --batch_size="$batch_size" \
        --steps="$steps"
}

# Train any policy with custom parameters
train_custom() {
    if [ $# -lt 3 ]; then
        echo "Usage: train_custom <policy_type> <dataset_id> <output_dir> [steps] [batch_size]"
        echo "Example: train_custom act ases200q2/my_dataset outputs/train/my_model 5000 32"
        return 1
    fi
    
    local policy_type=$1
    local dataset_id=$2
    local output_dir=$3
    local steps=${4:-5000}
    local batch_size=${5:-32}
    local job_name=$(basename "$output_dir")
    
    echo "Training $policy_type model..."
    echo "Dataset: $dataset_id"
    echo "Output: $output_dir"
    echo "Steps: $steps"
    echo "Batch size: $batch_size"
    
    python -m lerobot.scripts.train \
        --dataset.repo_id="$dataset_id" \
        --policy.type="$policy_type" \
        --output_dir="$output_dir" \
        --job_name="$job_name" \
        --policy.device=cuda \
        --wandb.enable=true \
        --policy.repo_id="$dataset_id" \
        --batch_size="$batch_size" \
        --steps="$steps"
}

# =============================================================================
# DATA COLLECTION
# =============================================================================

echo "=== Data Collection Commands ==="

# Collect data with gym manipulator
collect_data_gym() {
    local config_path=${1:-"lerobot-example-config-files/env_config_gym_hil_il.json"}
    echo "Collecting data with gym manipulator..."
    echo "Config: $config_path"
    python -m lerobot.scripts.rl.gym_manipulator --config_path "$config_path"
}

# Collect data with spacemouse random config
collect_data_spacemouse_random() {
    local config_path=${1:-"lerobot-example-config-files/env_config_gym_hil_il_spacemouse_random.json"}
    echo "Collecting data with spacemouse random config..."
    echo "Config: $config_path"
    python -m lerobot.scripts.rl.gym_manipulator --config_path "$config_path"
}

# Collect data with spacemouse no viewer
collect_data_spacemouse_no_viewer() {
    local config_path=${1:-"lerobot-example-config-files/env_config_gym_hil_il_spacemouse_no_viewer.json"}
    echo "Collecting data with spacemouse (no viewer)..."
    echo "Config: $config_path"
    python -m lerobot.scripts.rl.gym_manipulator --config_path "$config_path"
}

# =============================================================================
# UTILITY COMMANDS
# =============================================================================

echo "=== Utility Commands ==="

# Display system information
show_sys_info() {
    echo "Displaying system information..."
    python -m lerobot.scripts.display_sys_info
}

# Find joint limits
find_joint_limits() {
    echo "Finding joint limits..."
    python -m lerobot.scripts.find_joint_limits
}

# Crop dataset ROI
crop_dataset_roi() {
    if [ $# -eq 0 ]; then
        echo "Usage: crop_dataset_roi <input_dataset> <output_dataset>"
        echo "Example: crop_dataset_roi ases200q2/my_dataset ases200q2/my_cropped_dataset"
        return 1
    fi
    local input_dataset=$1
    local output_dataset=$2
    echo "Cropping dataset ROI..."
    echo "Input: $input_dataset"
    echo "Output: $output_dataset"
    python -m lerobot.scripts.rl.crop_dataset_roi \
        --input_dataset "$input_dataset" \
        --output_dataset "$output_dataset"
}

# =============================================================================
# MAIN EXECUTION FUNCTIONS
# =============================================================================

# Function to display available commands
show_help() {
    echo "Available commands:"
    echo ""
    echo "📊 DATASET VISUALIZATION:"
    echo "  visualize_gamepad_dataset    - Visualize gamepad grasp dataset"
    echo "  visualize_dataset <repo_id>  - Visualize any dataset"
    echo ""
    echo " POLICY EVALUATION:"
    echo "  eval_policy_with_config [config] - Evaluate policy with config file"
    echo "  eval_smolvla_model [checkpoint] [device] [episodes] - Evaluate SmolVLA model"
    echo "  eval_act_simulation [checkpoint] [device] [episodes] - Evaluate ACT in simulation"
    echo "  eval_act_model [checkpoint] [device] [episodes] - Evaluate ACT on dataset"
    echo ""
    echo "🚀 MODEL TRAINING:"
    echo "  train_smolvla [dataset] [output] [job] [steps] [batch] [repo_id] - Train SmolVLA model"
    echo "  train_act_dataset1 [dataset] [output] [job] [steps] [batch] - Train ACT on dataset 1"
    echo "  train_act_dataset2 [dataset] [output] [job] [steps] [batch] - Train ACT on dataset 2"
    echo "  train_custom <type> <dataset> <output> [steps] [batch] - Train custom policy"
    echo ""
    echo " DATA COLLECTION:"
    echo "  collect_data_gym [config] - Collect data with gym manipulator"
    echo "  collect_data_spacemouse_random [config] - Collect data with spacemouse"
    echo "  collect_data_spacemouse_no_viewer [config] - Collect data (no viewer)"
    echo ""
    echo " UTILITY:"
    echo "  show_sys_info              - Display system information"
    echo "  find_joint_limits          - Find joint limits"
    echo "  crop_dataset_roi <input> <output> - Crop dataset ROI"
    echo ""
    echo "Usage: $0 <command_name> [parameters...]"
    echo "Example: $0 train_smolvla ases200q2/my_dataset outputs/train/my_model"
    echo ""
    echo " Tips:"
    echo "  - Use quotes for parameters with spaces"
    echo "  - Most commands have sensible defaults"
    echo "  - Check the help for each command for detailed usage"
}

# =============================================================================
# SCRIPT EXECUTION
# =============================================================================

# Check if function name was provided
if [ $# -eq 0 ]; then
    echo "No command specified."
    show_help
    exit 1
fi

# Execute the requested function
FUNCTION_NAME=$1
shift  # Remove the function name from arguments

# Check if function exists
if declare -f "$FUNCTION_NAME" > /dev/null; then
    echo "Executing: $FUNCTION_NAME"
    echo "Parameters: $*"
    echo "=========================================="
    $FUNCTION_NAME "$@"
else
    echo "Error: Function '$FUNCTION_NAME' not found."
    echo ""
    show_help
    exit 1
fi

echo "=========================================="
echo "Command completed: $FUNCTION_NAME" 