---
noteId: "db09f0b0bf8611f0bdfec72c7df9bf4c"
tags: []

---

# Robot Joint Movement

This directory contains Python scripts to move the Franka Panda robot to specific joint angles after MoveIt is launched.

## Files

### `move_to_joint_angles.py`
Main script to move the robot to specific joint angles.

**Target Joint Angles (rad):** `[-0.159, 0.302, -0.093, -2.255, 0.047, 2.555, 0.498]`

### `test_joint_movement.py`
Test script that moves the robot to the target joint angles and then back to home position.

## Usage

### Basic Usage
```bash
cd isaac_franka_moveit_perception
python move_to_joint_angles.py
```

### Test the Movement
```bash
cd isaac_franka_moveit_perception
python test_joint_movement.py
```

## Prerequisites
1. MoveIt must be launched before running these scripts
2. ROS2 environment must be sourced
3. Robot controllers must be active

## Joint Angle Details
- panda_joint1: -0.159 rad (-9.1°)
- panda_joint2: 0.302 rad (17.3°)
- panda_joint3: -0.093 rad (-5.3°)
- panda_joint4: -2.255 rad (-129.2°)
- panda_joint5: 0.047 rad (2.7°)
- panda_joint6: 2.555 rad (146.4°)
- panda_joint7: 0.498 rad (28.5°)
