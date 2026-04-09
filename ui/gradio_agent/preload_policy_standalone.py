#!/usr/bin/env python3
"""
Standalone script to pre-load VLA policy.

This can be run independently or imported and called from any script.
Useful for warming up the policy cache before starting your main application.

Usage:
    python preload_policy_standalone.py

Automatically reads configuration from:
    1. policy_config.yaml (if exists)
    2. Environment variables (LEROBOT_*)
    3. Default values
"""

import sys
import os

# Add parent directory to path if needed
sys.path.insert(0, os.path.dirname(__file__))

from robot_tools import preload_vla_policy


def main():
    """Pre-load the VLA policy."""
    print("=" * 60)
    print("VLA Policy Pre-loader")
    print("=" * 60)
    print()

    # Pre-load the policy (automatically uses policy_config.yaml)
    print("🚀 Pre-loading policy...")
    print()

    success = preload_vla_policy()

    print()
    print("=" * 60)
    if success:
        print("✅ Policy pre-loaded successfully!")
        print("   The policy is now cached and ready for use.")
        print()
        print("💡 You can now run:")
        print("   python gradio_agent/demo_tool_calling.py")
    else:
        print("❌ Policy pre-loading failed")
        print("   Check the error messages above for details.")
    print("=" * 60)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
