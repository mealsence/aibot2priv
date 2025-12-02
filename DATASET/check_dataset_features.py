#!/usr/bin/env python3
"""Check if a LeRobot dataset contains image observations."""

import sys
from pathlib import Path

try:
    from lerobot.common.datasets.lerobot_dataset import LeRobotDataset
except ImportError:
    try:
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
    except ImportError:
        print("Error: Cannot import LeRobotDataset. Make sure lerobot is installed.")
        sys.exit(1)

def check_dataset(repo_id: str):
    """Check dataset features for camera observations."""
    print(f"Checking dataset: {repo_id}")
    print("=" * 60)
    
    try:
        # Load dataset metadata
        dataset = LeRobotDataset(repo_id)
        
        print(f"\nDataset loaded successfully!")
        print(f"Robot type: {dataset.meta.robot_type}")
        print(f"FPS: {dataset.meta.fps}")
        print(f"Total episodes: {dataset.meta.info.get('total_episodes', 'N/A')}")
        print(f"Total frames: {dataset.meta.info.get('total_frames', 'N/A')}")
        
        print(f"\n{'='*60}")
        print("FEATURES:")
        print(f"{'='*60}")
        
        features = dataset.meta.features
        has_images = False
        has_videos = False
        
        for key, feature_info in features.items():
            dtype = feature_info.get("dtype", "unknown")
            shape = feature_info.get("shape", "unknown")
            print(f"  {key}:")
            print(f"    dtype: {dtype}")
            print(f"    shape: {shape}")
            
            if dtype == "image":
                has_images = True
                print(f"    ✓ IMAGE observation found!")
            elif dtype == "video":
                has_videos = True
                print(f"    ✓ VIDEO observation found!")
            print()
        
        print(f"{'='*60}")
        print("SUMMARY:")
        print(f"{'='*60}")
        print(f"Camera keys (images/videos): {dataset.meta.camera_keys}")
        print(f"Image keys: {dataset.meta.image_keys}")
        print(f"Video keys: {dataset.meta.video_keys}")
        
        if has_images or has_videos:
            print(f"\n✓ Dataset CONTAINS camera observations!")
            if has_images:
                print(f"  - Stored as individual images (PNG)")
            if has_videos:
                print(f"  - Stored as video files (MP4)")
        else:
            print(f"\n✗ Dataset DOES NOT contain camera observations")
            print(f"  Only state observations found")
        
        return has_images or has_videos
        
    except Exception as e:
        print(f"Error loading dataset: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    repo_id = "ases200q2/spacemouse-ee-teleop-fast-pick-cube"
    check_dataset(repo_id)



