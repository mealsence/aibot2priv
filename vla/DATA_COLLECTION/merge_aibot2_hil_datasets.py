#!/usr/bin/env python3
"""Merge a base AIBOT2 dataset with HIL correction episodes.

Supports different local roots per dataset (the lerobot-edit-dataset CLI passes one
shared --root, which breaks when HIL data lives under a custom folder).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from lerobot.datasets.dataset_tools import merge_datasets
from lerobot.datasets.lerobot_dataset import LeRobotDataset
from lerobot.utils.constants import HF_LEROBOT_HOME


def _resolve_dataset_root(repo_id: str, root: str | None) -> Path | None:
    if root:
        return Path(root).expanduser()
    default_root = HF_LEROBOT_HOME / repo_id
    return default_root if default_root.exists() else None


def _load_dataset(repo_id: str, root: str | None) -> LeRobotDataset:
    resolved_root = _resolve_dataset_root(repo_id, root)
    if resolved_root is not None:
        return LeRobotDataset(repo_id, root=resolved_root)
    return LeRobotDataset(repo_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge base + HIL LeRobot datasets")
    parser.add_argument("base_repo_id", help="Base dataset repo id")
    parser.add_argument("hil_repo_id", help="HIL dataset repo id")
    parser.add_argument("output_repo_id", nargs="?", help="Merged dataset repo id")
    parser.add_argument("--base-root", default=os.getenv("LEROBOT_BASE_DATASET_ROOT"))
    parser.add_argument("--hil-root", default=os.getenv("LEROBOT_HIL_DATASET_ROOT"))
    parser.add_argument(
        "--output-root",
        default=os.getenv("LEROBOT_DATASET_ROOT", str(HF_LEROBOT_HOME)),
        help="Parent directory for merged dataset output",
    )
    parser.add_argument(
        "--push-to-hub",
        action="store_true",
        default=os.getenv("LEROBOT_DATASET_PUSH", "false").lower() == "true",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_repo_id = args.output_repo_id
    if not output_repo_id:
        output_repo_id = f"{args.base_repo_id}_with_hil"

    base_ds = _load_dataset(args.base_repo_id, args.base_root)
    hil_ds = _load_dataset(args.hil_repo_id, args.hil_root)

    output_dir = Path(args.output_root).expanduser() / output_repo_id
    merged = merge_datasets(
        [base_ds, hil_ds],
        output_repo_id=output_repo_id,
        output_dir=output_dir,
    )

    print(f"Merged dataset: {output_repo_id}")
    print(f"  Episodes: {merged.meta.total_episodes}")
    print(f"  Frames:   {merged.meta.total_frames}")
    print(f"  Root:     {output_dir}")

    if args.push_to_hub:
        LeRobotDataset(merged.repo_id, root=output_dir).push_to_hub()
        print(f"Pushed to hub: {output_repo_id}")


if __name__ == "__main__":
    main()
