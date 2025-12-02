---
noteId: "bc40fae0cf6f11f0980e61b07d63b8fd"
tags: []

---

# LeRobot ROS Agent - UV Installation Guide

This guide explains how to install `lerobot-ros-agent` using **[uv](https://docs.astral.sh/uv/)**, a fast Python package manager written in Rust.

## Why uv?

| Feature | uv | pip/conda |
|---------|-----|-----------|
| Speed | ⚡ 10-100x faster | Standard |
| Lockfiles | ✅ Built-in | ❌ Requires extra tools |
| Venv Management | ✅ Integrated | Manual |
| Disk Space | 🔽 Efficient caching | Larger footprint |
| ROS2 Compatible | ✅ Yes | ✅ Yes |

## Prerequisites

Before installing, ensure you have:

- **Ubuntu 22.04** (recommended) or compatible Linux distribution
- **Python 3.10 or 3.11** (not 3.12+ yet)
- **ROS2 Humble** installed (for robot control features)
- **NVIDIA GPU** with CUDA 12.x drivers (for GPU acceleration)

### Check Prerequisites

```bash
# Check Python version
python3 --version  # Should be 3.10.x or 3.11.x

# Check ROS2
source /opt/ros/humble/setup.bash
ros2 --version

# Check NVIDIA driver
nvidia-smi
```

## Quick Installation

### Option 1: Automated Setup (Recommended)

```bash
# Clone the repository
git clone --recursive https://github.com/your-username/lerobot-ros-agent.git
cd lerobot-ros-agent

# Run the installation script
./INSTALL/setup_with_uv.sh --cuda128
```

### Option 2: Manual Installation

If you prefer manual control over each step:

```bash
# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc  # or restart terminal

# 2. Clone repository
git clone --recursive https://github.com/your-username/lerobot-ros-agent.git
cd lerobot-ros-agent

# 3. Create virtual environment
uv venv .venv --python python3.10

# 4. Activate environment
source .venv/bin/activate

# 5. Install PyTorch with CUDA 12.8
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

# 6. Install project dependencies
uv pip install -e .

# 7. Install local packages
uv pip install -e ./lerobot --no-deps
uv pip install -e ./lerobot_robot_ros --no-deps
uv pip install -e ./lerobot_teleoperator_devices --no-deps
```

## Installation Options

The setup script supports several options:

```bash
# For RTX 40/50 series (CUDA 12.8)
./INSTALL/setup_with_uv.sh --cuda128

# For RTX 30 series (CUDA 12.4)
./INSTALL/setup_with_uv.sh --cuda124

# CPU only (no GPU)
./INSTALL/setup_with_uv.sh --cpu

# Include development dependencies
./INSTALL/setup_with_uv.sh --cuda128 --dev

# Skip ROS2 environment check
./INSTALL/setup_with_uv.sh --cuda128 --no-ros
```

## Environment Activation

After installation, activate the environment using the generated script:

```bash
# This sources ROS2, local workspace, and Python venv
source activate_env.sh
```

Or manually:

```bash
# Source ROS2 Humble
source /opt/ros/humble/setup.bash

# Source local ROS2 workspace (if built)
source isaac_franka_moveit_perception/install/setup.bash

# Activate Python environment
source .venv/bin/activate
```

## Directory Structure

After installation, your project will have:

```
lerobot-ros-agent/
├── .venv/                          # Python virtual environment
├── activate_env.sh                 # Combined activation script
├── pyproject.toml                  # Project dependencies
├── lerobot/                        # LeRobot submodule
├── lerobot_robot_ros/              # ROS2 robot wrapper
├── lerobot_teleoperator_devices/   # Teleoperator devices
├── gradio_agent/                   # Gradio demo application
└── isaac_franka_moveit_perception/ # ROS2 packages
```

## Verify Installation

After activation, verify the installation:

```bash
# Check Python packages
python -c "import torch; print(f'PyTorch: {torch.__version__}')"
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}')"
python -c "import lerobot; print(f'LeRobot: {lerobot.__version__}')"
python -c "from lerobot_robot_ros import PandaROSPositionConfig; print('lerobot_robot_ros: OK')"

# Run a quick test
python -c "
import torch
x = torch.randn(100, 100).cuda()
print('GPU test: PASSED')
"
```

## Running the Gradio Agent

Once installed, run the main application:

```bash
# Activate environment
source activate_env.sh

# Run with policy preloading
python gradio_agent/demo_tool_calling.py --preload-policy
```

## Troubleshooting

### Issue: NumPy 2.x compatibility with cv_bridge

```bash
# Ensure NumPy < 2.0 is installed
uv pip install "numpy<2.0.0"
```

### Issue: PyTorch not detecting CUDA

```bash
# Check NVIDIA driver
nvidia-smi

# Reinstall PyTorch
uv pip uninstall torch torchvision torchaudio -y
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
```

### Issue: lerobot import fails

```bash
# Reinstall lerobot
cd lerobot
git pull origin main
cd ..
uv pip install -e ./lerobot --no-deps
```

### Issue: ROS2 packages not found

```bash
# Make sure to source ROS2 before running
source /opt/ros/humble/setup.bash
source isaac_franka_moveit_perception/install/setup.bash
```

### Issue: uv command not found

```bash
# Add uv to PATH
export PATH="$HOME/.local/bin:$PATH"

# Or reinstall
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Updating Dependencies

To update packages:

```bash
# Update all packages
uv pip install --upgrade -e .

# Update specific package
uv pip install --upgrade torch

# Regenerate lockfile (if using)
uv pip compile pyproject.toml -o requirements.lock
```

## Comparison with Conda Installation

| Aspect | uv Installation | Conda Installation |
|--------|-----------------|-------------------|
| Install Time | ~2-5 minutes | ~10-20 minutes |
| Disk Space | ~5-8 GB | ~10-15 GB |
| ROS2 Compat | ✅ Native | ✅ With setup |
| Reproducibility | ✅ Lockfiles | ⚠️ Manual |
| Isolation | Virtual env | Conda env |

## Additional Resources

- [uv Documentation](https://docs.astral.sh/uv/)
- [LeRobot GitHub](https://github.com/huggingface/lerobot)
- [ROS2 Humble Docs](https://docs.ros.org/en/humble/)
- [PyTorch Installation](https://pytorch.org/get-started/locally/)

## Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review the [GitHub Issues](https://github.com/your-username/lerobot-ros-agent/issues)
3. Ensure all prerequisites are met
4. Try the conda-based installation as an alternative: `INSTALL/setup_lerobot_rtx5090_venv.sh`

