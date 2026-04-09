#!/usr/bin/env python3
"""
Complete inference example with robot integration.

This script shows the full inference loop:
1. Load policy
2. Connect to robot
3. Run inference loop (get observation -> predict action -> send action)
4. Clean up

Usage:
    python simple_inference_with_robot.py
"""

import os
import time
import torch
from lerobot.policies.factory import get_policy_class, make_pre_post_processors
from lerobot.policies.utils import build_inference_frame, make_robot_action
from lerobot.datasets.utils import hw_to_dataset_features
from lerobot.utils.utils import get_safe_torch_device

# Try to import robot utilities (may not be available in all environments)
try:
    from lerobot.robots.utils import make_robot_from_config
    from lerobot_robot_ros import (
        PandaROSPositionConfig,
        PandaROSConfig,
    )
    ROBOT_AVAILABLE = True
except ImportError:
    ROBOT_AVAILABLE = False
    print("⚠️  Robot imports not available. This script requires lerobot-robot-ros.")

# ============================================================================
# CONFIGURATION
# ============================================================================

POLICY_PATH = os.environ.get(
    "LEROBOT_POLICY_PATH",
    "ases200q2/Isaac_panda_pick_cube_act_20251116_101319"
)
POLICY_TYPE = os.environ.get("LEROBOT_POLICY_TYPE", "act")
# Supported policy types: "act", "smolvla", "diffusion", "tdmpc", "vqbet", "pi0", "pi05", "groot"
# Note: VLA policies (smolvla, pi0, pi05) require a task description

DEVICE = os.environ.get("LEROBOT_DEVICE", None)
TASK_DESCRIPTION = os.environ.get("LEROBOT_TASK", "pick the cube")
# Task description is required for VLA policies (smolvla, pi0, pi05)
# For non-VLA policies (act, diffusion, tdmpc), this can be empty or None

ROBOT_TYPE = os.environ.get("LEROBOT_ROBOT_TYPE", "panda_ros_position")
ROBOT_ID = os.environ.get("LEROBOT_ROBOT_ID", "my_panda_follower")

# Optional: Dataset ID for loading normalization stats
# If provided, will load dataset metadata and use its stats for normalization
# This ensures correct normalization even if pretrained model stats are missing
DATASET_ID = os.environ.get("LEROBOT_DATASET_ID", None)

# Inference loop parameters
FPS = int(os.environ.get("LEROBOT_FPS", "30"))  # Control frequency (must match training!)
NUM_STEPS = int(os.environ.get("LEROBOT_NUM_STEPS", "1000"))  # Number of timesteps to run


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def load_policy(
    policy_path: str,
    policy_type: str,
    device: torch.device,
    dataset_stats: dict[str, dict[str, torch.Tensor]] | None = None,
):
    """
    Load pretrained policy and processors.
    
    Args:
        policy_path: Path to pretrained policy
        policy_type: Type of policy ("act", "smolvla", etc.)
        device: Device to run on
        dataset_stats: Optional dataset statistics for normalization.
                     If provided, will override stats from pretrained model.
                     If None, will use stats saved in pretrained model (if available).
    
    Note:
        Normalization stats are critical for correct inference. The pretrained model
        should have stats saved, but you can override them by providing dataset_stats.
        This is useful if:
        - The pretrained model doesn't have stats saved
        - You want to use different normalization stats
        - You have access to the original dataset metadata
    """
    print(f"Loading policy: {policy_path} ({policy_type})...")
    
    # Get policy class
    policy_class = get_policy_class(policy_type)
    
    # Load pretrained policy
    policy = policy_class.from_pretrained(policy_path)
    policy.to(device)
    policy.eval()
    
    # Prepare processor overrides
    preprocessor_overrides = {"device_processor": {"device": str(device)}}
    postprocessor_overrides = {}
    
    # If dataset_stats provided, override normalization stats
    # This ensures correct normalization even if pretrained model stats are missing/incomplete
    if dataset_stats is not None:
        print("  Using provided dataset_stats for normalization")
        preprocessor_overrides["normalizer_processor"] = {
            "stats": dataset_stats,
            "features": {**policy.config.input_features, **policy.config.output_features},
            "norm_map": policy.config.normalization_mapping,
        }
        postprocessor_overrides["unnormalizer_processor"] = {
            "stats": dataset_stats,
            "features": policy.config.output_features,
            "norm_map": policy.config.normalization_mapping,
        }
    else:
        print("  Using normalization stats from pretrained model (if available)")
        print("  Note: If normalization fails, provide dataset_stats explicitly")
    
    # Create processors
    # When pretrained_path is provided, processors are loaded from the model
    # If dataset_stats is provided via overrides, they take precedence over saved stats
    processor_kwargs = {
        "preprocessor_overrides": preprocessor_overrides,
    }
    if postprocessor_overrides:
        processor_kwargs["postprocessor_overrides"] = postprocessor_overrides
    
    preprocessor, postprocessor = make_pre_post_processors(
        policy_cfg=policy.config,
        pretrained_path=policy_path,
        **processor_kwargs,
    )
    
    # Reset state (important for temporal policies)
    policy.reset()
    preprocessor.reset()
    postprocessor.reset()
    
    print("✅ Policy loaded and ready")
    return policy, preprocessor, postprocessor


