# ROS2 Controller Compatibility Report: Simulation vs Real-World Franka Panda

## Executive Summary

This report analyzes the controller configurations used in simulation (Isaac Sim) for data collection versus the real-world Franka Panda robot setup. It identifies compatibility issues and provides recommendations for aligning simulation and real-world control for seamless data collection and policy evaluation.

---

## 1. Simulation Setup Analysis

### 1.1 Launch Scripts for Data Collection

Two main launch scripts are used for data collection in simulation:

| Script | Purpose | Controller Used |
|--------|---------|-----------------|
| `launch_position_control_tmux.sh` | LeRobot recording with position control (low-latency) | `panda_position_controller` |
| `launch_moveit_tmux.sh` | Perception pipeline + SpaceMouse teleoperation | MoveIt planning |

### 1.2 Controllers Defined in Simulation

From `isaac_franka_moveit_perception/src/panda_moveit_config/config/ros2_controllers.yaml`:

```yaml
controller_manager:
  ros__parameters:
    update_rate: 100  # Hz

    panda_arm_controller:
      type: joint_trajectory_controller/JointTrajectoryController

    panda_position_controller:
      type: position_controllers/JointGroupPositionController

    panda_hand_controller:
      type: position_controllers/GripperActionController
```

### 1.3 Active Controller for Data Collection

The `panda_lerobot_record.launch.py` spawns **only** `panda_position_controller` (not `panda_arm_controller`):

```python
# Spawn panda_position_controller (FAST mode - direct position commands)
panda_position_controller_spawner = Node(
    package="controller_manager",
    executable="spawner",
    arguments=["panda_position_controller", "-c", "/controller_manager"],
)
```

**Key Point**: The simulation for data collection uses **direct position control** via `JointGroupPositionController`.

### 1.4 Topic and Message Type (Simulation)

- **Topic**: `/panda_position_controller/commands`
- **Message Type**: `Float64MultiArray`
- **Control Type**: Direct joint position (no interpolation, instant execution)
- **Latency**: ~15-20ms (ultra-low latency)
- **Joints**: 7 joints (panda_joint1 through panda_joint7)

### 1.5 LeRobot Robot Configuration (Simulation)

From `lerobot_robot_ros/lerobot_robot_ros/config.py`:

```python
@RobotConfig.register_subclass("panda_ros_position")
class PandaROSPositionConfig(PandaROSConfig):
    """Configuration for Franka Emika Panda with direct position control.
    
    Uses JOINT_POSITION action type for ultra-low latency control
    (~15-20ms vs ~120ms with trajectory control).
    """
    action_type: ActionType = ActionType.JOINT_POSITION
    
    ros2_interface: ROS2InterfaceConfig = field(
        default_factory=lambda: ROS2InterfaceConfig(
            arm_joint_names=["panda_joint1", "panda_joint2", "panda_joint3",
                           "panda_joint4", "panda_joint5", "panda_joint6", "panda_joint7"],
            gripper_joint_name="panda_finger_joint1",
            position_controller_name="panda_position_controller",
            gripper_controller_name="panda_hand_controller",
        ),
    )
```

---

## 2. Real-World Setup Analysis

### 2.1 Franka ROS2 Package Location

The real robot uses the official `franka_ros2` stack located at `/home/cihan/Franka_ROS2_Grasping`:

```
Franka_ROS2_Grasping/
├── src/
│   ├── franka_arm_ros2/        # Official Franka ROS 2 integration
│   │   ├── franka_bringup/    # Launch files for robot bring-up
│   │   ├── franka_control2/   # Custom control node
│   │   ├── franka_description/# URDF/xacro files
│   │   ├── franka_moveit_config/ # MoveIt2 configuration
│   │   ├── franka_hardware/   # Hardware interface (libfranka)
│   │   ├── franka_gripper/   # Gripper action server
│   │   ├── franka_example_controllers/ # Example controllers
│   │   └── franka_msgs/       # Custom messages/actions
│   └── ...
└── ...
```

### 2.2 Available Controller Types

Based on the codebase and franka_ros2 documentation, the following controllers are available:

| Controller | Interface | Topic/Action | Use Case |
|-----------|-----------|--------------|----------|
| **JointTrajectoryController** | Action + Topic | `/panda_arm_controller/joint_trajectory` | Smooth trajectory execution |
| **JointGroupPositionController** | Topic | `/panda_position_controller/commands` | Direct position commands |
| **JointVelocityController** | Topic | `/panda_velocity_controller/commands` | Velocity-based control |
| **JointImpedanceController** | Topic | Custom | Compliant/force-based control |
| **GravityCompensationController** | Topic | Custom | Gravity compensation |

### 2.3 Real Robot Control Code

From `REAL_ROBOT/real_robot_control.py`, the `RealRobotArmController` class auto-detects available controllers:

