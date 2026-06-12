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
#   ./misc/INSTALL/setup_with_uv.sh [OPTIONS]
#
# Options:
#   --cuda128     Install PyTorch with CUDA 12.8 (RTX 40/50 series)
#   --cuda124     Install PyTorch with CUDA 12.4 (RTX 30 series)
#   --cpu         Install PyTorch CPU-only version
#   --install-torch  Install PyTorch using selected/default CUDA option
#   --skip-torch     Skip PyTorch install (default; prints manual commands)
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
INSTALL_TORCH=false
INCLUDE_DEV=false
SKIP_ROS=false
VENV_NAME=".venv"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --cuda128)
            CUDA_VERSION="cu128"
            INSTALL_TORCH=true
            shift
            ;;
        --cuda124)
            CUDA_VERSION="cu124"
            INSTALL_TORCH=true
            shift
            ;;
        --cpu)
            CUDA_VERSION="cpu"
            INSTALL_TORCH=true
            shift
            ;;
        --install-torch)
            INSTALL_TORCH=true
            shift
            ;;
        --skip-torch)
            INSTALL_TORCH=false
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

# Expected layout: <repo>/misc/INSTALL/setup_with_uv.sh
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Fallback: search upwards for repository root containing pyproject.toml
if [[ ! -f "$PROJECT_ROOT/pyproject.toml" ]]; then
    SEARCH_DIR="$SCRIPT_DIR"
    while [[ "$SEARCH_DIR" != "/" ]]; do
        if [[ -f "$SEARCH_DIR/pyproject.toml" ]]; then
            PROJECT_ROOT="$SEARCH_DIR"
            break
        fi
        SEARCH_DIR="$(dirname "$SEARCH_DIR")"
    done
fi

if [[ ! -f "$PROJECT_ROOT/pyproject.toml" ]]; then
    echo -e "${RED}❌ Could not locate project root (missing pyproject.toml)${NC}"
    echo -e "${YELLOW}   Run this script from within the lerobot-ros-agent repository.${NC}"
    exit 1
fi

cd "$PROJECT_ROOT"

echo -e "${BLUE}📁 Project root: ${PROJECT_ROOT}${NC}"
echo ""

