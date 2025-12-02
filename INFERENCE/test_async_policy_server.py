#!/usr/bin/env python3
"""
Simple test script for Policy Server in async inference.

This script starts a policy server that listens for connections from robot clients.
The server will load the policy specified by the client during the initial handshake.

Usage:
    # Terminal 1: Start the policy server
    python test_async_policy_server.py

    # Terminal 2: Start the robot client (see test_async_robot_client.py)
"""

import os
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

from lerobot.async_inference.configs import PolicyServerConfig
from lerobot.async_inference.policy_server import serve

# Configuration
HOST = "127.0.0.1"  # Use "0.0.0.0" to accept connections from any IP
PORT = 8080

if __name__ == "__main__":
    print(f"Starting Policy Server on {HOST}:{PORT}")
    print("Waiting for robot client to connect...")
    print("Press Ctrl+C to stop the server")
    
    config = PolicyServerConfig(
        host=HOST,
        port=PORT,
    )
    
    try:
        serve(config)
    except KeyboardInterrupt:
        print("\nPolicy Server stopped.")

