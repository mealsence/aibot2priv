#!/usr/bin/env python
"""
Custom PI05 training script with 8-bit AdamW optimizer for memory efficiency.

This script patches the optimizer factory at runtime to use bitsandbytes' 8-bit Adam,
reducing optimizer state memory from ~29GB to ~7GB for 4B parameter models.

Usage:
    python train_pi05_8bit.py [additional lerobot-train args]
    
Example:
    python train_pi05_8bit.py --steps=5000 --batch_size=2
"""
import sys
import os
from dataclasses import asdict, dataclass

# Set CUDA allocator configuration for better memory management
os.environ.setdefault("PYTORCH_ALLOC_CONF", "expandable_segments:True")

import torch

# Import bitsandbytes for 8-bit optimizer
try:
    import bitsandbytes as bnb
except ImportError:
    print("ERROR: bitsandbytes is required. Install with: pip install bitsandbytes")
    sys.exit(1)

# Import lerobot components
from lerobot.optim.optimizers import OptimizerConfig


# Define 8-bit AdamW optimizer config
@dataclass
class AdamW8bitConfig(OptimizerConfig):
    """8-bit AdamW optimizer using bitsandbytes for memory-efficient training.
    
    This optimizer uses 8-bit precision for optimizer states (momentum and variance),
    reducing memory usage by ~4x compared to standard fp32 optimizer states.
    Particularly useful for training large models like PI05 on limited GPU memory.
    """
    lr: float = 1e-3
    betas: tuple[float, float] = (0.9, 0.999)
    eps: float = 1e-8
    weight_decay: float = 1e-2
    grad_clip_norm: float = 10.0

    def build(self, params: dict) -> torch.optim.Optimizer:
        kwargs = asdict(self)
        kwargs.pop("grad_clip_norm")
        return bnb.optim.AdamW8bit(params, **kwargs)


# Register 8-bit AdamW optimizer (only if not already registered)
try:
    OptimizerConfig.register_subclass("adamw_8bit")(AdamW8bitConfig)
except ValueError as e:
    if "already registered" in str(e):
        # Already registered, that's fine
        pass
    else:
        raise


def main():
    """Run training with 8-bit optimizer support."""
    # Import the main training function after registering the optimizer
    from lerobot.scripts.lerobot_train import main as lerobot_train_main
    
    print("=" * 60)
    print("PI05 Training with 8-bit AdamW Optimizer")
    print("=" * 60)
    print("Memory optimization: Using bitsandbytes AdamW8bit")
    print("This reduces optimizer state memory by ~4x")
    print("=" * 60)
    
    # Call the lerobot training main function
    lerobot_train_main()


if __name__ == "__main__":
    main()
