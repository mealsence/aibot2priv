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

Start `franka_ros2`:
```bash
source /opt/ros/humble/setup.bash
ros2 launch franka_bringup franka.launch.py robot_ip:=192.168.1.101
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

### SpaceMouse Teleoperation

Control the robot with a 3Dconnexion SpaceMouse:

1. **Activate your environment** (venv or conda with lerobot):
   ```bash
   source .venv/bin/activate   # or: conda activate lerobot-ros
   ```
2. **Start SpaceMouse driver** (on this workstation):
   ```bash
   ros2 run spacenav spacenav_node --ros-args -r /spacenav/joy:=/joy
   ```
3. **Run spacemouse control**:
   ```bash
   cd REAL_ROBOT && python spacemouse_control.py
   ```
4. Move the SpaceMouse to control the end-effector. Button 0: close gripper, Button 1: open gripper.

Requires `placo` for IK: `pip install placo` or `pip install lerobot[placo-dep]`.

## Files

| File | Description |
|---|---|
| `move_to_joint_angles.py` | Main script — validates, confirms, and moves the robot |
| `spacemouse_control.py` | SpaceMouse teleop — Joy → IK → joint commands |
| `real_robot_control.py` | Control module — ROS2 interface, gripper, arm control, diagnostics |

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