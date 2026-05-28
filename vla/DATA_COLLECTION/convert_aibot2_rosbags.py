#!/usr/bin/env python3
"""Convert AIBOT2 ROS2 bags into a LeRobot dataset.

This is intended for bags recorded alongside
``ases200q2/Aibot2_pick_object_from_table_v6`` data collection. Each bag
directory becomes one LeRobot episode. Frames are sampled at a fixed FPS from
the recorded bag timeline and assembled from the nearest/latest ROS messages.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from rclpy.serialization import deserialize_message
from rosbag2_py import ConverterOptions, SequentialReader, StorageOptions
from rosidl_runtime_py.utilities import get_message

from lerobot.datasets.lerobot_dataset import LeRobotDataset


LOGGER = logging.getLogger("convert_aibot2_rosbags")


DEFAULT_REPO_ID = "ases200q2/Aibot2_pick_object_and_put_the_box_2026-05-20_rosbag"
DEFAULT_REFERENCE_ROOT = Path.home() / "lerobot_datasets/Aibot2_pick_object_and_put_the_box_2026-05-20"
DEFAULT_OUTPUT_ROOT = Path.home() / "lerobot_datasets/Aibot2_pick_object_and_put_the_box_2026-05-20_rosbag"
DEFAULT_TASK = "Pick object from table and put it inside the box"

ACTION_NAMES = [
    "left_arm.x",
    "left_arm.y",
    "left_arm.z",
    "left_arm.qx",
    "left_arm.qy",
    "left_arm.qz",
    "left_arm.qw",
    "right_arm.x",
    "right_arm.y",
    "right_arm.z",
    "right_arm.qx",
    "right_arm.qy",
    "right_arm.qz",
    "right_arm.qw",
    "left_gripper.pos",
    "right_gripper.pos",
]

STATE_NAMES = [
    "ZPF_left_Joint1.pos",
    "ZPF_left_Joint2.pos",
    "ZPF_left_Joint3.pos",
    "ZPF_left_Joint4.pos",
    "ZPF_left_Joint5.pos",
    "ZPF_left_Joint6.pos",
    "ZPF_left_Joint7.pos",
    "ZPF_right_Joint1.pos",
    "ZPF_right_Joint2.pos",
    "ZPF_right_Joint3.pos",
    "ZPF_right_Joint4.pos",
    "ZPF_right_Joint5.pos",
    "ZPF_right_Joint6.pos",
    "ZPF_right_Joint7.pos",
    "2FEG_l_Joint1.pos",
    "2FEG_r_Joint1.pos",
]

JOINT_NAMES = [name.removesuffix(".pos") for name in STATE_NAMES]

DEFAULT_CAMERA_TOPICS = {
    "camera_front": "/camera/camera_front/color/image_raw/compressed",
    "camera_left": "/camera/camera_left/color/image_raw/compressed",
    "camera_right": "/camera/camera_right/color/image_raw/compressed",
    "camera_top": "/camera/camera_top/color/image_raw/compressed",
}


@dataclass(frozen=True)
class TimedValue:
    t: float
    value: Any


@dataclass
class BagData:
    bag: Path
    start_ns: int | None = None
    end_ns: int | None = None
    states: list[TimedValue] | None = None
    actions: list[TimedValue] | None = None
    hand_states: list[TimedValue] | None = None
    images: dict[str, list[TimedValue]] | None = None

    def __post_init__(self) -> None:
        self.states = [] if self.states is None else self.states
        self.actions = [] if self.actions is None else self.actions
        self.hand_states = [] if self.hand_states is None else self.hand_states
        self.images = {} if self.images is None else self.images


@dataclass
class NearestResult:
    value: Any | None
    age_s: float | None


def ns_to_s(ns: int, start_ns: int) -> float:
    return (ns - start_ns) / 1e9


def stamp_to_ns(stamp: Any) -> int:
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


def pose_to_values(pose: Any) -> list[float]:
    return [
        float(pose.position.x),
        float(pose.position.y),
        float(pose.position.z),
        float(pose.orientation.x),
        float(pose.orientation.y),
        float(pose.orientation.z),
        float(pose.orientation.w),
    ]


def normalize_hand_value(raw: float, open_value: float, close_value: float) -> float:
    if open_value == close_value:
        return 0.0
    value = (open_value - raw) / (open_value - close_value)
    return float(max(0.0, min(1.0, value)))


def joint_state_to_vector(msg: Any) -> np.ndarray | None:
    if len(msg.name) != len(msg.position):
        return None

    positions = dict(zip(msg.name, msg.position, strict=False))
    try:
        return np.asarray([float(positions[name]) for name in JOINT_NAMES], dtype=np.float32)
    except KeyError:
        return None


def pose_array_to_action(
    msg: Any,
    left_pose_index: int,
    right_pose_index: int,
    left_gripper: float,
    right_gripper: float,
) -> np.ndarray | None:
    poses = getattr(msg, "poses", None)
    if poses is None or len(poses) <= max(left_pose_index, right_pose_index):
        return None

    values = (
        pose_to_values(poses[left_pose_index])
        + pose_to_values(poses[right_pose_index])
        + [left_gripper, right_gripper]
    )
    return np.asarray(values, dtype=np.float32)


def pair_direct_cmd_actions(
    left_cmds: list[TimedValue],
    right_cmds: list[TimedValue],
    hand_states: list[TimedValue],
    max_pair_age_s: float,
) -> list[TimedValue]:
    actions: list[TimedValue] = []
    right_times = [item.t for item in right_cmds]
    right_idx = 0

    for left in left_cmds:
        while right_idx + 1 < len(right_times) and right_times[right_idx + 1] <= left.t:
            right_idx += 1

        candidates = []
        if right_idx < len(right_cmds):
            candidates.append(right_cmds[right_idx])
        if right_idx + 1 < len(right_cmds):
            candidates.append(right_cmds[right_idx + 1])

        if not candidates:
            continue

        right = min(candidates, key=lambda item: abs(item.t - left.t))
        if abs(right.t - left.t) > max_pair_age_s:
            continue

        hand = latest_at_or_before(hand_states, left.t, math.inf)
        left_gripper, right_gripper = (0.0, 0.0)
        if hand.value is not None:
            left_gripper, right_gripper = hand.value

        values = (
            pose_to_values(left.value.pose)
            + pose_to_values(right.value.pose)
            + [left_gripper, right_gripper]
        )
        actions.append(TimedValue(left.t, np.asarray(values, dtype=np.float32)))

    return actions


def decode_image(msg: Any, width: int, height: int, rgb: bool = True) -> np.ndarray | None:
    data = np.frombuffer(msg.data, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        return None

    if rgb:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    if width > 0 and height > 0 and (image.shape[1] != width or image.shape[0] != height):
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)

    return np.asarray(image, dtype=np.uint8)


def latest_at_or_before(values: list[TimedValue], t: float, max_age_s: float) -> NearestResult:
    if not values:
        return NearestResult(None, None)

    lo = 0
    hi = len(values)
    while lo < hi:
        mid = (lo + hi) // 2
        if values[mid].t <= t:
            lo = mid + 1
        else:
            hi = mid

    if lo == 0:
        candidate = values[0]
    else:
        candidate = values[lo - 1]

    age_s = abs(t - candidate.t)
    if age_s > max_age_s:
        return NearestResult(None, age_s)
    return NearestResult(candidate.value, age_s)


def nearest(values: list[TimedValue], t: float, max_age_s: float) -> NearestResult:
    if not values:
        return NearestResult(None, None)

    lo = 0
    hi = len(values)
    while lo < hi:
        mid = (lo + hi) // 2
        if values[mid].t < t:
            lo = mid + 1
        else:
            hi = mid

    candidates = []
    if lo < len(values):
        candidates.append(values[lo])
    if lo > 0:
        candidates.append(values[lo - 1])
    candidate = min(candidates, key=lambda item: abs(item.t - t))

    age_s = abs(t - candidate.t)
    if age_s > max_age_s:
        return NearestResult(None, age_s)
    return NearestResult(candidate.value, age_s)


def get_msg_time_ns(topic: str, msg: Any, bag_time_ns: int, prefer_header_stamp: bool) -> int:
    if prefer_header_stamp and hasattr(msg, "header"):
        stamp = getattr(msg.header, "stamp", None)
        if stamp is not None and (stamp.sec or stamp.nanosec):
            return stamp_to_ns(stamp)
    return bag_time_ns


def discover_bags(bag_dir: Path, bag_glob: str, limit: int | None) -> list[Path]:
    if (bag_dir / "metadata.yaml").is_file():
        bags = [bag_dir]
    else:
        bags = sorted(path for path in bag_dir.glob(bag_glob) if (path / "metadata.yaml").is_file())
    return bags[:limit] if limit else bags


def normalized_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def load_previous_converted_bags(output_root: Path) -> set[str]:
    report_path = output_root / "meta/rosbag_conversion.json"
    if not report_path.is_file():
        return set()

    try:
        with report_path.open("r", encoding="utf-8") as f:
            report = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("Could not read previous conversion report %s: %s", report_path, exc)
        return set()

    converted = {normalized_path(path) for path in report.get("converted_bag_paths", [])}
    converted.update(
        normalized_path(item["bag"])
        for item in report.get("bags", [])
        if item.get("status") == "converted" and item.get("bag")
    )
    return converted


def default_bag_dir() -> Path:
    base_dir = Path.home() / "aibot2/rosbags"
    today_dir = base_dir / f"{datetime.now():%Y-%m-%d}"
    if today_dir.is_dir():
        return today_dir

    if base_dir.is_dir():
        dated_dirs = sorted(
            path
            for path in base_dir.iterdir()
            if path.is_dir()
            and len(path.name) == 10
            and path.name[4] == "-"
            and path.name[7] == "-"
            and path.name.replace("-", "").isdigit()
        )
        if dated_dirs:
            return dated_dirs[-1]

    return today_dir


def read_bag(
    bag: Path,
    *,
    camera_topics: dict[str, str],
    action_topic: str,
    joint_state_topic: str,
    hand_state_topic: str,
    direct_left_topic: str,
    direct_right_topic: str,
    action_source: str,
    left_pose_index: int,
    right_pose_index: int,
    hand_left_index: int,
    hand_right_index: int,
    hand_open_value: float,
    hand_close_value: float,
    width: int,
    height: int,
    prefer_header_stamp: bool,
    direct_pair_max_age_s: float,
) -> BagData:
    reader = SequentialReader()
    reader.open(
        StorageOptions(uri=str(bag), storage_id="sqlite3"),
        ConverterOptions(input_serialization_format="cdr", output_serialization_format="cdr"),
    )

    topic_types = {topic.name: topic.type for topic in reader.get_all_topics_and_types()}
    msg_classes = {
        topic: get_message(msg_type)
        for topic, msg_type in topic_types.items()
        if topic
        in {
            *camera_topics.values(),
            action_topic,
            joint_state_topic,
            hand_state_topic,
            direct_left_topic,
            direct_right_topic,
        }
    }

    bag_data = BagData(bag=bag, images={name: [] for name in camera_topics})
    left_gripper = 0.0
    right_gripper = 0.0
    direct_left: list[TimedValue] = []
    direct_right: list[TimedValue] = []

    while reader.has_next():
        topic, serialized, bag_time_ns = reader.read_next()
        if topic not in msg_classes:
            continue

        msg = deserialize_message(serialized, msg_classes[topic])
        t_ns = get_msg_time_ns(topic, msg, bag_time_ns, prefer_header_stamp)

        if bag_data.start_ns is None:
            bag_data.start_ns = t_ns
        bag_data.start_ns = min(bag_data.start_ns, t_ns)
        bag_data.end_ns = t_ns if bag_data.end_ns is None else max(bag_data.end_ns, t_ns)

        if topic == joint_state_topic:
            state = joint_state_to_vector(msg)
            if state is not None:
                bag_data.states.append(TimedValue(t=0.0, value=(t_ns, state)))
        elif topic == hand_state_topic:
            try:
                left_raw = float(msg.data[hand_left_index])
                right_raw = float(msg.data[hand_right_index])
            except (IndexError, TypeError, ValueError):
                continue
            left_gripper = normalize_hand_value(left_raw, hand_open_value, hand_close_value)
            right_gripper = normalize_hand_value(right_raw, hand_open_value, hand_close_value)
            bag_data.hand_states.append(TimedValue(t=0.0, value=(t_ns, (left_gripper, right_gripper))))
        elif topic == action_topic and action_source in {"auto", "control"}:
            action = pose_array_to_action(
                msg,
                left_pose_index=left_pose_index,
                right_pose_index=right_pose_index,
                left_gripper=left_gripper,
                right_gripper=right_gripper,
            )
            if action is not None:
                bag_data.actions.append(TimedValue(t=0.0, value=(t_ns, action)))
        elif topic == direct_left_topic and action_source in {"auto", "direct"}:
            direct_left.append(TimedValue(t=0.0, value=(t_ns, msg)))
        elif topic == direct_right_topic and action_source in {"auto", "direct"}:
            direct_right.append(TimedValue(t=0.0, value=(t_ns, msg)))
        else:
            camera_name = next((name for name, cam_topic in camera_topics.items() if cam_topic == topic), None)
            if camera_name is not None:
                image = decode_image(msg, width=width, height=height)
                if image is not None:
                    bag_data.images[camera_name].append(TimedValue(t=0.0, value=(t_ns, image)))

    if bag_data.start_ns is None:
        return bag_data

    bag_data.states = [
        TimedValue(ns_to_s(t_ns, bag_data.start_ns), state) for _, (t_ns, state) in enumerate_tv(bag_data.states)
    ]
    bag_data.hand_states = [
        TimedValue(ns_to_s(t_ns, bag_data.start_ns), value)
        for _, (t_ns, value) in enumerate_tv(bag_data.hand_states)
    ]
    bag_data.actions = [
        TimedValue(ns_to_s(t_ns, bag_data.start_ns), action) for _, (t_ns, action) in enumerate_tv(bag_data.actions)
    ]
    for camera_name, images in bag_data.images.items():
        bag_data.images[camera_name] = [
            TimedValue(ns_to_s(t_ns, bag_data.start_ns), image) for _, (t_ns, image) in enumerate_tv(images)
        ]

    if action_source == "direct" or (action_source == "auto" and not bag_data.actions):
        direct_left = [
            TimedValue(ns_to_s(t_ns, bag_data.start_ns), msg) for _, (t_ns, msg) in enumerate_tv(direct_left)
        ]
        direct_right = [
            TimedValue(ns_to_s(t_ns, bag_data.start_ns), msg) for _, (t_ns, msg) in enumerate_tv(direct_right)
        ]
        bag_data.actions = pair_direct_cmd_actions(
            direct_left,
            direct_right,
            bag_data.hand_states,
            max_pair_age_s=direct_pair_max_age_s,
        )

    bag_data.states.sort(key=lambda item: item.t)
    bag_data.actions.sort(key=lambda item: item.t)
    bag_data.hand_states.sort(key=lambda item: item.t)
    for images in bag_data.images.values():
        images.sort(key=lambda item: item.t)

    return bag_data


def enumerate_tv(values: list[TimedValue]):
    for i, item in enumerate(values):
        yield i, item.value


def build_features_from_reference(
    reference_root: Path | None,
    fps: int,
    width: int,
    height: int,
    camera_names: list[str],
) -> dict[str, dict]:
    if reference_root is not None:
        info_path = reference_root / "meta/info.json"
        if info_path.is_file():
            with info_path.open("r", encoding="utf-8") as f:
                info = json.load(f)
            features = {
                key: value
                for key, value in info["features"].items()
                if key
                not in {
                    "timestamp",
                    "frame_index",
                    "episode_index",
                    "index",
                    "task_index",
                }
            }
            return features
        LOGGER.warning("Reference dataset metadata not found: %s", info_path)

    del fps
    features = {
        "action": {
            "dtype": "float32",
            "shape": (len(ACTION_NAMES),),
            "names": ACTION_NAMES,
        },
        "observation.state": {
            "dtype": "float32",
            "shape": (len(STATE_NAMES),),
            "names": STATE_NAMES,
        },
    }
    for camera_name in camera_names:
        features[f"observation.images.{camera_name}"] = {
            "dtype": "video",
            "shape": (height, width, 3),
            "names": ["height", "width", "channels"],
        }
    return features


def normalize_feature_shapes(features: dict[str, dict]) -> dict[str, dict]:
    normalized = {}
    for key, value in features.items():
        normalized[key] = dict(value)
        if isinstance(normalized[key].get("shape"), list):
            normalized[key]["shape"] = tuple(normalized[key]["shape"])
    return normalized


def set_camera_storage(features: dict[str, dict], *, use_video: bool) -> dict[str, dict]:
    updated = {}
    for key, value in features.items():
        updated[key] = dict(value)
        if key.startswith("observation.images."):
            updated[key]["dtype"] = "video" if use_video else "image"
            if not use_video:
                updated[key].pop("info", None)
    return updated


def infer_width_height(features: dict[str, dict], width: int | None, height: int | None) -> tuple[int, int]:
    if width and height:
        return width, height

    for key, ft in features.items():
        if key.startswith("observation.images."):
            shape = ft["shape"]
            return int(width or shape[1]), int(height or shape[0])

    return int(width or 320), int(height or 240)


def parse_camera_topics(args: argparse.Namespace, features: dict[str, dict]) -> dict[str, str]:
    camera_names = [
        key.removeprefix("observation.images.")
        for key in features
        if key.startswith("observation.images.")
    ]
    if not camera_names:
        camera_names = list(DEFAULT_CAMERA_TOPICS)

    topics = {}
    for camera_name in camera_names:
        env_name = f"AIBOT2_{camera_name.upper()}_TOPIC"
        topics[camera_name] = os.getenv(env_name, DEFAULT_CAMERA_TOPICS.get(camera_name, ""))

    for override in args.camera_topic:
        if "=" not in override:
            raise ValueError(f"--camera-topic must be NAME=TOPIC, got: {override}")
        name, topic = override.split("=", 1)
        topics[name.strip()] = topic.strip()

    missing = [name for name, topic in topics.items() if not topic]
    if missing:
        raise ValueError(f"No ROS topic configured for cameras: {missing}")

    return topics


def prepare_output_root(root: Path, overwrite: bool, resume: bool) -> Path:
    if not root.exists():
        return root

    if overwrite:
        shutil.rmtree(root)
        return root

    if resume:
        return root

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return root.with_name(f"{root.name}_{timestamp}")


def create_or_open_dataset(
    *,
    repo_id: str,
    root: Path,
    features: dict[str, dict],
    fps: int,
    robot_type: str,
    resume: bool,
    image_writer_processes: int,
    image_writer_threads: int,
    video: bool,
) -> LeRobotDataset:
    if resume and root.exists():
        dataset = LeRobotDataset(repo_id=repo_id, root=root)
        dataset.start_image_writer(image_writer_processes, image_writer_threads)
        return dataset

    return LeRobotDataset.create(
        repo_id=repo_id,
        root=root,
        fps=fps,
        features=features,
        robot_type=robot_type,
        use_videos=video,
        image_writer_processes=image_writer_processes,
        image_writer_threads=image_writer_threads,
    )


def add_bag_episode(
    dataset: LeRobotDataset,
    bag_data: BagData,
    *,
    fps: int,
    camera_topics: dict[str, str],
    task: str,
    max_state_age_s: float,
    max_action_age_s: float,
    max_image_age_s: float,
    min_frames: int,
) -> dict[str, Any]:
    if bag_data.start_ns is None or bag_data.end_ns is None:
        return {"bag": str(bag_data.bag), "status": "skipped", "reason": "empty bag"}

    duration_s = max(0.0, (bag_data.end_ns - bag_data.start_ns) / 1e9)
    frame_count = int(math.floor(duration_s * fps)) + 1

    if not bag_data.states:
        return {"bag": str(bag_data.bag), "status": "skipped", "reason": "missing joint states"}
    if not bag_data.actions:
        return {"bag": str(bag_data.bag), "status": "skipped", "reason": "missing actions"}

    for camera_name in camera_topics:
        if not bag_data.images.get(camera_name):
            return {
                "bag": str(bag_data.bag),
                "status": "skipped",
                "reason": f"missing camera frames for {camera_name}",
            }

    ages: dict[str, list[float]] = {
        "state": [],
        "action": [],
        **{camera_name: [] for camera_name in camera_topics},
    }
    skipped_frames = 0
    written_frames = 0

    for frame_idx in range(frame_count):
        t = frame_idx / fps
        state = latest_at_or_before(bag_data.states, t, max_state_age_s)
        action = latest_at_or_before(bag_data.actions, t, max_action_age_s)

        if state.value is None or action.value is None:
            skipped_frames += 1
            continue

        frame = {
            "observation.state": state.value,
            "action": action.value,
            "task": task,
        }
        ages["state"].append(float(state.age_s or 0.0))
        ages["action"].append(float(action.age_s or 0.0))

        missing_image = False
        for camera_name in camera_topics:
            image = nearest(bag_data.images[camera_name], t, max_image_age_s)
            if image.value is None:
                missing_image = True
                break
            frame[f"observation.images.{camera_name}"] = image.value
            ages[camera_name].append(float(image.age_s or 0.0))

        if missing_image:
            skipped_frames += 1
            continue

        dataset.add_frame(frame)
        written_frames += 1

    if written_frames < min_frames:
        dataset.clear_episode_buffer(delete_images=True)
        return {
            "bag": str(bag_data.bag),
            "status": "skipped",
            "reason": f"only {written_frames} usable frames",
            "duration_s": duration_s,
            "candidate_frames": frame_count,
            "skipped_frames": skipped_frames,
        }

    dataset.save_episode()

    return {
        "bag": str(bag_data.bag),
        "status": "converted",
        "duration_s": duration_s,
        "frames": written_frames,
        "candidate_frames": frame_count,
        "skipped_frames": skipped_frames,
        "max_age_s": {key: max(values) if values else None for key, values in ages.items()},
        "mean_age_s": {key: float(np.mean(values)) if values else None for key, values in ages.items()},
    }


def write_conversion_report(output_root: Path, report: dict[str, Any]) -> None:
    meta_dir = output_root / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    with (meta_dir / "rosbag_conversion.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "bag_dir",
        nargs="?",
        default=os.getenv("AIBOT2_ROSBAG_DIR"),
        help="ROS bag directory, or a parent directory containing bag directories.",
    )
    parser.add_argument("--bag-glob", default=os.getenv("AIBOT2_ROSBAG_GLOB", "alphabot2_bag_*"))
    parser.add_argument("--limit", type=int, default=None, help="Convert only the first N bags.")
    parser.add_argument("--repo-id", default=os.getenv("LEROBOT_DATASET_REPO_ID", DEFAULT_REPO_ID))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(os.getenv("LEROBOT_DATASET_ROOT", str(DEFAULT_OUTPUT_ROOT))).expanduser(),
    )
    parser.add_argument(
        "--reference-dataset-root",
        type=Path,
        default=Path(os.getenv("AIBOT2_REFERENCE_DATASET_ROOT", str(DEFAULT_REFERENCE_ROOT))).expanduser(),
        help="Existing LeRobot dataset whose feature schema should be reused.",
    )
    parser.add_argument("--task", default=os.getenv("LEROBOT_SINGLE_TASK", DEFAULT_TASK))
    parser.add_argument("--fps", type=int, default=int(os.getenv("LEROBOT_DATASET_FPS", "15")))
    parser.add_argument("--width", type=int, default=int(os.getenv("LEROBOT_CAMERA_WIDTH", "0")) or None)
    parser.add_argument("--height", type=int, default=int(os.getenv("LEROBOT_CAMERA_HEIGHT", "0")) or None)
    parser.add_argument("--robot-type", default="aibot2")
    parser.add_argument(
        "--action-source",
        choices=["auto", "control", "direct"],
        default=os.getenv("AIBOT2_ACTION_SOURCE", "auto"),
        help="'control' uses /control_poses_target; 'direct' pairs left/right Cartesian command topics.",
    )
    parser.add_argument("--action-topic", default=os.getenv("AIBOT2_ACTION_TOPIC", "/control_poses_target"))
    parser.add_argument("--joint-state-topic", default=os.getenv("AIBOT2_JOINT_STATE_TOPIC", "/joint_states"))
    parser.add_argument("--hand-state-topic", default=os.getenv("AIBOT2_HAND_STATE_TOPIC", "/hand_states"))
    parser.add_argument(
        "--direct-left-topic",
        default=os.getenv("AIBOT2_DIRECT_LEFT_TOPIC", "/left_arm_cartesian_direct_cmd"),
    )
    parser.add_argument(
        "--direct-right-topic",
        default=os.getenv("AIBOT2_DIRECT_RIGHT_TOPIC", "/right_arm_cartesian_direct_cmd"),
    )
    parser.add_argument("--left-pose-index", type=int, default=int(os.getenv("AIBOT2_LEFT_POSE_INDEX", "0")))
    parser.add_argument("--right-pose-index", type=int, default=int(os.getenv("AIBOT2_RIGHT_POSE_INDEX", "1")))
    parser.add_argument("--hand-left-index", type=int, default=int(os.getenv("AIBOT2_HAND_LEFT_INDEX", "0")))
    parser.add_argument("--hand-right-index", type=int, default=int(os.getenv("AIBOT2_HAND_RIGHT_INDEX", "1")))
    parser.add_argument("--hand-open-value", type=float, default=float(os.getenv("AIBOT2_HAND_OPEN_VALUE", "800")))
    parser.add_argument("--hand-close-value", type=float, default=float(os.getenv("AIBOT2_HAND_CLOSE_VALUE", "0")))
    parser.add_argument("--camera-topic", action="append", default=[], help="Override camera topic as NAME=TOPIC.")
    parser.add_argument("--max-state-age-s", type=float, default=float(os.getenv("AIBOT2_MAX_STATE_AGE_S", "0.20")))
    parser.add_argument("--max-action-age-s", type=float, default=float(os.getenv("AIBOT2_MAX_ACTION_AGE_S", "0.20")))
    parser.add_argument("--max-image-age-s", type=float, default=float(os.getenv("AIBOT2_MAX_IMAGE_AGE_S", "0.20")))
    parser.add_argument("--direct-pair-max-age-s", type=float, default=0.05)
    parser.add_argument("--min-frames", type=int, default=5)
    parser.add_argument("--prefer-bag-time", action="store_true", help="Use bag receive time instead of header stamps.")
    parser.add_argument("--image-writer-processes", type=int, default=int(os.getenv("LEROBOT_NUM_IMAGE_WRITER_PROCESSES", "1")))
    parser.add_argument("--image-writer-threads", type=int, default=int(os.getenv("LEROBOT_NUM_IMAGE_WRITER_THREADS", "8")))
    parser.add_argument("--no-video", action="store_true", help="Store image files instead of mp4 videos.")
    parser.add_argument("--overwrite", action="store_true", help="Delete output root if it already exists.")
    parser.add_argument("--resume", action="store_true", help="Append episodes to an existing output root.")
    parser.add_argument("--reprocess", action="store_true", help="With --resume, convert bags even if the report says they were already converted.")
    parser.add_argument("--dry-run", action="store_true", help="Read bags and print summary without writing dataset.")
    parser.add_argument("--push-to-hub", action="store_true", default=os.getenv("LEROBOT_DATASET_PUSH", "false").lower() == "true")
    parser.add_argument("--private", action="store_true", default=os.getenv("LEROBOT_DATASET_PRIVATE", "false").lower() == "true")
    parser.add_argument("--log-level", default=os.getenv("LOGLEVEL", "INFO"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(levelname)s: %(message)s")

    if args.bag_dir is None:
        args.bag_dir = str(default_bag_dir())
    bag_dir = Path(args.bag_dir).expanduser()
    if not bag_dir.exists():
        LOGGER.error("Bag directory does not exist: %s", bag_dir)
        return 2

    features = normalize_feature_shapes(
        build_features_from_reference(
            args.reference_dataset_root,
            args.fps,
            args.width or 320,
            args.height or 240,
            list(DEFAULT_CAMERA_TOPICS),
        )
    )
    features = set_camera_storage(features, use_video=not args.no_video)
    width, height = infer_width_height(features, args.width, args.height)
    camera_topics = parse_camera_topics(args, features)

    output_root = prepare_output_root(args.output_root, overwrite=args.overwrite, resume=args.resume)
    bags = discover_bags(bag_dir, args.bag_glob, args.limit)
    if not bags:
        LOGGER.error("No ROS bag directories found under %s matching %s", bag_dir, args.bag_glob)
        return 2

    LOGGER.info("Source bags: %s (%d episode candidates)", bag_dir, len(bags))
    LOGGER.info("Output root: %s", output_root)
    LOGGER.info("Repo id: %s", args.repo_id)
    LOGGER.info("FPS: %d, image size: %dx%d, cameras: %s", args.fps, width, height, ", ".join(camera_topics))

    dataset = None
    previous_converted_bags = set()
    if args.resume and not args.reprocess:
        previous_converted_bags = load_previous_converted_bags(output_root)
        if previous_converted_bags:
            LOGGER.info("Will skip %d previously converted bag(s) from %s", len(previous_converted_bags), output_root)

    report: dict[str, Any] = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(bag_dir),
        "repo_id": args.repo_id,
        "output_root": str(output_root),
        "fps": args.fps,
        "image_size": {"width": width, "height": height},
        "camera_topics": camera_topics,
        "action_source": args.action_source,
        "previously_converted_bags": len(previous_converted_bags),
        "bags": [],
    }

    if not args.dry_run:
        dataset = create_or_open_dataset(
            repo_id=args.repo_id,
            root=output_root,
            features=features,
            fps=args.fps,
            robot_type=args.robot_type,
            resume=args.resume,
            image_writer_processes=args.image_writer_processes,
            image_writer_threads=args.image_writer_threads,
            video=not args.no_video,
        )

    converted = 0
    converted_bags = set(previous_converted_bags)
    for i, bag in enumerate(bags, start=1):
        bag_key = normalized_path(bag)
        if bag_key in previous_converted_bags:
            LOGGER.info("[%d/%d] Skipping previously converted %s", i, len(bags), bag.name)
            report["bags"].append(
                {
                    "bag": str(bag),
                    "status": "skipped",
                    "reason": "already converted in output dataset",
                }
            )
            continue

        LOGGER.info("[%d/%d] Reading %s", i, len(bags), bag.name)
        try:
            bag_data = read_bag(
                bag,
                camera_topics=camera_topics,
                action_topic=args.action_topic,
                joint_state_topic=args.joint_state_topic,
                hand_state_topic=args.hand_state_topic,
                direct_left_topic=args.direct_left_topic,
                direct_right_topic=args.direct_right_topic,
                action_source=args.action_source,
                left_pose_index=args.left_pose_index,
                right_pose_index=args.right_pose_index,
                hand_left_index=args.hand_left_index,
                hand_right_index=args.hand_right_index,
                hand_open_value=args.hand_open_value,
                hand_close_value=args.hand_close_value,
                width=width,
                height=height,
                prefer_header_stamp=not args.prefer_bag_time,
                direct_pair_max_age_s=args.direct_pair_max_age_s,
            )
            if args.dry_run:
                duration_s = 0.0
                if bag_data.start_ns is not None and bag_data.end_ns is not None:
                    duration_s = (bag_data.end_ns - bag_data.start_ns) / 1e9
                result = {
                    "bag": str(bag),
                    "status": "would_convert",
                    "duration_s": duration_s,
                    "state_messages": len(bag_data.states or []),
                    "action_messages": len(bag_data.actions or []),
                    "camera_messages": {
                        name: len(values) for name, values in (bag_data.images or {}).items()
                    },
                }
            else:
                assert dataset is not None
                result = add_bag_episode(
                    dataset,
                    bag_data,
                    fps=args.fps,
                    camera_topics=camera_topics,
                    task=args.task,
                    max_state_age_s=args.max_state_age_s,
                    max_action_age_s=args.max_action_age_s,
                    max_image_age_s=args.max_image_age_s,
                    min_frames=args.min_frames,
                )
                if result["status"] == "converted":
                    converted += 1
                    converted_bags.add(bag_key)
                    LOGGER.info("Converted %s: %d frames", bag.name, result["frames"])
                else:
                    LOGGER.warning("Skipped %s: %s", bag.name, result.get("reason", "unknown reason"))
            report["bags"].append(result)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            LOGGER.exception("Failed to convert %s", bag)
            report["bags"].append({"bag": str(bag), "status": "failed", "reason": str(exc)})

    report["converted_episodes"] = converted
    report["total_episode_candidates"] = len(bags)
    report["converted_bag_paths"] = sorted(converted_bags)

    if args.dry_run:
        print(json.dumps(report, indent=2))
        return 0

    assert dataset is not None
    dataset.finalize()
    dataset.stop_image_writer()
    write_conversion_report(output_root, report)
    LOGGER.info("Wrote conversion report: %s", output_root / "meta/rosbag_conversion.json")
    LOGGER.info("Converted %d/%d bags", converted, len(bags))

    if args.push_to_hub:
        LOGGER.info("Pushing dataset to Hugging Face Hub: %s", args.repo_id)
        dataset.push_to_hub(private=args.private)
        LOGGER.info("Done: https://huggingface.co/datasets/%s", args.repo_id)

    return 0 if converted > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
