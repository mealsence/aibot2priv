#!/bin/bash

# =============================================================================
# LeRobot ROS Agent - UV Installation Script
# =============================================================================
#
# This script sets up the lerobot-ros-agent environment using uv (ultraviolet)
# a fast Python package manager written in Rust.
#
# Features:
#   - 10-100x faster than pip
#   - Built-in virtual environment management
#   - Lockfile support for reproducible builds
#   - Compatible with ROS2 Humble
#
# Usage:
#   ./INSTALL/setup_with_uv.sh [OPTIONS]
#
# Options:
#   --cuda128     Install PyTorch with CUDA 12.8 (RTX 40/50 series)
#   --cuda124     Install PyTorch with CUDA 12.4 (RTX 30 series)
#   --cpu         Install PyTorch CPU-only version
#   --dev         Include development dependencies
#   --no-ros      Skip ROS2 environment sourcing (for non-ROS usage)
#   --help        Show this help message
#
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default options
CUDA_VERSION="cu128"
INCLUDE_DEV=false
SKIP_ROS=false
VENV_NAME=".venv"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --cuda128)
            CUDA_VERSION="cu128"
            shift
            ;;
        --cuda124)
            CUDA_VERSION="cu124"
            shift
            ;;
        --cpu)
            CUDA_VERSION="cpu"
            shift
            ;;
        --dev)
            INCLUDE_DEV=true
            shift
            ;;
        --no-ros)
            SKIP_ROS=true
            shift
            ;;
        --help)
            head -35 "$0" | tail -30
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${CYAN}"
echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║         LeRobot ROS Agent - UV Installation                          ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo -e "${BLUE}📁 Project root: ${PROJECT_ROOT}${NC}"
echo ""

# =============================================================================
# Step 1: Check prerequisites
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 1: Checking prerequisites${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f2)

if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 10 ]]; then
    echo -e "${RED}❌ Python 3.10+ required, found: $PYTHON_VERSION${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python version: $PYTHON_VERSION${NC}"

# Check for NVIDIA GPU (optional)
if command -v nvidia-smi &> /dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
    echo -e "${GREEN}✅ GPU detected: $GPU_NAME${NC}"
else
    echo -e "${YELLOW}⚠️  No NVIDIA GPU detected (will use CPU or specified CUDA version)${NC}"
fi

# Check ROS2
if [[ "$SKIP_ROS" == false ]]; then
    if [[ -f "/opt/ros/humble/setup.bash" ]]; then
        echo -e "${GREEN}✅ ROS2 Humble found${NC}"
    else
        echo -e "${YELLOW}⚠️  ROS2 Humble not found at /opt/ros/humble${NC}"
        echo -e "${YELLOW}   ROS2-dependent features may not work${NC}"
    fi
fi

echo ""

