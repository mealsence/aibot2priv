# Data Collection

This directory contains scripts for collecting teleoperation datasets with the Franka Panda robot. Data can be collected in **simulation** (Isaac Sim) or on a **real robot**.

---

## Quick Start

### Simulation (Isaac Sim)

```bash
# Terminal 1: Start Isaac Sim, load USD, run simulation
# Terminal 2: Launch ROS2 controller + SpaceMouse
./launch_position_control_tmux.sh

# Terminal 3: Record data
./DATA_COLLECTION/record_spacemouse_ee_fast.sh
```

### Real Robot

**Option A — Cartesian velocity control** (recommended for real robot):

```bash
# Terminal 1 (on control PC): Franka with cartesian_twist_controller
ros2 launch franka_bringup cartesian_twist_controller.launch.py robot_ip:=192.168.1.101

# Terminal 2 (on workstation): SpaceMouse driver
ros2 run spacenav spacenav_node

# Terminal 3 (on workstation): RealSense camera (required for recording)
cd REAL_ROBOT && ./launch_realsense_camera.sh

# Terminal 4 (on workstation): Record data
./DATA_COLLECTION/record_spacemouse_cartesian_vel_real.sh
```

**Option B — Trajectory control**:

```bash
# Terminal 1 (on control PC): Franka bringup
ros2 launch franka_bringup franka.launch.py robot_ip:=192.168.1.101

# Terminal 2 (on workstation): SpaceMouse driver
ros2 run spacenav spacenav_node --ros-args -r /spacenav/joy:=/joy

# Terminal 3 (on workstation): RealSense cameras (optional)
cd REAL_ROBOT && ./launch_realsense_camera.sh

# Terminal 4 (on workstation): Record data
LEROBOT_ROBOT_TYPE=panda_ros ./DATA_COLLECTION/record_spacemouse_ee.sh
```

---

## Recording Scripts

| Script | Robot Type | Use Case |
|--------|------------|----------|
| `record_spacemouse_cartesian_vel_real.sh` | `panda_ros_cartesian` | Real robot; Cartesian velocity control, SpaceMouse teleop |
| `record_spacemouse_ee.sh` | `panda_ros` (trajectory) | Simulation or real robot; smooth motion, ~100ms latency |
| `record_spacemouse_ee_fast.sh` | `panda_ros_position` (position) | Simulation only; ultra-low latency (~15–20ms) |

### `record_spacemouse_cartesian_vel_real.sh`

- **Robot**: `panda_ros_cartesian` (CartesianTwistController)
- **Best for**: Real robot with Cartesian velocity control
- **Prerequisites**: Franka with `cartesian_twist_controller`, SpaceMouse, RealSense camera (`./REAL_ROBOT/launch_realsense_camera.sh`)
- **Default dataset**: `~/lerobot_datasets/Real_Panda_CartesianVel_SpaceMouse`

### `record_spacemouse_ee.sh`

- **Robot**: `panda_ros` (JointTrajectoryController)
- **Best for**: Real robot, or simulation when smooth motion is preferred
- **Default dataset**: `~/lerobot_datasets/spacemouse-ee-teleop`
- **Default repo**: `ases200q2/Isaac_Panda_SpaceMouse_EE`

### `record_spacemouse_ee_fast.sh`

- **Robot**: `panda_ros_position` (JointGroupPositionController)
- **Best for**: Isaac Sim only (position control can be unstable on real hardware)
- **Default dataset**: `~/lerobot_datasets/Isaac_Panda_PickCube_SpaceMouse_EE_fast_100episodes`
- **Default repo**: `ases200q2/Isaac_Panda_PickCube_SpaceMouse_EE_fast_100episodes`
- **Tuning**: Exposes SpaceMouse sensitivity (`linear_step_m`, `dead_zone`, `gripper_step`)

---

## Prerequisites

### Simulation

1. **Isaac Sim** running with the Panda USD scene
2. **ROS2 workspace** built: `cd isaac_franka_moveit_perception && colcon build --symlink-install`
3. **SpaceMouse** connected (3Dconnexion)
4. **Python environment** with lerobot (conda `lerobot-ros-isaac` / `lerobot-ros` or `.venv`)

### Real Robot

1. **Franka bringup** running on the control PC
2. **ROS2** on the workstation, able to reach the control PC
3. **SpaceMouse** connected
4. **`panda_ros`** robot type (trajectory controller) — see [REAL_ROBOT/SIM_REAL_CONTROLLER_ALIGNMENT_REPORT.md](../REAL_ROBOT/SIM_REAL_CONTROLLER_ALIGNMENT_REPORT.md)

---

## Environment Variables

Override defaults by setting these before running the scripts:

| Variable | Description | Example |
|----------|-------------|---------|
| `LEROBOT_ROBOT_TYPE` | Robot type | `panda_ros` or `panda_ros_position` |
| `LEROBOT_DATASET_ROOT` | Base directory for datasets | `~/lerobot_datasets/my_task` |
| `LEROBOT_DATASET_REPO_ID` | HuggingFace repo ID | `username/my_dataset` |
| `LEROBOT_SINGLE_TASK` | Task description | `Pick cube from table` |
| `LEROBOT_NUM_EPISODES` | Number of episodes | `50` |
| `LEROBOT_EPISODE_TIME_S` | Episode duration (seconds) | `60` |
| `LEROBOT_RESET_TIME_S` | Reset period between episodes | `60` |
| `LEROBOT_DATASET_FPS` | Recording FPS | `30` |
| `LEROBOT_RESUME` | Resume existing dataset | `true` or `false` |
| `LEROBOT_DATASET_PUSH` | Push to HuggingFace Hub | `true` or `false` |
| `LEROBOT_DATASET_VIDEO` | Encode video | `true` or `false` |
| `LEROBOT_DISPLAY_DATA` | Show camera feed | `true` or `false` |

