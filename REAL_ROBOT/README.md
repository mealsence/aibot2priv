# REAL_ROBOT — Real Franka Panda Control

Scripts for controlling a **real Franka Panda** robot via `franka_ros2`.

## Network Setup

| Machine | IP | Role |
|---|---|---|
| **Control PC** | `192.168.1.2` | Runs `franka_ros2` bringup (connected to robot via Ethernet) |
| **Workstation** | this PC | Runs these scripts, sends ROS2 commands over network |
| **Robot** | `192.168.1.101` | Franka Panda arm (FCI interface) |

## Prerequisites

### 1. On the Control PC (192.168.1.2)

Start the Cartesian twist controller:
```bash
source /home/franka/franka_ros2_i2r/install/setup.bash
ros2 launch franka_bringup cartesian_twist_controller.launch.py robot_ip:=192.168.1.101
```

### 2. On this Workstation

Ensure ROS2 is sourced and can communicate with the control PC:
```bash
source /opt/ros/humble/setup.bash

# Verify communication (should see topics from the control PC)
ros2 topic list | grep -E "joint_states|franka|panda"
```

> **Note**: Both machines must be on the same network and use the same `ROS_DOMAIN_ID` (default: 0).

## Usage

### Check Available Topics (Safe — No Movement)
```bash
python move_to_joint_angles.py --check-topics
```

### Dry Run (Safe — No Movement)
```bash
python move_to_joint_angles.py --dry-run
```

### Move to Default Target Angles
```bash
python move_to_joint_angles.py
# Target: [-0.159, 0.302, -0.093, -2.255, 0.047, 2.555, 0.498]
```

### Move to Custom Angles
```bash
python move_to_joint_angles.py --joints -0.034 -0.436 -0.076 -2.581 -0.038 2.145 0.703
```

### Skip Confirmation
```bash
python move_to_joint_angles.py --no-confirm --duration 5
```

### SpaceMouse Teleoperation — Cartesian velocity (no IK)

Direct Cartesian velocity teleoperation. No IK — the SpaceMouse twist is scaled and sent straight to libfranka's Cartesian velocity interface. Simpler and lower-latency, but requires `CartesianTwistController` from `franka_ros2_i2r`.

**Control PC** — switch to `cartesian_twist_controller.launch.py`:
```bash
# On control PC (192.168.1.2):
source /home/franka/franka_ros2_i2r/install/setup.bash
ros2 launch franka_bringup cartesian_twist_controller.launch.py robot_ip:=192.168.1.101
```

Verify the controller is active:
```bash
ros2 control list_controllers
# Expected: cartesian_twist_controller  [active]
```

**Workstation** — start SpaceMouse driver (no remap needed, use default topic):
```bash
ros2 run spacenav spacenav_node
```

**Workstation** — run the bridge:
```bash
cd REAL_ROBOT && python spacemouse_cartesian_vel.py
```

Press **Button 0** on the SpaceMouse to toggle enable/disable. Move the SpaceMouse to control the end-effector in 6 DOF.

| SpaceMouse axis | Robot motion |
|---|---|
| Push forward/back | X |
| Push left/right | Y |
| Push up/down | Z |
| Tilt forward/back | Rx |
| Tilt left/right | Ry |
| Twist | Rz |

Default scales: `linear = 0.05 m/s`, `angular = 0.1 rad/s`. No Python dependencies beyond ROS2.

## Files

| File | Description |
|---|---|
| `move_to_joint_angles.py` | Main script — validates, confirms, and moves the robot |
| `spacemouse_cartesian_vel.py` | SpaceMouse teleop — Twist → Cartesian velocity (no IK) |
| `real_robot_control.py` | Control module — ROS2 interface, gripper, arm control, diagnostics |
| `launch_realsense_camera.sh` | Launch RealSense cameras → ROS2 topics (`/rgb/camera_1`, etc.) |
| `realsense_ros2_publisher.py` | RealSense to ROS2 image publisher |

### RealSense Camera (for data collection)

For `lerobot-record` and `record_spacemouse_cartesian_vel_real.sh`, you need a camera publishing to `/rgb/camera_1`. Use the RealSense launch script:

```bash
# On workstation (separate terminal):
cd REAL_ROBOT
./launch_realsense_camera.sh
```

- **Config**: Edit `camera_config.yaml` with your camera serial numbers (run `lerobot-find-cameras realsense` to find them)
- **Full guide**: See [CAMERA_SETUP.md](CAMERA_SETUP.md)

## Safety

- **Confirmation prompt**: The script asks for confirmation before moving the robot
- **Joint limit validation**: All target angles are checked against Panda limits
- **Large movement detection**: Automatically increases duration for large movements
- **Dry-run mode**: Test everything without sending movement commands


(.venv) cihan@Solaris:~/lerobot-ros-agent/REAL_ROBOT$ ros2 topic list 
/dynamic_joint_states
/franka/joint_states
/franka_robot_state_broadcaster/robot_state
/franka_robot_state_broadcaster/transition_event
/joint_state_broadcaster/transition_event
/joint_states
/joy
/panda_arm_controller/controller_state
/panda_arm_controller/joint_trajectory
/panda_arm_controller/state
/panda_arm_controller/transition_event
/panda_gripper/joint_states
/parameter_events
/robot_description
/rosout
/spacenav/joy
/spacenav/offset
/spacenav/rot_offset
/spacenav/twist
/tf
/tf_static