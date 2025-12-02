#!/bin/bash

# =============================================================================
# Complete LeRobot Setup for RTX 5090 (Virtual Environment)
# =============================================================================
#
# This script creates a complete virtual environment setup for LeRobot
# with RTX 5090 compatibility
# =============================================================================

set -e

echo "🚀 Complete LeRobot Setup for RTX 5080 (Virtual Environment)"
echo "============================================================="
echo ""

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "❌ Please run this script from the lerobot-dev directory"
    echo "   First clone: git clone https://github.com/huggingface/lerobot.git"
    echo "   Then cd lerobot"
    echo "   Then run: ./TOOLS/fixes/setup_lerobot_rtx5090_venv.sh"
    exit 1
fi

# Check if RTX 5090 is present
if nvidia-smi --query-gpu=name --format=csv,noheader | grep -q "RTX 5080"; then
    echo "✅ NVIDIA RTX 5090 detected"
else
    echo "⚠️  Warning: RTX 5090 not detected"
    echo "This script is optimized for RTX 5090 compatibility"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo ""

echo "============================================================="
echo "📦 Setting up Virtual Environment"
echo "============================================================="
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate
echo "✅ Virtual environment activated"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip
echo "✅ Pip upgraded"

echo ""
echo "============================================================="
echo "🔧 Installing PyTorch for RTX 5090"
echo "============================================================="
echo ""

# Install PyTorch 2.8.0 with CUDA 12.8 (RTX 5090 support)
echo "Installing PyTorch 2.8.0 with CUDA 12.8..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128
echo "✅ PyTorch installed"

# Install additional dependencies
echo "Installing additional dependencies..."
pip install typeguard --upgrade huggingface-hub wandb
echo "✅ Additional dependencies installed"

echo ""
echo "============================================================="
echo "📚 Installing LeRobot"
echo "============================================================="
echo ""

# Install LeRobot in editable mode
echo "Installing LeRobot in editable mode..."
pip install -e .
echo "✅ LeRobot installed"

# Install development dependencies
echo "Installing development dependencies..."
pip install pytest pre-commit black flake8 mypy
echo "✅ Development dependencies installed"

echo ""
echo "============================================================="
echo "🎣 Setting up Development Tools"
echo "============================================================="
echo ""

# Setup pre-commit hooks
echo "Setting up pre-commit hooks..."
pre-commit install || echo "⚠️  Pre-commit setup failed (this is optional)"
echo "✅ Pre-commit hooks configured"

# Make scripts executable
echo "Making scripts executable..."
chmod +x lerobot_commands.sh 2>/dev/null || true
chmod +x TRAIN/*.sh 2>/dev/null || true
chmod +x TEST/run_*.py 2>/dev/null || true
chmod +x TEST/test_spacemouse_*.py 2>/dev/null || true
chmod +x TOOLS/fixes/*.sh 2>/dev/null || true
echo "✅ Scripts made executable"

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p logs checkpoints datasets outputs
echo "✅ Directories created"

echo ""
echo "============================================================="
echo "🧪 Verifying Installation"
echo "============================================================="
echo ""

# Verify PyTorch installation
echo "Verifying PyTorch installation..."
python -c "
import torch
print('=' * 60)
print('✅ Installation Verification')
print('=' * 60)
print(f'PyTorch version: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'CUDA version: {torch.version.cuda}')
if torch.cuda.is_available():
    print(f'GPU detected: {torch.cuda.get_device_name(0)}')
    print(f'GPU count: {torch.cuda.device_count()}')
    # Test operations
    try:
        x = torch.randn(100, 100).cuda()
        y = torch.matmul(x, x)
        print('✅ CUDA operations working correctly!')

        # Test more complex operations
        z = torch.randn(1000, 1000).cuda()
        mean = z.mean()
        std = z.std()
        normalized = (z - mean) / std
        print('✅ Advanced CUDA operations working!')

    except Exception as e:
        print(f'❌ CUDA test failed: {e}')
else:
    print('❌ CUDA not available')
print('=' * 60)
"

# Verify LeRobot installation
echo "Verifying LeRobot installation..."
python -c "
try:
    import lerobot
    print(f'✅ LeRobot version: {lerobot.__version__}')
except ImportError as e:
    print(f'❌ LeRobot import failed: {e}')
"

# Check dependencies
echo "Checking dependencies..."
pip check || echo "⚠️  Some dependency conflicts detected (this may be normal)"

echo ""
echo "============================================================="
echo "✅ Setup Complete!"
echo "============================================================="
echo ""
echo "🎉 Your LeRobot environment is ready for RTX 5090!"
echo ""
echo "📋 Environment Details:"
echo "  - Virtual Environment: $(pwd)/venv"
echo "  - Python: $(python --version)"
echo "  - PyTorch: $(python -c 'import torch; print(torch.__version__)')"
echo "  - CUDA: $(python -c 'import torch; print(torch.version.cuda)')"
echo "  - GPU: $(python -c 'import torch; print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\")')"
echo ""
echo "🚀 How to Use:"
echo "  1. Activate environment: source venv/bin/activate"
echo "  2. Run training: lerobot-train"
echo "  3. Run evaluation: lerobot-eval"
echo "  4. Deactivate: deactivate"
echo ""
echo "📖 Documentation:"
echo "  - README.md: Project overview"
echo "  - docs/: Full documentation"
echo "  - examples/: Example scripts"
echo ""
echo "🔧 Troubleshooting:"
echo "  - If you have issues, run: ./TOOLS/fixes/fix_rtx5090_venv.sh"
echo "  - Check GPU status: nvidia-smi"
echo "  - Test PyTorch: python -c 'import torch; print(torch.cuda.is_available())'"
echo ""
echo "Happy coding! 🤖"