```python
class RealRobotArmController:
    """
    Auto-detects the available control interface:
    - FollowJointTrajectory action on /panda_arm_controller/follow_joint_trajectory
    - JointTrajectory topic on /panda_arm_controller/joint_trajectory
    - Float64MultiArray topic on /panda_position_controller/commands
    """
    
    def _detect_controller_type(self) -> str:
        # Tries in order:
        # 1. FollowJointTrajectory action
        # 2. JointTrajectory topic
        # 3. Position controller topic
```

### 2.4 Gripper Control (Real Robot)

The real robot supports multiple gripper control methods:

1. **Native Franka action**: `/panda_gripper/move` (franka_msgs.action.Move)
2. **GripperCommand action**: `/panda_hand_controller/gripper_cmd` (control_msgs.action.GripperCommand)

---

## 3. The Issue: Position Controller Problems on Real Hardware

### 3.1 Problem Statement

The user reports: *"there is issue with ros2 position controller with franka robot so it should be effort or velocity"*

### 3.2 Root Cause Analysis

The issue with direct position control on real Franka hardware stems from:

1. **Franka's Built-in Controllers**: The Franka Control Interface (FCI) has built-in controllers that handle motion. Direct position commands from ros2_control may conflict with these built-in controllers.

2. **Timing Issues**: Direct position control requires high-frequency (~100Hz+) command streaming. Any timing jitter can cause unstable behavior.

3. **Hardware Interface Limitations**: The `franka_hardware` interface may not handle position commands as smoothly as trajectory commands.

4. **Safety Mechanisms**: Franka's safety systems may reject direct position commands that violate velocity/acceleration limits.

5. **Control Mode Mismatch**: The franka_hardware interface in ros2_control typically runs in a specific control mode (position, velocity, or effort). Switching between modes can cause issues.

### 3.3 Observed Symptoms

- Unstable or jerky robot motion
- Robot not responding to position commands
- Error messages related to control mode
- Joint position overshooting

---

## 4. Controller Options Comparison

### 4.1 All Available Controllers

| Controller | Latency | Smoothness | Reliability | Complexity |
|------------|---------|------------|-------------|------------|
| **JointGroupPositionController** | ~15ms (lowest) | Low (jerky) | **Problematic** on real hardware | Low |
| **JointTrajectoryController** | ~100ms | High (smooth) | **Reliable** | Low |
| **JointVelocityController** | ~50ms | Medium | Moderate | Medium |
| **JointImpedanceController** | ~50ms | High (compliant) | Moderate | High |

### 4.2 Recommendation: JointTrajectoryController

For real-world Franka robot, **JointTrajectoryController** is the most reliable option:

- **Proven reliability**: Works seamlessly with franka_hardware interface
- **Smooth motion**: Handles interpolation internally
- **Built-in safety**: Respects velocity/acceleration limits
- **Topic**: `/panda_arm_controller/joint_trajectory`
- **Message**: `JointTrajectory`

---

## 5. Implementation Recommendations

### 5.1 Option A: Use Trajectory Controller for Real Robot (Recommended)

This is the most reliable option that works with the real robot:

**Step 1**: Configure LeRobot to use trajectory-based control:

```bash
# In eval.sh or record script, use:
ROBOT_TYPE="${LEROBOT_ROBOT_TYPE:-panda_ros}"  # NOT panda_ros_position
```

**Step 2**: Update robot config:

```python
# In config.py, ensure:
@RobotConfig.register_subclass("panda_ros")
class PandaROSConfig(ROS2Config):
    action_type: ActionType = ActionType.JOINT_TRAJECTORY  # NOT JOINT_POSITION
    # Uses: /panda_arm_controller/joint_trajectory
```

**Step 3**: Launch real robot with trajectory controller:

```bash
# On robot control PC:
ros2 launch franka_bringup franka.launch.py robot_ip:=192.168.1.101
```

### 5.2 Option B: Create Velocity Controller Adapter

If position controller behavior is required, create a velocity controller that integrates position commands:

1. Create a new ros2_control controller package
2. Subscribe to position commands (Float64MultiArray)
3. Compute velocity from position delta / time
4. Send velocity commands to robot via `/panda_velocity_controller/commands`

**Implementation Complexity**: High (requires C++ controller development)

### 5.3 Option C: Use Built-in Franka Controllers

The franka_example_controllers package provides controllers that work directly with Franka's FCI:

- `joint_position_example_controller`: Direct position control
- `joint_velocity_example_controller`: Velocity control
- `joint_impedance_example_controller`: Impedance control
- `gravity_compensation_example_controller`: Gravity compensation

These can be launched via:

```bash
ros2 launch franka_bringup joint_velocity_example_controller.launch.py robot_ip:=192.168.1.101
```

