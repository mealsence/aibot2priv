#!/usr/bin/env python3
"""Quick test: connect aibot2, record a few observations, save as LeRobot dataset, push to HF.

Unlike ``lerobot-record`` / ``record_aibot2.sh``, this script does not require a teleoperator or
policy — it logs observations and fills actions with zeros (smoke test only, not imitation data).

Usage:
    source ~/ros2_alpha2_source.sh
    source /path/to/.venv/bin/activate
    python test_aibot2_record.py

Env vars:
    LEROBOT_DATASET_REPO_ID  (default: ases200q2/Aibot2_test)
    LEROBOT_DATASET_ROOT     (default: ~/lerobot_datasets/Aibot2_test)
    LEROBOT_SINGLE_TASK      (default: Pick object from table)
    LEROBOT_NUM_EPISODES     (default: 2)
    LEROBOT_EPISODE_SECONDS  (default: 10)
    LEROBOT_EPISODE_STEPS    (optional override; default: LEROBOT_EPISODE_SECONDS * LEROBOT_FPS)
    LEROBOT_FPS              (default: 25)
    LEROBOT_PUSH             (default: false)
    LEROBOT_CAMERA_COUNT     (default: 4)
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path

import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _finalize_dataset_files(dataset) -> None:
    """Flush LeRobot's open parquet writer before reading or uploading files."""
    close_writer = getattr(dataset, "_close_writer", None)
    if close_writer is not None:
        close_writer()

    meta = getattr(dataset, "meta", None)
    close_meta_writer = getattr(meta, "_close_writer", None)
    if close_meta_writer is not None:
        close_meta_writer()


def _validate_local_parquets(dataset_root: str) -> None:
    """Catch incomplete parquet files before pushing them to the Hub."""
    import pyarrow.parquet as pq

    root = Path(dataset_root)
    parquet_paths = sorted(root.glob("**/*.parquet"))
    if not parquet_paths:
        raise RuntimeError(f"No parquet files found under {root}")

    for path in parquet_paths:
        data = path.read_bytes()
        if not data.startswith(b"PAR1") or not data.endswith(b"PAR1"):
            raise RuntimeError(f"Incomplete parquet file, not pushing: {path}")
        pq.read_metadata(path)


def _validate_episode_metadata(dataset_root: str) -> None:
    """Make sure data rows and episode metadata agree before pushing."""
    import json

    import pandas as pd

    root = Path(dataset_root)
    info = json.loads((root / "meta/info.json").read_text())
    episode_paths = []
    data_paths = []
    deadline = time.monotonic() + 30.0
    while True:
        episode_paths = sorted((root / "meta/episodes").glob("**/*.parquet"))
        data_paths = sorted((root / "data").glob("**/*.parquet"))
        if episode_paths and data_paths:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(0.25)

    if not episode_paths:
        raise RuntimeError(f"No episode metadata parquet files found under {root / 'meta/episodes'}")
    if not data_paths:
        raise RuntimeError(f"No data parquet files found under {root / 'data'}")

    episodes = pd.concat(pd.read_parquet(path) for path in episode_paths)
    data = pd.concat(pd.read_parquet(path) for path in data_paths)

    expected_episodes = sorted(data["episode_index"].unique().tolist())
    metadata_episodes = sorted(episodes["episode_index"].tolist())
    if metadata_episodes != expected_episodes:
        raise RuntimeError(
            f"Episode metadata mismatch: meta has {metadata_episodes}, data has {expected_episodes}"
        )

    total_length = int(episodes["length"].sum())
    if total_length != len(data) or int(info["total_frames"]) != len(data):
        raise RuntimeError(
            f"Frame metadata mismatch: meta length={total_length}, "
            f"info total_frames={info['total_frames']}, data rows={len(data)}"
        )

    if int(info["total_episodes"]) != len(metadata_episodes):
        raise RuntimeError(
            f"Episode count mismatch: info total_episodes={info['total_episodes']}, "
            f"meta rows={len(metadata_episodes)}"
        )


