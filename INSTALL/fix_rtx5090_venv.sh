#!/bin/bash

# =============================================================================
# Fix PyTorch Compatibility for NVIDIA RTX 5090 (Virtual Environment)
# =============================================================================
#
# Issue: RTX 5090 has compute capability sm_120 (Blackwell architecture)
# PyTorch stable (2.7.1) only supports up to sm_90
#
# Solution: Install PyTorch 2.8.0 with CUDA 12.8 support in virtual environment
# =============================================================================

set -e

echo "🔧 RTX 5090 PyTorch Compatibility Fix (Virtual Environment)"
echo "============================================================="
echo ""

# Check if we're in a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "❌ No virtual environment active"
    echo "Please activate your virtual environment first:"
    echo "  python -m venv venv"
    echo "  source venv/bin/activate"
    echo ""
    echo "Or if you already have one:"
    echo "  source venv/bin/activate"
    exit 1
fi

echo "✅ Virtual environment detected: $VIRTUAL_ENV"
echo ""

# Check if RTX 5090 is present
if nvidia-smi --query-gpu=name --format=csv,noheader | grep -q "RTX 5090"; then
    echo "✅ NVIDIA RTX 5090 detected"
else
    echo "⚠️  Warning: RTX 5090 not detected"
    echo "This script is specifically for RTX 5090 compatibility"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo ""

echo "📋 Current PyTorch Configuration:"
python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA version: {torch.version.cuda}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')" 2>&1 || true
echo ""

# Check PyTorch compatibility warning
echo "🔍 Checking for compatibility issues..."
COMPAT_CHECK=$(python -c "import torch; torch.cuda.init()" 2>&1 || true)
if echo "$COMPAT_CHECK" | grep -q "sm_120 is not compatible"; then
    echo "❌ Confirmed: PyTorch incompatible with RTX 5090"
    echo ""
else
    echo "✅ No compatibility issues detected"
    echo "Your PyTorch installation appears to be working correctly"
    echo ""
    read -p "Do you still want to upgrade to PyTorch 2.8.0+cu128? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Exiting without changes"
        exit 0
    fi
fi

echo "============================================================="
echo "🚀 Starting PyTorch Upgrade for RTX 5090"
echo "============================================================="
echo ""
echo "This will:"
echo "  1. Uninstall current PyTorch"
echo "  2. Install PyTorch 2.8.0 with CUDA 12.8 (RTX 5090 support)"
echo "  3. Install missing dependencies"
echo "  4. Verify the installation"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted by user"
    exit 0
fi

echo ""
echo "Step 1/4: Uninstalling current PyTorch..."
pip uninstall -y torch torchvision torchaudio 2>&1 | grep -v "^Proceed" || true

echo ""
echo "Step 2/4: Installing PyTorch 2.8.0 with CUDA 12.8..."
echo "This may take a few minutes..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

echo ""
echo "Step 3/4: Installing missing dependencies..."
pip install typeguard --upgrade huggingface-hub wandb

echo ""
echo "Step 4/4: Verifying installation..."
python -c "
import torch
print('=' * 60)
print('✅ PyTorch Installation Verified')
print('=' * 60)
print(f'PyTorch version: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
print(f'CUDA version: {torch.version.cuda}')
if torch.cuda.is_available():
    print(f'GPU detected: {torch.cuda.get_device_name(0)}')
    print(f'GPU count: {torch.cuda.device_count()}')
    # Test a simple operation
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

if [ $? -eq 0 ]; then
    echo ""
    echo "============================================================="
    echo "✅ RTX 5090 Fix Complete!"
    echo "============================================================="
    echo ""
    echo "Your virtual environment is now ready to use the RTX 5090 with PyTorch"
    echo ""
    echo "📋 Next Steps:"
    echo "  - Install lerobot: pip install -e ."
    echo "  - Test your training/evaluation commands"
    echo "  - The compute capability warning should be gone"
    echo "  - CUDA operations should work normally"
    echo ""
    echo "💡 To reactivate this environment later:"
    echo "  source venv/bin/activate"
    echo ""
else
    echo ""
    echo "============================================================="
    echo "❌ Installation Failed"
    echo "============================================================="
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check your internet connection"
    echo "  2. Ensure you have enough disk space"
    echo "  3. Try manually: pip install torch --index-url https://download.pytorch.org/whl/cu128"
    echo "  4. Check if your virtual environment is properly activated"
    echo ""
    exit 1
fi