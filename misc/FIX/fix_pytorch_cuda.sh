#!/bin/bash
set -e

echo "🔧 Fixing PyTorch CUDA Library Conflict"
echo "========================================"
echo ""

# Activate conda environment
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate lerobot-org

echo "Step 1: Uninstalling PyTorch..."
pip uninstall -y torch torchvision torchaudio || true

echo ""
echo "Step 2: Removing conflicting conda CUDA packages..."
conda remove -y cudatoolkit cudnn cuda-toolkit nvidia cuda -c conda-forge -c nvidia 2>/dev/null || echo "No conda CUDA packages to remove"

echo ""
echo "Step 3: Cleaning pip cache..."
pip cache purge || true

echo ""
echo "Step 4: Installing PyTorch with CUDA 12.8..."
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

echo ""
echo "Step 5: Verifying installation..."
python -c "
import torch
print('=' * 60)
print('✅ PyTorch Installation')
print('=' * 60)
print(f'PyTorch version: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'CUDA version: {torch.version.cuda}')
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    # Test CUDA operation
    try:
        x = torch.randn(10, 10).cuda()
        y = torch.matmul(x, x)
        print('✅ CUDA operations working!')
    except Exception as e:
        print(f'❌ CUDA test failed: {e}')
else:
    print('⚠️  CUDA not available')
print('=' * 60)
"

echo ""
echo "Done! If CUDA still doesn't work, try Option 2 (CUDA 12.1) or Option 3 (CPU-only)."