def _push_dataset_to_hub(dataset, dataset_root: str) -> None:
    """Push, then explicitly refresh metadata files that the visualizer depends on."""
    from huggingface_hub import HfApi

    dataset.push_to_hub()

    # The visualizer trusts meta/info.json and meta/episodes/*.parquet. Make a
    # second small metadata upload so stale Hub metadata cannot survive a push.
    HfApi().upload_folder(
        repo_id=dataset.repo_id,
        repo_type="dataset",
        folder_path=str(Path(dataset_root) / "meta"),
        path_in_repo="meta",
    )


def main():
    from lerobot_robot_ros import Aibot2Config, Aibot2

    repo_id = os.getenv("LEROBOT_DATASET_REPO_ID", "ases200q2/Aibot2_test")
    dataset_root = os.getenv("LEROBOT_DATASET_ROOT", os.path.expanduser("~/lerobot_datasets/Aibot2_test"))
    if Path(dataset_root).exists():
        suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
        dataset_root = f"{dataset_root}_{suffix}"
        logger.warning("Dataset root already exists; writing to %s instead.", dataset_root)
    single_task = os.getenv("LEROBOT_SINGLE_TASK", "Pick object from table")
    fps = int(os.getenv("LEROBOT_FPS", "25"))
    num_episodes = int(os.getenv("LEROBOT_NUM_EPISODES", "2"))
    episode_seconds = float(os.getenv("LEROBOT_EPISODE_SECONDS", "10"))
    episode_steps = int(os.getenv("LEROBOT_EPISODE_STEPS", str(max(1, int(round(episode_seconds * fps))))))
    push = os.getenv("LEROBOT_PUSH", "false").lower() == "true"
    camera_count = int(os.getenv("LEROBOT_CAMERA_COUNT", "4"))

    os.environ["LEROBOT_CAMERA_COUNT"] = str(camera_count)

    # --- Setup robot (set camera count BEFORE creating config) ---
    config = Aibot2Config() if camera_count > 0 else Aibot2Config(cameras={})
    robot = Aibot2(config)

    logger.info("Connecting to aibot2...")
    robot.connect()
    logger.info("Connected! Action features: %s", list(robot.action_features.keys()))
    logger.info("Observation features: %s",
                [k for k in robot.observation_features if not k.startswith("camera")])
    camera_frame_counts_start = {
        key: getattr(cam, "frames_received", 0) for key, cam in robot.cameras.items()
    }

    # --- Setup dataset ---
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.datasets.utils import hw_to_dataset_features

    # Build ordered lists of observation and action keys (excluding cameras)
    obs_keys = [k for k, v in robot.observation_features.items() if not isinstance(v, tuple)]
    action_keys = list(robot.action_features.keys())
    use_videos = any(isinstance(ft, tuple) for ft in robot.observation_features.values())

    # Match the schema produced by `lerobot-record`.
    # Example working Franka dataset:
    #   action
    #   observation.state
    #   observation.images.camera_1
    features = {
        **hw_to_dataset_features(robot.action_features, "action", use_video=use_videos),
        **hw_to_dataset_features(robot.observation_features, "observation", use_video=use_videos),
    }

    dataset = LeRobotDataset.create(
        repo_id=repo_id,
        root=dataset_root,
        fps=fps,
        features=features,
        robot_type=robot.name,
        use_videos=use_videos,
    )

    logger.info("Dataset created at %s", dataset_root)

    # --- Record episodes ---
    total_recorded_frames = 0
    total_recording_time = 0.0
    camera_recording_frames = {key: 0 for key in robot.cameras}
    camera_fresh_frames = {key: 0 for key in robot.cameras}
    camera_reused_frames = {key: 0 for key in robot.cameras}
    camera_last_counts = {
        key: getattr(cam, "frames_received", 0) for key, cam in robot.cameras.items()
    }
    try:
        for ep in range(num_episodes):
            logger.info("=== Episode %d/%d ===", ep + 1, num_episodes)
            input("Press Enter to start recording...")

            episode_start = time.perf_counter()
            camera_counts_episode_start = {
                key: getattr(cam, "frames_received", 0) for key, cam in robot.cameras.items()
            }
            window_start = episode_start
            for step in range(episode_steps):
                t0 = time.perf_counter()

                obs = robot.get_observation()

                # Build frame — pack joints into vectors
                frame = {"task": single_task}
                # Camera images use the standard LeRobot recorder prefix:
                # observation.images.<camera_name>
                for key, ft in robot.observation_features.items():
                    if isinstance(ft, tuple):
                        frame[f"observation.images.{key}"] = obs[key]
                        current_count = getattr(robot.cameras[key], "frames_received", 0)
                        if current_count > camera_last_counts.get(key, 0):
                            camera_fresh_frames[key] += 1
                        else:
                            camera_reused_frames[key] += 1
                        camera_last_counts[key] = current_count
                # observation.state = [left_arm_joints(7), right_arm_joints(7), left_gripper, right_gripper]
                frame["observation.state"] = np.array(
                    [obs[k] for k in obs_keys], dtype=np.float32
                )
                # action = zeros (no teleop)
                frame["action"] = np.zeros(len(action_keys), dtype=np.float32)

                dataset.add_frame(frame)

                dt = time.perf_counter() - t0
                sleep_time = max(0, 1.0 / fps - dt)
                if sleep_time > 0:
                    time.sleep(sleep_time)

                if (step + 1) % 30 == 0:
                    window_elapsed = time.perf_counter() - window_start
                    logger.info(
                        "  Step %d/%d (%.1f Hz actual over last %d frames)",
                        step + 1,
                        episode_steps,
                        30 / max(window_elapsed, 1e-6),
                        30,
                    )
                    window_start = time.perf_counter()

            episode_elapsed = time.perf_counter() - episode_start
            for key, cam in robot.cameras.items():
                camera_recording_frames[key] += (
                    getattr(cam, "frames_received", 0) - camera_counts_episode_start.get(key, 0)
                )

            dataset.save_episode()
            total_recorded_frames += episode_steps
            total_recording_time += episode_elapsed
            logger.info("Episode %d saved (%d frames)", ep + 1, episode_steps)

    except KeyboardInterrupt:
        logger.info("Recording interrupted")
    finally:
        if total_recorded_frames > 0 and total_recording_time > 0:
            logger.info(
                "Recording timing: %.1f Hz actual over %.1fs (%d frames, target %d Hz)",
                total_recorded_frames / total_recording_time,
                total_recording_time,
                total_recorded_frames,
                fps,
            )
            for key, cam in robot.cameras.items():
                frames_received = camera_recording_frames.get(key, 0)
                logger.info(
                    "Camera %s: %d ROS frames received during recording (%.1f Hz, %.1f%% of dataset frames; %d fresh, %d reused)",
                    key,
                    frames_received,
                    frames_received / total_recording_time,
                    100.0 * frames_received / total_recorded_frames,
                    camera_fresh_frames.get(key, 0),
                    camera_reused_frames.get(key, 0),
                )
                if frames_received < 0.9 * total_recorded_frames:
                    logger.warning(
                        "Camera %s is slower than the dataset FPS. Consider LEROBOT_FPS=%d or fewer cameras.",
                        key,
                        max(1, int(frames_received / total_recording_time)),
                    )
        robot.disconnect()

    _finalize_dataset_files(dataset)
    _validate_local_parquets(dataset_root)
    _validate_episode_metadata(dataset_root)

    # --- Push ---
    if push:
        logger.info("Pushing to Hugging Face: %s", repo_id)
        _push_dataset_to_hub(dataset, dataset_root)
        logger.info("Done! View at: https://huggingface.co/datasets/%s", repo_id)
    else:
        logger.info("Skipping push. To push: LEROBOT_PUSH=true python %s", __file__)
        logger.info("Or manually: python -c \"from lerobot.datasets.lerobot_dataset import LeRobotDataset; "
                     "ds = LeRobotDataset('%s', root='%s'); ds.push_to_hub()\"", repo_id, dataset_root)


if __name__ == "__main__":
    main()
