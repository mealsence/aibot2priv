#!/usr/bin/env python3
"""
Simple test script for Robot Client in async inference.

This script connects to a policy server and runs inference with your trained policy.

Before running:
1. Make sure the policy server is running (see test_async_policy_server.py)
2. Update the configuration below with your:
   - Policy path (local checkpoint or HuggingFace Hub model)
   - Server address

Usage:
    # Terminal 1: Start the policy server
    python test_async_policy_server.py
    
    # Terminal 2: Start the robot client
    python test_async_robot_client.py
"""

import os
import sys
import threading
from pathlib import Path

# Environment activation (same as record_spacemouse_ee_fast.sh)
def activate_python_env():
    """Activate conda or venv environment if available."""
    project_root = Path(__file__).parent
    
    # Check if already in an environment
    if os.environ.get("CONDA_PREFIX") or os.environ.get("VIRTUAL_ENV"):
        return
    
    # Try conda
    if os.system("command -v conda >/dev/null 2>&1") == 0:
        import subprocess
        try:
            conda_base = subprocess.check_output(["conda", "info", "--base"], text=True).strip()
            conda_sh = Path(conda_base) / "etc" / "profile.d" / "conda.sh"
            if conda_sh.exists():
                # Try common environment names
                for env_name in ["lerobot-ros-isaac", "lerobot-ros"]:
                    result = subprocess.run(
                        ["conda", "env", "list"],
                        capture_output=True,
                        text=True
                    )
                    if env_name in result.stdout:
                        os.system(f'eval "$(conda shell.bash hook)" && conda activate {env_name}')
                        print(f"Activated conda environment: {env_name}")
                        return
        except Exception:
            pass
    
    # Try venv
    venv_activate = project_root / ".venv" / "bin" / "activate"
    if venv_activate.exists():
        print(f"Using virtual environment at {venv_activate.parent}")
        # Note: venv activation in Python script requires exec or subprocess
        # For now, just warn if not already activated
        if not os.environ.get("VIRTUAL_ENV"):
            print("Warning: Virtual environment found but not activated. Please activate manually or use conda.")

activate_python_env()

from lerobot.async_inference.configs import RobotClientConfig
from lerobot.async_inference.helpers import visualize_action_queue_size
from lerobot.async_inference.robot_client import RobotClient

# ============================================================================
# CONFIGURATION - UPDATE THESE VALUES FOR YOUR SETUP
# ============================================================================

# Policy Configuration
POLICY_TYPE = "act"  # Options: "act", "smolvla", "diffusion", "tdmpc", "vqbet", "pi0", "pi05"

# Path to your trained policy - can be:
# 1. Local path: "/path/to/outputs/train/model_name/checkpoints/last/pretrained_model"
# 2. HuggingFace Hub: "username/model_name"
# Example for HuggingFace Hub: "ases200q2/Isaac_panda_pick_cube_act_20251116_101319"
# Example for local: "outputs/train/Isaac_panda_pick_cube_act_20251116_101319/checkpoints/last/pretrained_model"
PRETRAINED_NAME_OR_PATH = os.environ.get(
    "LEROBOT_POLICY_PATH",
    "ases200q2/Isaac_panda_pick_cube_act_20251116_101319"
)

POLICY_DEVICE = "cuda"  # Options: "cuda", "cpu", "mps" (for Mac)

# Server Configuration
SERVER_ADDRESS = "127.0.0.1:8080"  # Address of the policy server

# Robot Configuration (matching record_spacemouse_ee_fast.sh)
# Using panda_ros_position for ultra-low latency direct position control
ROBOT_TYPE = os.environ.get("LEROBOT_ROBOT_TYPE", "panda_ros_position")
ROBOT_ID = os.environ.get("LEROBOT_ROBOT_ID", "my_panda_follower")

# Camera configuration is automatically handled by PandaROSPositionConfig
# Camera settings can be customized via environment variables:
# - LEROBOT_CAMERA_TOPIC (default: /rgb/camera_1)
# - LEROBOT_CAMERA_WIDTH (default: 640)
# - LEROBOT_CAMERA_HEIGHT (default: 480)
# - LEROBOT_CAMERA_FPS (default: 30)

# Async Inference Parameters
ACTIONS_PER_CHUNK = 50  # Number of actions to output at once (should be less than policy max)
CHUNK_SIZE_THRESHOLD = 0.5  # Threshold (0-1) for when to request new actions
# Lower values = more frequent updates, higher values = less frequent updates

# Task description (for policies that support it, like SmolVLA)
TASK = ""  # e.g., "Pick up the cube" or leave empty for ACT policies

# ============================================================================
# ROBOT CONFIGURATION SETUP
# ============================================================================

# Import the appropriate robot config based on robot type
if ROBOT_TYPE in ("panda_ros_position", "panda_ros_isaac_fast"):
    from lerobot_robot_ros import PandaROSPositionConfig
    # PandaROSPositionConfig automatically handles camera configuration from environment variables
    robot_cfg = PandaROSPositionConfig(id=ROBOT_ID)