### RealSense Multi-Camera (when using RealSense cameras)

| Variable | Description | Example |
|----------|-------------|---------|
| `LEROBOT_REALSENSE_CONFIG_FILE` | Path to camera config YAML | `REAL_ROBOT/camera_config.yaml` |
| `LEROBOT_REALSENSE_CAMERAS` | JSON camera configuration | `'{"camera_1": {"serial": "123"}}'` |
| `LEROBOT_REALSENSE_DEFAULT_WIDTH` | Camera width | `640` |
| `LEROBOT_REALSENSE_DEFAULT_HEIGHT` | Camera height | `480` |
| `LEROBOT_REALSENSE_DEFAULT_FPS` | Camera FPS | `30` |

For more RealSense camera setup details, see [REAL_ROBOT/CAMERA_SETUP.md](../REAL_ROBOT/CAMERA_SETUP.md).
When `LEROBOT_CAMERA_TOPICS` and `LEROBOT_CAMERA_TOPIC` are not set, `record_spacemouse_ee.sh` auto-discovers `/rgb/camera_*` topics from ROS2.

### SpaceMouse Tuning (record_spacemouse_ee_fast.sh)

| Variable | Description | Default |
|----------|-------------|---------|
| `LEROBOT_TELEOP_LINEAR_STEP_M` | Movement step (meters) | `0.01` |
| `LEROBOT_TELEOP_DEAD_ZONE` | Input dead zone | `0.01` |
| `LEROBOT_TELEOP_GRIPPER_STEP` | Gripper step | `0.001` |

### Camera (when using panda_ros / panda_ros_position)

| Variable | Description | Default |
|----------|-------------|---------|
| `LEROBOT_CAMERA_TOPIC` | ROS2 image topic | `/rgb/camera_1` |
| `LEROBOT_CAMERA_TOPICS` | Comma-separated ROS2 topics for multi-camera recording | `/rgb/camera_1,/rgb/camera_2` |
| `LEROBOT_CAMERA_WIDTH` | Image width | `640` |
| `LEROBOT_CAMERA_HEIGHT` | Image height | `480` |
| `LEROBOT_CAMERA_FPS` | Camera FPS | `30` |

---

## Examples

### Basic recording (simulation)

```bash
./DATA_COLLECTION/record_spacemouse_ee_fast.sh
```

### Custom task and episodes

```bash
LEROBOT_SINGLE_TASK="Stack red cube on blue cube" \
LEROBOT_NUM_EPISODES=20 \
./DATA_COLLECTION/record_spacemouse_ee.sh
```

### Real robot with custom dataset path

```bash
LEROBOT_ROBOT_TYPE=panda_ros \
LEROBOT_DATASET_ROOT=~/lerobot_datasets/real_panda_pick_cube \
LEROBOT_DATASET_REPO_ID=myuser/real_panda_pick_cube \
./DATA_COLLECTION/record_spacemouse_ee.sh
```

### Resume existing dataset

```bash
LEROBOT_RESUME=true ./DATA_COLLECTION/record_spacemouse_ee.sh
```

### Pass extra CLI arguments

```bash
./DATA_COLLECTION/record_spacemouse_ee.sh --teleop.config.linear_step_m=0.005
```

---

## Workflow During Recording

1. **Episode phase** (default 60s): Policy or teleop controls the robot. SpaceMouse moves the end-effector; buttons control the gripper.
2. **Reset phase** (default 60s): Use SpaceMouse to reposition objects and the robot for the next episode.
3. Episodes repeat until `LEROBOT_NUM_EPISODES` is reached.

---

## Data Stored

- **Observations**: Joint states (`panda_joint*.pos`), gripper state, camera images
- **Actions**: Joint targets from IK (`panda_joint*.pos`, `gripper.pos`)
- **Metadata**: Task description, episode boundaries, timestamps

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Robot not moving | Check ROS2 topics: `ros2 topic list \| grep panda` |
| SpaceMouse not detected | Run `ros2 run spacenav spacenav_node` with remap: `-r /spacenav/joy:=/joy` |
| Real robot jerky/unstable | Use `LEROBOT_ROBOT_TYPE=panda_ros` (trajectory controller) |
| Camera not found | Set `LEROBOT_CAMERA_TOPIC` to your image topic |
| Slow recording / robot lag | Use `record_spacemouse_ee_fast.sh` in sim; tune `NUM_IMAGE_WRITER_THREADS` |

---

## Related Documentation

- [HOW TO RUN](../HOW%20TO%20RUN) — Teleoperation options and parameters
- [REAL_ROBOT/README.md](../REAL_ROBOT/README.md) — Real robot setup
- [REAL_ROBOT/SIM_REAL_CONTROLLER_ALIGNMENT_REPORT.md](../REAL_ROBOT/SIM_REAL_CONTROLLER_ALIGNMENT_REPORT.md) — Controller compatibility (sim vs real)