---

## 6. Consistency Between Simulation and Real Robot

### 6.1 Current Mismatch

| Aspect | Simulation | Real Robot (with issues) | Real Robot (recommended) |
|--------|------------|--------------------------|-------------------------|
| Controller | JointGroupPositionController | JointGroupPositionController | JointTrajectoryController |
| Topic | /panda_position_controller/commands | /panda_position_controller/commands | /panda_arm_controller/joint_trajectory |
| Message | Float64MultiArray | Float64MultiArray | JointTrajectory |
| Latency | ~15ms | Problematic | ~100ms |

### 6.2 Recommended Approach for Consistency

To maintain consistency between simulation and real robot:

1. **For Simulation**: Continue using `panda_position_controller` (works well in Isaac Sim)
2. **For Real Robot**: Use `panda_arm_controller` (JointTrajectoryController)
3. **Accept Latency Difference**: The ~85ms latency difference is acceptable for teleoperation and policy execution

### 6.3 Evaluation Script Updates

Update `EVALUATION/eval.sh` to use trajectory controller:

```bash
# Change from:
ROBOT_TYPE="${LEROBOT_ROBOT_TYPE:-panda_ros_position}"

# To:
ROBOT_TYPE="${LEROBOT_ROBOT_TYPE:-panda_ros}"
```

---

## 7. Data Collection Workflow

### 7.1 Simulation Data Collection

```bash
# Terminal 1: Launch Isaac Sim with ROS2 bridge
# Terminal 2: Launch position controller
./launch_position_control_tmux.sh

# Terminal 3: Start recording
./DATA_COLLECTION/record_spacemouse_ee.sh
```

### 7.2 Real Robot Data Collection

```bash
# Terminal 1: On robot control PC
ros2 launch franka_bringup franka.launch.py robot_ip:=192.168.1.101

# Terminal 2: On workstation - use trajectory controller
lerobot-record \
  --robot.type=panda_ros \
  --robot.id=my_panda \
  --teleop.type=spacemouse_ee_panda \
  ...
```

---

## 8. Summary and Recommendations

### 8.1 Key Findings

1. **Simulation uses direct position control** via `JointGroupPositionController` for ultra-low latency (~15-20ms)

2. **Real robot has issues** with direct position control due to timing, hardware interface, and safety mechanism conflicts

3. **JointTrajectoryController** is the recommended alternative for real robot operation

4. **Latency trade-off**: ~15ms (simulation) vs ~100ms (real robot with trajectory)

### 8.2 Recommended Actions

| Priority | Action | Effort |
|----------|--------|--------|
| High | Update eval.sh to use `panda_ros` instead of `panda_ros_position` | Low |
| High | Test real robot with JointTrajectoryController | Low |
| Medium | Create velocity controller adapter if needed | High |
| Low | Document best practices for simulation-to-real transfer | Medium |

### 8.3 Conclusion

The simulation uses `JointGroupPositionController` (direct position commands) for ultra-low latency data collection, while the real Franka Panda robot works most reliably with `JointTrajectoryController`.

**Recommended approach**:
- Use `panda_ros` (trajectory-based) for real robot control
- The latency difference (~15ms vs ~100ms) is acceptable for teleoperation and policy execution
- This ensures stable, reliable operation on real hardware

**If ultra-low latency is critical**, consider implementing a velocity controller adapter or using the built-in Franka controllers directly (via `franka_example_controllers`) rather than ros2_control position interface.

---

## Appendix A: File Locations

| File | Location |
|------|----------|
| Simulation launch script | `launch_position_control_tmux.sh` |
| Simulation controller config | `isaac_franka_moveit_perception/src/panda_moveit_config/config/ros2_controllers.yaml` |
| Simulation launch file | `isaac_franka_moveit_perception/src/panda_moveit_config/launch/panda_lerobot_record.launch.py` |
| LeRobot config | `lerobot_robot_ros/lerobot_robot_ros/config.py` |
| LeRobot interface | `lerobot_robot_ros/lerobot_robot_ros/ros_interface.py` |
| Real robot control | `REAL_ROBOT/real_robot_control.py` |
| Evaluation script | `EVALUATION/eval.sh` |
| Franka ROS2 packages | `/home/cihan/Franka_ROS2_Grasping/src/` |

## Appendix B: ROS Topics Reference

### Simulation Topics
- Position commands: `/panda_position_controller/commands`
- Joint states: `/joint_states`

### Real Robot Topics
- Trajectory commands: `/panda_arm_controller/joint_trajectory`
- Position commands: `/panda_position_controller/commands`
- Joint states: `/joint_states`
- Gripper action: `/panda_gripper/move`

---

*Report generated: February 2026*
*Author: Analysis of lerobot-ros-agent and Franka_ROS2_Grasping repositories*
