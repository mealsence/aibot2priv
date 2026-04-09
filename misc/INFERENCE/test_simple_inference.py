#!/usr/bin/env python3
"""
Simple inference script for trained lerobot policies.

This is the simplest possible way to run inference with a trained policy.
It demonstrates the core inference loop without any extra complexity.

Usage:
    python simple_inference.py
"""

import os
import torch
from lerobot.policies.factory import get_policy_class, make_pre_post_processors
from lerobot.utils.control_utils import predict_action
from lerobot.utils.utils import get_safe_torch_device

# ============================================================================
# CONFIGURATION - Modify these for your setup
# ============================================================================

# Policy path: Can be a HuggingFace Hub model ID or local path
# Examples:
#   - HuggingFace Hub: "username/model_name"
#   - Local path: "/path/to/outputs/train/model_name/checkpoints/last/pretrained_model"
POLICY_PATH = os.environ.get(
    "LEROBOT_POLICY_PATH",
    "ases200q2/Isaac_panda_pick_cube_act_20251116_101319"  # Default example
)

# Policy type: "act", "smolvla", "diffusion", "tdmpc", etc.
POLICY_TYPE = os.environ.get("LEROBOT_POLICY_TYPE", "act")

# Device: "cuda", "cpu", or None for auto-detect
DEVICE = os.environ.get("LEROBOT_DEVICE", None)

# Task description (for VLA policies like smolvla)
TASK_DESCRIPTION = os.environ.get("LEROBOT_TASK", "pick the cube")

# Robot type (if using robot)
ROBOT_TYPE = os.environ.get("LEROBOT_ROBOT_TYPE", None)

# ============================================================================
# SIMPLE INFERENCE FUNCTION
# ============================================================================

def simple_inference(
    policy_path: str,
    policy_type: str = "act",
    device: str | None = None,
    task: str | None = None,
    robot_type: str | None = None,
):
    """
    Simplest possible inference function.
    
    This function:
    1. Loads a pretrained policy
    2. Creates preprocessor and postprocessor
    3. Shows how to run inference on a single observation
    
    Args:
        policy_path: Path to pretrained policy (HuggingFace Hub ID or local path)
        policy_type: Type of policy ("act", "smolvla", etc.)
        device: Device to run on ("cuda", "cpu", or None for auto-detect)
        task: Task description for VLA policies
        robot_type: Robot type identifier
    """
    print("=" * 60)
    print("SIMPLE LEROBOT INFERENCE")
    print("=" * 60)
    print(f"Policy path: {policy_path}")
    print(f"Policy type: {policy_type}")
    
    # Step 1: Get device
    if device is None:
        device = get_safe_torch_device("cuda" if torch.cuda.is_available() else "cpu", log=False)
    else:
        device = get_safe_torch_device(device, log=False)
    print(f"Device: {device}")
    print()
    
    # Step 2: Get policy class and load pretrained policy
    print("Loading policy...")
    policy_class = get_policy_class(policy_type)
    policy = policy_class.from_pretrained(policy_path)
    policy.to(device)
    policy.eval()
    print("✅ Policy loaded")
    
    # Step 3: Create preprocessor and postprocessor
    print("Creating processors...")
    # NOTE: When using pretrained_path, normalization stats should be loaded from the model.
    # However, if the model doesn't have stats saved, you may need to provide dataset_stats:
    #   dataset_stats = LeRobotDatasetMetadata("dataset_id").stats
    #   preprocessor_overrides = {
    #       "device_processor": {"device": str(device)},
    #       "normalizer_processor": {"stats": dataset_stats, ...}
    #   }
    preprocessor, postprocessor = make_pre_post_processors(
        policy_cfg=policy.config,
        pretrained_path=policy_path,
        preprocessor_overrides={"device_processor": {"device": str(device)}},
    )
    print("✅ Processors created")
    print("   Note: Normalization stats are loaded from pretrained model")
    print("   If normalization fails, provide dataset_stats explicitly")
    print()
    
    # Step 4: Reset policy state (important for temporal policies like ACT)
    policy.reset()
    preprocessor.reset()
    postprocessor.reset()
    print("✅ Policy state reset")
    print()
    
    # Step 5: Example inference loop
    # NOTE: This is a minimal example. In practice, you would:
    #   - Get observations from your robot/environment
    #   - Run inference in a loop
    #   - Send actions to your robot/environment
    
    print("=" * 60)
    print("INFERENCE EXAMPLE")
    print("=" * 60)
    print()
    print("To run inference, you need to:")
    print("1. Get an observation (from robot or environment)")
    print("2. Call predict_action() with the observation")
    print("3. Send the action to your robot/environment")
    print()
    print("Example code:")
    print("-" * 60)
    print("""
# Get observation from robot/environment
observation = robot.get_observation()  # or env.get_observation()

# Run inference
action = predict_action(
    observation=observation,
    policy=policy,
    device=device,
    preprocessor=preprocessor,
    postprocessor=postprocessor,
    use_amp=getattr(policy.config, "use_amp", False),
    task=task,
    robot_type=robot_type,
)

# Send action to robot/environment
robot.send_action(action)  # or env.step(action)
""")
    print("-" * 60)
    print()
    
    # Return loaded components for use
    return {
        "policy": policy,
        "preprocessor": preprocessor,
        "postprocessor": postprocessor,
        "device": device,
    }


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Run simple inference
    components = simple_inference(
        policy_path=POLICY_PATH,
        policy_type=POLICY_TYPE,
        device=DEVICE,
        task=TASK_DESCRIPTION,
        robot_type=ROBOT_TYPE,
    )
    
    print("=" * 60)
    print("✅ Inference setup complete!")
    print("=" * 60)
    print()
    print("You can now use the loaded components:")
    print(f"  - policy: {type(components['policy']).__name__}")
    print(f"  - preprocessor: {type(components['preprocessor']).__name__}")
    print(f"  - postprocessor: {type(components['postprocessor']).__name__}")
    print(f"  - device: {components['device']}")
    print()
    print("For a complete example with robot integration, see:")
    print("  - robot_tools.py (execute_vla_task function)")
    print("  - test_vla_execution.py (full test script)")
    print("  - lerobot/examples/tutorial/act/act_using_example.py")