elif ROBOT_TYPE in ("panda_ros", "panda_ros_isaac"):
    from lerobot_robot_ros import PandaROSConfig
    robot_cfg = PandaROSConfig(id=ROBOT_ID)
elif ROBOT_TYPE == "so100_follower":
    from lerobot.robots.so100_follower import SO100FollowerConfig
    ROBOT_PORT = os.environ.get("LEROBOT_ROBOT_PORT", "/dev/tty.usbmodem58760431631")
    from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
    CAMERAS = {
        "up": OpenCVCameraConfig(index_or_path=0, width=640, height=480, fps=30),
        "side": OpenCVCameraConfig(index_or_path=1, width=640, height=480, fps=30),
    }
    robot_cfg = SO100FollowerConfig(port=ROBOT_PORT, id=ROBOT_ID, cameras=CAMERAS)
elif ROBOT_TYPE == "so101_follower":
    from lerobot.robots.so101_follower import SO101FollowerConfig
    ROBOT_PORT = os.environ.get("LEROBOT_ROBOT_PORT", "/dev/tty.usbmodem58760431631")
    from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
    CAMERAS = {
        "up": OpenCVCameraConfig(index_or_path=0, width=640, height=480, fps=30),
        "side": OpenCVCameraConfig(index_or_path=1, width=640, height=480, fps=30),
    }
    robot_cfg = SO101FollowerConfig(port=ROBOT_PORT, id=ROBOT_ID, cameras=CAMERAS)
elif ROBOT_TYPE == "bi_so100_follower":
    from lerobot.robots.bi_so100_follower import BiSO100FollowerConfig
    LEFT_ARM_PORT = os.environ.get("LEROBOT_LEFT_ARM_PORT", "/dev/tty.usbmodem58760431631")
    RIGHT_ARM_PORT = os.environ.get("LEROBOT_RIGHT_ARM_PORT", "/dev/tty.usbmodem58760431632")
    from lerobot.cameras.opencv.configuration_opencv import OpenCVCameraConfig
    CAMERAS = {
        "up": OpenCVCameraConfig(index_or_path=0, width=640, height=480, fps=30),
        "side": OpenCVCameraConfig(index_or_path=1, width=640, height=480, fps=30),
    }
    robot_cfg = BiSO100FollowerConfig(
        left_arm_port=LEFT_ARM_PORT,
        right_arm_port=RIGHT_ARM_PORT,
        id=ROBOT_ID,
        cameras=CAMERAS
    )
else:
    raise ValueError(
        f"Unsupported robot type: {ROBOT_TYPE}. "
        f"Supported: panda_ros_position, panda_ros, "
        f"so100_follower, so101_follower, bi_so100_follower"
    )

# ============================================================================
# CLIENT CONFIGURATION
# ============================================================================

client_cfg = RobotClientConfig(
    robot=robot_cfg,
    server_address=SERVER_ADDRESS,
    policy_device=POLICY_DEVICE,
    policy_type=POLICY_TYPE,
    pretrained_name_or_path=PRETRAINED_NAME_OR_PATH,
    chunk_size_threshold=CHUNK_SIZE_THRESHOLD,
    actions_per_chunk=ACTIONS_PER_CHUNK,
    task=TASK,
)

# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Robot Client Configuration")
    print("=" * 60)
    print(f"Policy Type: {POLICY_TYPE}")
    print(f"Policy Path: {PRETRAINED_NAME_OR_PATH}")
    print(f"Policy Device: {POLICY_DEVICE}")
    print(f"Server Address: {SERVER_ADDRESS}")
    print(f"Robot Type: {ROBOT_TYPE}")
    print(f"Actions per Chunk: {ACTIONS_PER_CHUNK}")
    print(f"Chunk Size Threshold: {CHUNK_SIZE_THRESHOLD}")
    print("=" * 60)
    print()
    
    # Check if policy path exists (for local paths)
    if Path(PRETRAINED_NAME_OR_PATH).exists():
        print(f"✓ Found local policy at: {PRETRAINED_NAME_OR_PATH}")
    else:
        print(f"⚠ Policy path not found locally: {PRETRAINED_NAME_OR_PATH}")
        print("  Will try to load from HuggingFace Hub if it's a Hub model name")
    print()
    
    # Create and start client
    client = RobotClient(client_cfg)
    
    if client.start():
        print("✓ Successfully connected to policy server!")
        print("Starting action receiver thread...")
        
        # Start action receiver thread
        action_receiver_thread = threading.Thread(target=client.receive_actions, daemon=True)
        action_receiver_thread.start()
        
        try:
            print("Starting control loop...")
            print("Press Ctrl+C to stop")
            print()
            
            # Run the control loop
            client.control_loop(TASK)
            
        except KeyboardInterrupt:
            print("\nStopping robot client...")
            client.stop()
            action_receiver_thread.join()
            
            # Optionally visualize the action queue size
            print("\nAction queue size over time:")
            visualize_action_queue_size(client.action_queue_size)
            
            print("\nRobot client stopped.")
    else:
        print("✗ Failed to connect to policy server!")
        print(f"  Make sure the server is running at {SERVER_ADDRESS}")