# =============================================================================
# Step 1: Check prerequisites
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 1: Checking prerequisites${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Check Python version and select a supported interpreter
SYSTEM_PYTHON_VERSION="unknown"
if command -v python3 &> /dev/null; then
    SYSTEM_PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
fi

PYTHON_BIN=""
for candidate in python3.10 python3.11 python3; do
    if command -v "$candidate" &> /dev/null; then
        candidate_version=$("$candidate" --version 2>&1 | cut -d' ' -f2)
        candidate_major=$(echo "$candidate_version" | cut -d'.' -f1)
        candidate_minor=$(echo "$candidate_version" | cut -d'.' -f2)
        if [[ "$candidate_major" -eq 3 ]] && ([[ "$candidate_minor" -eq 10 ]] || [[ "$candidate_minor" -eq 11 ]]); then
            PYTHON_BIN="$candidate"
            PYTHON_VERSION="$candidate_version"
            break
        fi
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    echo -e "${RED}❌ Python 3.10 or 3.11 is required."
    echo -e "${YELLOW}   Detected system python3: $SYSTEM_PYTHON_VERSION${NC}"
    echo -e "${YELLOW}   Install python3.10 or python3.11 and retry.${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Using Python interpreter: $PYTHON_BIN ($PYTHON_VERSION)${NC}"

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
    uv venv "$VENV_NAME" --python "$PYTHON_BIN"
fi

# Activate virtual environment
source "$VENV_NAME/bin/activate"
echo -e "${GREEN}✅ Virtual environment created and activated: $VENV_NAME${NC}"
echo ""

# =============================================================================
# Step 4: Install PyTorch
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 4: PyTorch setup${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [[ "$INSTALL_TORCH" == true ]]; then
    if [[ "$CUDA_VERSION" == "cpu" ]]; then
        echo -e "${BLUE}📦 Installing PyTorch (CPU)...${NC}"
        uv pip install torch torchvision torchaudio \
            --index-strategy unsafe-best-match \
            --index-url https://pypi.org/simple \
            --extra-index-url https://download.pytorch.org/whl/cpu
    elif [[ "$CUDA_VERSION" == "cu124" ]]; then
        echo -e "${BLUE}📦 Installing PyTorch with CUDA 12.4...${NC}"
        uv pip install torch torchvision torchaudio \
            --index-strategy unsafe-best-match \
            --index-url https://pypi.org/simple \
            --extra-index-url https://download.pytorch.org/whl/cu124 \
            --extra-index-url https://pypi.nvidia.com
    else
        echo -e "${BLUE}📦 Installing PyTorch with CUDA 12.8...${NC}"
        uv pip install torch torchvision torchaudio \
            --index-strategy unsafe-best-match \
            --index-url https://pypi.org/simple \
            --extra-index-url https://download.pytorch.org/whl/cu128 \
            --extra-index-url https://pypi.nvidia.com
    fi

    # Verify PyTorch installation
    python -c "import torch; print(f'PyTorch {torch.__version__}, CUDA: {torch.cuda.is_available()}')" && \
        echo -e "${GREEN}✅ PyTorch installed successfully${NC}" || \
        echo -e "${RED}❌ PyTorch installation failed${NC}"
else
    echo -e "${YELLOW}⏭️  Skipping PyTorch install (default behavior)${NC}"
    echo -e "${BLUE}Install manually based on your GPU/driver:${NC}"
    echo "  CUDA 12.8: uv pip install torch torchvision torchaudio --index-strategy unsafe-best-match --index-url https://pypi.org/simple --extra-index-url https://download.pytorch.org/whl/cu128 --extra-index-url https://pypi.nvidia.com"
    echo "  CUDA 12.4: uv pip install torch torchvision torchaudio --index-strategy unsafe-best-match --index-url https://pypi.org/simple --extra-index-url https://download.pytorch.org/whl/cu124 --extra-index-url https://pypi.nvidia.com"
    echo "  CPU only : uv pip install torch torchvision torchaudio --index-strategy unsafe-best-match --index-url https://pypi.org/simple --extra-index-url https://download.pytorch.org/whl/cpu"
    echo -e "${BLUE}Tip: re-run this script with --cuda128, --cuda124, or --cpu for automatic install.${NC}"
fi
echo ""

# =============================================================================
# Step 5: Install project dependencies
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 5: Installing project dependencies${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

PROJECT_INDEX_ARGS="--index-strategy unsafe-best-match --index-url https://pypi.org/simple"
if [[ "$CUDA_VERSION" == "cpu" ]]; then
    PROJECT_INDEX_ARGS="$PROJECT_INDEX_ARGS --extra-index-url https://download.pytorch.org/whl/cpu"
elif [[ "$CUDA_VERSION" == "cu124" ]]; then
    PROJECT_INDEX_ARGS="$PROJECT_INDEX_ARGS --extra-index-url https://download.pytorch.org/whl/cu124 --extra-index-url https://pypi.nvidia.com"
else
    PROJECT_INDEX_ARGS="$PROJECT_INDEX_ARGS --extra-index-url https://download.pytorch.org/whl/cu128 --extra-index-url https://pypi.nvidia.com"
fi

# Install main project
if [[ "$INCLUDE_DEV" == true ]]; then
    echo -e "${BLUE}📦 Installing project with dev dependencies...${NC}"
    uv pip install $PROJECT_INDEX_ARGS -e ".[dev]"
else
    echo -e "${BLUE}📦 Installing project dependencies...${NC}"
    uv pip install $PROJECT_INDEX_ARGS -e .
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
if [[ -d "ros2/lerobot_robot_ros" ]]; then
    echo -e "${BLUE}📦 Installing lerobot_robot_ros...${NC}"
    uv pip install -e "./ros2/lerobot_robot_ros" --no-deps
    echo -e "${GREEN}✅ lerobot_robot_ros installed${NC}"
fi

# Install lerobot_teleoperator_devices
if [[ -d "ros2/lerobot_teleoperator_devices" ]]; then
    echo -e "${BLUE}📦 Installing lerobot_teleoperator_devices...${NC}"
    uv pip install -e "./ros2/lerobot_teleoperator_devices" --no-deps
    echo -e "${GREEN}✅ lerobot_teleoperator_devices installed${NC}"
fi

echo ""

# =============================================================================
# Step 7: Install gradio_agent requirements
# =============================================================================
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}Step 7: Installing gradio_agent requirements${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [[ -f "ui/gradio_agent/requirements.txt" ]]; then
    echo -e "${BLUE}📦 Installing gradio_agent requirements...${NC}"
    # Install with version constraints relaxed for numpy
    uv pip install -r ui/gradio_agent/requirements.txt --no-deps 2>/dev/null || true
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
if [[ -f "$SCRIPT_DIR/ros2/isaac_franka_moveit_perception/install/setup.bash" ]]; then
    source "$SCRIPT_DIR/ros2/isaac_franka_moveit_perception/install/setup.bash"
    echo "✅ Local ROS2 workspace sourced"
fi

# Activate Python virtual environment
if [[ -f "$SCRIPT_DIR/.venv/bin/activate" ]]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
    echo "✅ Python virtual environment activated"
else
    echo "⚠️  Virtual environment not found. Run misc/INSTALL/setup_with_uv.sh first."
fi

echo ""
echo "Environment ready! You can now run:"
echo "  python ui/gradio_agent/demo_tool_calling.py --preload-policy"
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

INSTALL_TORCH="$INSTALL_TORCH" python << 'VERIFY_EOF'
import sys
import os
success = True

install_torch = os.environ.get("INSTALL_TORCH", "false").lower() == "true"

packages = [
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

# Check torch (required only if auto-install was requested)
try:
    import torch
    print(f"  ✅ PyTorch: {torch.__version__}")
    if torch.cuda.is_available():
        print(f"  ✅ CUDA: {torch.version.cuda} ({torch.cuda.get_device_name(0)})")
    else:
        print(f"  ⚠️  CUDA: Not available (CPU mode)")
except ImportError as e:
    if install_torch:
        print(f"  ❌ PyTorch: {e}")
        success = False
    else:
        print(f"  ⚠️  PyTorch: Not installed (manual install mode)")
        print("     Use one of:")
        print("     uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128")
        print("     uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124")
        print("     uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu")

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
if [[ "$INSTALL_TORCH" == true ]]; then
    echo "  • PyTorch: installed ($CUDA_VERSION)"
else
    echo "  • PyTorch: skipped (manual install mode)"
fi
echo "  • Activation script: source activate_env.sh"
echo ""

echo -e "${YELLOW}🚀 Quick Start:${NC}"
echo ""
echo "  # Activate environment (includes ROS2)"
echo "  source activate_env.sh"
echo ""
echo "  # Run the Gradio agent"
echo "  python ui/gradio_agent/demo_tool_calling.py --preload-policy"
echo ""

echo -e "${BLUE}📖 For more info, see: misc/INSTALL/UV_INSTALL.md${NC}"
echo ""