def setup_robot(robot_type: str, robot_id: str):
    """Set up and connect to robot."""
    if not ROBOT_AVAILABLE:
        raise RuntimeError("Robot utilities not available")
    
    print(f"Setting up robot: {robot_type} (id: {robot_id})...")
    
    # Create robot config
    if robot_type in ("panda_ros_position", "panda_ros_isaac_fast"):
        robot_cfg = PandaROSPositionConfig(id=robot_id)
    elif robot_type in ("panda_ros", "panda_ros_isaac"):
        robot_cfg = PandaROSConfig(id=robot_id)
    else:
        raise ValueError(f"Unsupported robot type: {robot_type}")
    
    # Create and connect robot
    robot = make_robot_from_config(robot_cfg)
    if not robot.is_connected:
        robot.connect()
    
    print("✅ Robot connected")
    return robot


def get_dataset_features(robot):
    """
    Convert robot features to dataset features format.
    
    This is needed for build_inference_frame() and make_robot_action().
    """
    action_features = hw_to_dataset_features(robot.action_features, "action")
    obs_features = hw_to_dataset_features(robot.observation_features, "observation")
    dataset_features = {**action_features, **obs_features}
    return dataset_features


def busy_wait(duration: float):
    """Busy wait for precise timing."""
    if duration <= 0:
        return
    start = time.perf_counter()
    while time.perf_counter() - start < duration:
        pass


# ============================================================================
# MAIN INFERENCE LOOP
# ============================================================================