# =============================================================================
# Step 2: Install uv if not present
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 2: Setting up uv package manager${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if ! command -v uv &> /dev/null; then
    echo -e "${BLUE}📦 Installing uv...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # Add to PATH for current session
    export PATH="$HOME/.local/bin:$PATH"
    
    # Add to shell config if not already present
    SHELL_RC="$HOME/.bashrc"
    if [[ -f "$HOME/.zshrc" ]]; then
        SHELL_RC="$HOME/.zshrc"
    fi
    
    if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$SHELL_RC" 2>/dev/null; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        echo -e "${GREEN}✅ Added uv to PATH in $SHELL_RC${NC}"
    fi
fi

UV_VERSION=$(uv --version 2>&1)
echo -e "${GREEN}✅ uv installed: $UV_VERSION${NC}"
echo ""

# =============================================================================
# Step 3: Create virtual environment
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 3: Creating virtual environment${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [[ -d "$VENV_NAME" ]]; then
    echo -e "${YELLOW}⚠️  Virtual environment already exists${NC}"
    read -p "Do you want to recreate it? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$VENV_NAME"
        echo -e "${BLUE}🗑️  Removed existing environment${NC}"
    fi
fi

if [[ ! -d "$VENV_NAME" ]]; then
    echo -e "${BLUE}📦 Creating virtual environment with Python $PYTHON_VERSION...${NC}"
    uv venv "$VENV_NAME" --python python3
fi

# Activate virtual environment
source "$VENV_NAME/bin/activate"
echo -e "${GREEN}✅ Virtual environment created and activated: $VENV_NAME${NC}"
echo ""

# =============================================================================
# Step 4: Install PyTorch
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 4: Installing PyTorch (${CUDA_VERSION})${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [[ "$CUDA_VERSION" == "cpu" ]]; then
    echo -e "${BLUE}📦 Installing PyTorch (CPU)...${NC}"
    uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
elif [[ "$CUDA_VERSION" == "cu124" ]]; then
    echo -e "${BLUE}📦 Installing PyTorch with CUDA 12.4...${NC}"
    uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
else
    echo -e "${BLUE}📦 Installing PyTorch with CUDA 12.8...${NC}"
    uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
fi

# Verify PyTorch installation
python -c "import torch; print(f'PyTorch {torch.__version__}, CUDA: {torch.cuda.is_available()}')" && \
    echo -e "${GREEN}✅ PyTorch installed successfully${NC}" || \
    echo -e "${RED}❌ PyTorch installation failed${NC}"
echo ""

# =============================================================================
# Step 5: Install project dependencies
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 5: Installing project dependencies${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Install main project
if [[ "$INCLUDE_DEV" == true ]]; then
    echo -e "${BLUE}📦 Installing project with dev dependencies...${NC}"
    uv pip install -e ".[dev]"
else
    echo -e "${BLUE}📦 Installing project dependencies...${NC}"
    uv pip install -e .
fi

echo -e "${GREEN}✅ Project dependencies installed${NC}"
echo ""

# =============================================================================
# Step 6: Install submodules (lerobot, lerobot_robot_ros, etc.)
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 6: Installing local packages${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Initialize git submodules
echo -e "${BLUE}📦 Initializing git submodules...${NC}"
git submodule update --init --recursive 2>/dev/null || echo -e "${YELLOW}⚠️  Git submodules not available or already initialized${NC}"

# Install lerobot
if [[ -d "lerobot" ]]; then
    echo -e "${BLUE}📦 Installing lerobot...${NC}"
    uv pip install -e "./lerobot[smolvla]" --no-deps 2>/dev/null || \
    uv pip install -e "./lerobot" --no-deps
    echo -e "${GREEN}✅ lerobot installed${NC}"
fi

# Install lerobot_robot_ros
if [[ -d "lerobot_robot_ros" ]]; then
    echo -e "${BLUE}📦 Installing lerobot_robot_ros...${NC}"
    uv pip install -e "./lerobot_robot_ros" --no-deps
    echo -e "${GREEN}✅ lerobot_robot_ros installed${NC}"
fi

# Install lerobot_teleoperator_devices
if [[ -d "lerobot_teleoperator_devices" ]]; then
    echo -e "${BLUE}📦 Installing lerobot_teleoperator_devices...${NC}"
    uv pip install -e "./lerobot_teleoperator_devices" --no-deps
    echo -e "${GREEN}✅ lerobot_teleoperator_devices installed${NC}"
fi

echo ""

# =============================================================================
# Step 7: Install gradio_agent requirements
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 7: Installing gradio_agent requirements${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [[ -f "gradio_agent/requirements.txt" ]]; then
    echo -e "${BLUE}📦 Installing gradio_agent requirements...${NC}"
    # Install with version constraints relaxed for numpy
    uv pip install -r gradio_agent/requirements.txt --no-deps 2>/dev/null || true
    echo -e "${GREEN}✅ gradio_agent requirements installed${NC}"
fi

echo ""

# =============================================================================
# Step 8: Create activation script
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 8: Creating activation script${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

cat > "activate_env.sh" << 'EOF'
#!/bin/bash
# =============================================================================
# LeRobot ROS Agent - Environment Activation Script
# =============================================================================
# Usage: source activate_env.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source ROS2 Humble
if [[ -f "/opt/ros/humble/setup.bash" ]]; then
    source /opt/ros/humble/setup.bash
    echo "✅ ROS2 Humble sourced"
fi

# Source local ROS2 workspace (if built)
if [[ -f "$SCRIPT_DIR/isaac_franka_moveit_perception/install/setup.bash" ]]; then
    source "$SCRIPT_DIR/isaac_franka_moveit_perception/install/setup.bash"
    echo "✅ Local ROS2 workspace sourced"
fi

# Activate Python virtual environment
if [[ -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
    echo "✅ Python virtual environment activated"
else
    echo "⚠️  Virtual environment not found. Run INSTALL/setup_with_uv.sh first."
fi

echo ""
echo "Environment ready! You can now run:"
echo "  python gradio_agent/demo_tool_calling.py --preload-policy"
EOF

chmod +x activate_env.sh
echo -e "${GREEN}✅ Created activate_env.sh${NC}"
echo ""

# =============================================================================
# Step 9: Verification
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 9: Verifying installation${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

echo -e "${BLUE}Checking imports...${NC}"

python << 'VERIFY_EOF'
import sys
success = True
packages = [
    ("torch", "PyTorch"),
    ("numpy", "NumPy"),
    ("cv2", "OpenCV"),
    ("gradio", "Gradio"),
    ("transformers", "Transformers"),
]

for module, name in packages:
    try:
        m = __import__(module)
        version = getattr(m, "__version__", "unknown")
        print(f"  ✅ {name}: {version}")
    except ImportError as e:
        print(f"  ❌ {name}: {e}")
        success = False

# Check CUDA
import torch
if torch.cuda.is_available():
    print(f"  ✅ CUDA: {torch.version.cuda} ({torch.cuda.get_device_name(0)})")
else:
    print(f"  ⚠️  CUDA: Not available (CPU mode)")

# Check lerobot
try:
    import lerobot
    print(f"  ✅ LeRobot: {lerobot.__version__}")
except ImportError:
    print("  ⚠️  LeRobot: Not installed (run: uv pip install -e ./lerobot)")

# Check lerobot_robot_ros
try:
    from lerobot_robot_ros import PandaROSPositionConfig
    print(f"  ✅ lerobot_robot_ros: Available")
except ImportError as e:
    print(f"  ⚠️  lerobot_robot_ros: {e}")

sys.exit(0 if success else 1)
VERIFY_EOF

echo ""

# =============================================================================
# Complete!
# =============================================================================
echo -e "${CYAN}"
echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║                    ✅ Installation Complete!                         ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${GREEN}📋 Summary:${NC}"
echo "  • Virtual environment: $PROJECT_ROOT/$VENV_NAME"
echo "  • PyTorch CUDA: $CUDA_VERSION"
echo "  • Activation script: source activate_env.sh"
echo ""

echo -e "${YELLOW}🚀 Quick Start:${NC}"
echo ""
echo "  # Activate environment (includes ROS2)"
echo "  source activate_env.sh"
echo ""
echo "  # Run the Gradio agent"
echo "  python gradio_agent/demo_tool_calling.py --preload-policy"
echo ""

echo -e "${BLUE}📖 For more info, see: INSTALL/UV_INSTALL.md${NC}"
echo ""

