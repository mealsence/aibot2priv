# Aibot2 combined dataset at 15 FPS

This document explains how to rebuild **`ases200q2/Aibot2_combined_pick_object_datasets_15fps`** from the curated rosbags in `~/aibot2/rosbags/Aibot2_combined_pick_object_datasets/`.

The 15 FPS dataset is the same as [`ases200q2/Aibot2_combined_pick_object_datasets`](https://huggingface.co/datasets/ases200q2/Aibot2_combined_pick_object_datasets) (398 episodes, same task, same action/state/camera schema) except that frames are sampled at **15 Hz** instead of **25 Hz**.

| | Original (25 FPS) | 15 FPS |
|---|------------------|--------|
| Hub repo | `ases200q2/Aibot2_combined_pick_object_datasets` | `ases200q2/Aibot2_combined_pick_object_datasets_15fps` |
| Episodes | 398 | 398 |
| Total frames | 133,581 | 80,210 (~60%) |
| Training/eval FPS | 25 | 15 |

---

## Rosbag source folder

The folder `~/aibot2/rosbags/Aibot2_combined_pick_object_datasets/` contains the **398 rosbags** that were used for the original combined dataset (not every bag under `~/aibot2/rosbags/`).

```
~/aibot2/rosbags/Aibot2_combined_pick_object_datasets/
├── 2026-05-19/          # 197 bags → Hub 2026-05-19 rosbag dataset
├── 2026-05-18/          # 201 bags → Hub v1 rosbag dataset
├── included_bags.txt    # full list of source paths
└── excluded_bags_2026-05-19.txt   # 12 bags converted locally but not in combined
```

The converter only looks **one directory level** for `alphabot2_bag_*`, so you must run conversion **per date subfolder** (`2026-05-19`, then `2026-05-18`).

---

## What `REF` vs `--fps` mean

| Variable / flag | Role |
|-----------------|------|
| **`REF`** (`--reference-dataset-root`) | Copies **feature schema** only (action names, joint names, camera keys, 240×320) from the 25 FPS combined dataset. It does **not** set FPS. |
| **`--fps 15`** / `LEROBOT_DATASET_FPS=15` | Sets **sampling rate**, episode frame counts, and `meta/info.json` → `"fps": 15`. |

Using the 25 FPS combined dataset as `REF` is correct so the new dataset stays compatible with existing training configs.

---

## Prerequisites

```bash
cd ~/lerobot-ros-agent-aibot2
source .venv/bin/activate
source /opt/ros/humble/setup.bash
hf auth login   # if pushing to Hub
```

---

## Convert (local dataset)

```bash
cd ~/lerobot-ros-agent-aibot2
source .venv/bin/activate
source /opt/ros/humble/setup.bash

export LEROBOT_DATASET_FPS=15
OUT=~/lerobot_datasets/Aibot2_combined_pick_object_datasets_15fps
REPO=ases200q2/Aibot2_combined_pick_object_datasets_15fps
REF=~/.cache/huggingface/lerobot/ases200q2/Aibot2_combined_pick_object_datasets
BASE=~/aibot2/rosbags/Aibot2_combined_pick_object_datasets

for day in 2026-05-19 2026-05-18; do
  ./vla/DATA_COLLECTION/convert_aibot2_rosbags.sh "$BASE/$day" \
    --fps 15 \
    --output-root "$OUT" \
    --repo-id "$REPO" \
    --reference-dataset-root "$REF" \
    --resume
done
```

- **`--resume`**: skips bags already listed as `converted` in `$OUT/meta/rosbag_conversion.json`.
- **`--reprocess`**: with `--resume`, re-convert bags that were already converted.
- **`--overwrite`**: delete `$OUT` and start fresh (do not use with `--resume` on a finished dataset).
- **Test one bag**: add `--limit 1` and use `--overwrite` on an empty test output dir.

Check FPS after conversion:

```bash
python3 -c "import json; print(json.load(open('$OUT/meta/info.json'))['fps'])"
# Expected: 15
```

---

## Push to Hugging Face Hub

Push **after both days** are converted so the upload includes all 398 episodes. Only the last command needs `--push-to-hub`:

```bash
cd ~/lerobot-ros-agent-aibot2
source .venv/bin/activate
source /opt/ros/humble/setup.bash

export LEROBOT_DATASET_FPS=15
OUT=~/lerobot_datasets/Aibot2_combined_pick_object_datasets_15fps
REPO=ases200q2/Aibot2_combined_pick_object_datasets_15fps
REF=~/.cache/huggingface/lerobot/ases200q2/Aibot2_combined_pick_object_datasets
BASE=~/aibot2/rosbags/Aibot2_combined_pick_object_datasets

./vla/DATA_COLLECTION/convert_aibot2_rosbags.sh "$BASE/2026-05-19" \
  --fps 15 --output-root "$OUT" --repo-id "$REPO" \
  --reference-dataset-root "$REF" --resume

./vla/DATA_COLLECTION/convert_aibot2_rosbags.sh "$BASE/2026-05-18" \
  --fps 15 --output-root "$OUT" --repo-id "$REPO" \
  --reference-dataset-root "$REF" --resume --push-to-hub
```

Add `--private` if the Hub dataset should be private.

Hub URL: https://huggingface.co/datasets/ases200q2/Aibot2_combined_pick_object_datasets_15fps

---

## Train on the 15 FPS dataset

```bash
cd ~/lerobot-ros-agent-aibot2/vla/TRAIN
LEROBOT_DATASET_REPO_ID=ases200q2/Aibot2_combined_pick_object_datasets_15fps \
  ./train_aibot2.sh act
```

Use the same FPS at **eval** (`LEROBOT_DATASET_FPS=15` in eval scripts) so control timing matches training.

---

## Conversion report

Per-bag status, frame counts, and sync ages are written to:

`$OUT/meta/rosbag_conversion.json`

If you run the loop twice with `--resume`, the report file reflects the **last** run’s bag list unless you merge reports manually; `meta/info.json` and episode parquet files still reflect the full dataset on disk.

---

## Related scripts

| Script | Purpose |
|--------|---------|
| `convert_aibot2_rosbags.sh` | Shell wrapper (ROS + venv + Python converter) |
| `convert_aibot2_rosbags.py` | ROS2 bag → LeRobot v3 dataset |

See also the general rosbag section in [README.md](./README.md).