def run_inference_loop(
    policy,
    preprocessor,
    postprocessor,
    device: torch.device,
    robot,
    task: str | None,
    robot_type: str | None,
    num_steps: int,
    fps: int,
    dataset_features: dict,
):
    """
    Run the main inference loop.
    
    This function works with all lerobot policy types:
    - ACT, Diffusion, TDMPC, VQBeT: task can be None or empty
    - SmolVLA, PI0, PI05 (VLA policies): task description is required
    - Groot: task and robot_type may be required depending on training
    
    All policies use the same inference pattern:
    1. Get observation from robot
    2. Build inference frame (converts to dataset format)
    3. Preprocess observation
    4. Run policy.select_action()
    5. Postprocess action
    6. Convert to robot format
    7. Send to robot
    """
    print("=" * 60)
    print("STARTING INFERENCE LOOP")
    print("=" * 60)
    print(f"Steps: {num_steps}")
    print(f"FPS: {fps} Hz")
    print(f"Expected duration: {num_steps / fps:.1f} seconds")
    if task:
        print(f"Task: {task}")
    if robot_type:
        print(f"Robot type: {robot_type}")
    print()
    
    successful_steps = 0
    
    for step in range(num_steps):
        try:
            loop_start = time.perf_counter()
            
            # 1. Get observation from robot
            obs = robot.get_observation()
            
            # 2. Build inference frame (converts robot obs to dataset format and prepares for inference)
            obs_frame = build_inference_frame(
                observation=obs,
                ds_features=dataset_features,
                device=device,
                task=task,
                robot_type=robot_type,
            )
            
            # 3. Preprocess observation
            obs_processed = preprocessor(obs_frame)
            
            # 4. Run inference
            action_tensor = policy.select_action(obs_processed)
            
            # 5. Postprocess action
            action_tensor = postprocessor(action_tensor)
            
            # 6. Convert action to robot format
            action = make_robot_action(action_tensor, dataset_features)
            
            # 7. Send action to robot
            robot.send_action(action)
            
            successful_steps += 1
            
            # Progress update: print every second (fps steps = 1 second)
            # This gives a nice once-per-second update regardless of FPS
            if (step + 1) % fps == 0:
                elapsed = (step + 1) / fps
                print(f"  ✓ Step {step + 1}/{num_steps} ({elapsed:.1f}s)")
            
            # Maintain target FPS
            dt = time.perf_counter() - loop_start
            busy_wait(1.0 / fps - dt)
            
        except Exception as e:
            print(f"  ⚠️  Error at step {step + 1}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print()
    print(f"✅ Completed {successful_steps}/{num_steps} steps")
    print(f"   Duration: {successful_steps / fps:.1f} seconds")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main function."""
    print("=" * 60)
    print("SIMPLE INFERENCE WITH ROBOT")
    print("=" * 60)
    print()
    
    if not ROBOT_AVAILABLE:
        print("❌ Robot utilities not available.")
        print("   Please install lerobot-robot-ros or use simple_inference.py")
        return
    
    # Get device
    if DEVICE is None:
        device = get_safe_torch_device("cuda" if torch.cuda.is_available() else "cpu", log=False)
    else:
        device = get_safe_torch_device(DEVICE, log=False)
    
    print(f"Device: {device}")
    print()
    
    # Optionally load dataset stats for normalization
    dataset_stats = None
    if DATASET_ID:
        try:
            from lerobot.datasets.lerobot_dataset import LeRobotDatasetMetadata
            print(f"Loading dataset metadata: {DATASET_ID}...")
            dataset_metadata = LeRobotDatasetMetadata(DATASET_ID)
            dataset_stats = dataset_metadata.stats
            print("✅ Dataset stats loaded")
        except Exception as e:
            print(f"⚠️  Warning: Could not load dataset metadata: {e}")
            print("   Continuing without dataset stats (will use pretrained model stats)")
    print()
    
    # Load policy
    policy, preprocessor, postprocessor = load_policy(
        POLICY_PATH, POLICY_TYPE, device, dataset_stats=dataset_stats
    )
    print()
    
    # Setup robot
    robot = setup_robot(ROBOT_TYPE, ROBOT_ID)
    print()
    
    # Get dataset features (needed for build_inference_frame and make_robot_action)
    print("Converting robot features to dataset format...")
    dataset_features = get_dataset_features(robot)
    print("✅ Dataset features ready")
    print()
    
    # Run inference loop
    try:
        run_inference_loop(
            policy=policy,
            preprocessor=preprocessor,
            postprocessor=postprocessor,
            device=device,
            robot=robot,
            task=TASK_DESCRIPTION,
            robot_type=ROBOT_TYPE,
            num_steps=NUM_STEPS,
            fps=FPS,
            dataset_features=dataset_features,
        )
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n✅ Cleanup complete")


if __name__ == "__main__":
    main()

