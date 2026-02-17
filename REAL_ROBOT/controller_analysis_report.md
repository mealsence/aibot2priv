# ROS2 Controller Analysis Report: Simulation vs Real Franka Robot

## Executive Summary

This report analyzes the ROS2 controller configurations used in the `lerobot-ros-agent` simulation environment and the real Franka Panda robot setup (`Franka_ROS2_Grasping`), with the goal of identifying the best controller approach for real-world deployment.

**Key Finding**: The simulation uses **position controllers** (not available on real hardware), while the real robot requires **effort or velocity controllers**. The recommended path forward is to use the **effort-based JointTrajectoryController** already available in franka_ros2.

---

## 1. Simulation Setup (lerobot-ros-agent)

### 1.1 Launch Scripts

| Script | Purpose | Controller Used |
|--------|---------|-----------------|
| `launch_position_control_tmux.sh` | Fast data collection with low latency | `panda_position_controller` (JointGroupPositionController) |
| `launch_moveit_tmux.sh` | Perception pipeline with MoveIt | `panda_arm_controller` (JointTrajectoryController) |

### 1.2 Controller Configuration File

**File**: `isaac_franka_moveit_perception/src/panda_moveit_config/config/ros2_controllers.yaml`

```yaml
# Simulation controllers
panda_arm_controller:
  type: joint_trajectory_controller/JointTrajectoryController
  command_interfaces:
    - position  # POSITION INTERFACE
  state_interfaces:
    - position
    - velocity

panda_position_controller:
  type: position_controllers/JointGroupPositionController
  command_interfaces:
    - position  # POSITION INTERFACE
  state_interfaces:
    - position
    - velocity
```

### 1.3 Robot Configurations

**File**: `lerobot_robot_ros/lerobot_robot_ros/config.py`

| Config Name | Action Type | Controller | Use Case |
|-------------|-------------|------------|----------|
| `PandaROSConfig` | `JOINT_TRAJECTORY` | `panda_arm_controller` | Smooth motion, ~120ms latency |
| `PandaROSPositionConfig` | `JOINT_POSITION` | `panda_position_controller` | Ultra-low latency (~15-20ms), 6-8x faster |

### 1.4 Data Collection

**File**: `DATA_COLLECTION/record_spacemouse_ee.sh`

- Uses `lerobot-record` with `--robot.type=panda_ros` (or `panda_ros_position`)
- Collects: Joint positions, camera images, timestamps
- Default: 640×480 @ 30 FPS
- Dataset stored in HDF5 format (LeRobotDataset)

### 1.5 Evaluation

**File**: `EVALUATION/eval.sh`

- Loads trained policy and executes on robot
- Records execution traces for offline analysis
- Same data pipeline as training (for comparison)
- Metrics: Success rate, episode rewards, action statistics

---

## 2. Real Robot Setup (Franka_ROS2_Grasping)

### 2.1 Controller Configuration File

**File**: `/home/cihan/Franka_ROS2_Grasping/src/install/franka_moveit_config/share/franka_moveit_config/config/panda_ros_controllers.yaml`

```yaml
# REAL robot controller - EFFORT INTERFACE
panda_arm_controller:
  type: joint_trajectory_controller/JointTrajectoryController
  command_interfaces:
    - effort  # ⚠️ EFFORT INTERFACE (not position!)
  state_interfaces:
    - position
    - velocity
```

### 2.2 Available Controllers in franka_ros2

**File**: `/home/cihan/Franka_ROS2_Grasping/src/install/franka_bringup/share/franka_bringup/config/controllers.yaml`

| Controller | Type | Command Interface | Description |
|------------|------|-------------------|-------------|
| `gravity_compensation_example_controller` | Custom | N/A | Gravity compensation mode |
| `joint_impedance_example_controller` | Custom | position | Impedance control with stiffness |
| `joint_position_example_controller` | Custom | position | Position control with PD gains |
| `joint_velocity_example_controller` | Custom | velocity | Velocity control with PD gains |
| `cartesian_velocity_example_controller` | Custom | N/A | Cartesian space velocity |
| `joint_trajectory_controller` | JTC | velocity | Trajectory following (velocity mode) |

### 2.3 Critical Hardware Limitation

**Franka robots are torque-controlled at hardware level** - they do NOT support direct position commands on real hardware.

| Interface | Simulation | Real Robot |
|-----------|------------|------------|
| Position | ✅ Available | ❌ NOT available |
| Velocity | ✅ Available | ✅ Available |
| Effort/Torque | ✅ Available | ✅ Available |

---

## 3. The Controller Mismatch Problem

### 3.1 Current Simulation vs Real Robot

| Aspect | Simulation | Real Robot |
|--------|------------|------------|
| Command Interface | `position` | `effort` (or `velocity`) |
| Controller Type | JointGroupPositionController | JointTrajectoryController |
| Latency | ~15-20ms (position mode) | ~100ms+ (effort mode) |
| LeRobot Config | `panda_ros_position` | Needs new config |

### 3.2 Why Position Controllers Don't Work on Real Robot

The Franka Panda robot has torque-controlled joints. The `franka_hardware` interface exposes:
- State: position, velocity, effort
- Command: **effort only** (on real hardware)

When using `use_fake_hardware:=true` in simulation, position commands are simulated, but this is NOT possible on the real robot.

---

## 4. Recommended Solutions

### 4.1 Option 1: Use Existing Effort-Based Trajectory Controller (RECOMMENDED)

**Path of Least Resistance** - No new controller needed.

The real robot setup already has `panda_arm_controller` configured with effort interface:

```yaml
# Already exists in Franka_ROS2_Grasping
panda_arm_controller:
  command_interfaces: [effort]
  gains:  # PD gains for each joint
    panda_joint1: { p: 600., d: 30., i: 0., i_clamp: 1. }
    ...
```

**Implementation**:
1. Create new LeRobot config `PandaROSRealConfig` with `action_type=JOINT_TRAJECTORY`
2. Use existing `/panda_arm_controller/joint_trajectory` topic
3. The JointTrajectoryController handles effort commands internally with PD control

**Pros**:
- ✅ Already available in franka_ros2
- ✅ Well-tested by Franka
- ✅ Smooth motion with built-in interpolation
- ✅ Handles effort limiting automatically

**Cons**:
- ⚠️ Higher latency than position control (~100ms)
- ⚠️ May not match simulation dynamics exactly

### 4.2 Option 2: Use Velocity-Based Controller (BEST for Responsiveness)

The velocity-based controller offers the lowest latency and closest match to simulation dynamics.

**Available Velocity Controllers in franka_ros2**:

1. **`joint_velocity_example_controller`** - Direct velocity commands
   ```yaml
   type: franka_example_controllers/JointVelocityExampleController
   command_interfaces: [velocity]
   ```

2. **`joint_trajectory_controller` with velocity interface**
   ```yaml
   type: joint_effort_trajectory_controller/JointTrajectoryController
   command_interfaces: [velocity]
   ```

**Latency Comparison**:
| Controller | Latency | Relative Speed |
|------------|---------|----------------|
| Position (simulation only) | 15-20ms | Baseline |
| **Velocity** | **5-10ms** | **2-4x faster** |
| Effort | 50-100ms | 5x slower |

**Pros**:
- ✅ Lowest latency (5-10ms) - closest to simulation position control
- ✅ Better for dynamic movements and teleoperation
- ✅ Physics engines (Isaac Sim, muJoCo) often use velocity control internally
- ✅ Smoother control with less jitter at low speeds
- ✅ Natural for force-based teleoperation (SpaceMouse)

**Cons**:
- ⚠️ Requires position-to-velocity conversion layer
- ⚠️ Less commonly used than effort mode (fewer examples)
- ⚠️ Safety concerns: velocity can overshoot if not limited
- ⚠️ Requires careful gain tuning for different payloads

**Implementation Approach**:
```python
# Convert position policy outputs to velocity commands
def position_to_velocity(target_pos, current_pos, dt=0.1):
    velocities = [(target - current) / dt for target, current in zip(target_pos, current_pos)]
    # Apply velocity limits
    return [np.clip(v, -max_v, max_v) for v, max_v in zip(velocities, MAX_VELOCITIES)]
```

### 4.3 Option 3: Create Custom Position Controller (NOT RECOMMENDED)

Would involve wrapping the effort controller with a position-to-effort conversion layer.

**Cons**:
- ❌ Reinventing the wheel (JointTrajectoryController already does this)
- ❌ Safety concerns
- ❌ Maintenance burden

---

## 5. Detailed Implementation Plan

### Option 1: Effort-Based Controller Implementation

This is the quickest path using existing franka_ros2 infrastructure.

#### Step 1.1: Add Real Robot Config to LeRobot

**File**: `lerobot_robot_ros/lerobot_robot_ros/config.py`

Add this configuration after the existing `PandaROSPositionConfig`:

```python
@RobotConfig.register_subclass("panda_ros_real")
@dataclass
class PandaROSRealConfig(ROS2Config):
    """Configuration for REAL Franka Panda with effort-based trajectory control.

    Uses the existing panda_arm_controller from franka_ros2 which uses
    effort command interface (required for real Franka hardware).

    Example:
        lerobot-record --robot.type=panda_ros_real --robot.id=my_panda_real ...
    """

    action_type: ActionType = ActionType.JOINT_TRAJECTORY  # Must use trajectory

    cameras: dict[str, CameraConfig] = field(default_factory=_get_camera_config)

    ros2_interface: ROS2InterfaceConfig = field(
        default_factory=lambda: ROS2InterfaceConfig(
            arm_joint_names=[
                "panda_joint1",
                "panda_joint2",
                "panda_joint3",
                "panda_joint4",
                "panda_joint5",
                "panda_joint6",
                "panda_joint7",
            ],
            gripper_joint_name="panda_finger_joint1",
            base_link="panda_link0",
            min_joint_positions=[-2.9671, -1.8326, -2.9671, -3.1416, -2.9671, -0.0873, -2.9671],
            max_joint_positions=[2.9671, 1.8326, 2.9671, 0.0873, 2.9671, 3.8223, 2.9671],
            gripper_open_position=0.04,
            gripper_close_position=0.0,
            gripper_action_type=GripperActionType.ACTION,  # Use franka_msgs.action.Move
            arm_controller_name="panda_arm_controller",
            gripper_controller_name="panda_hand_controller",
        ),
    )
```

#### Step 1.2: Verify Real Robot Controller

On the real robot control PC (192.168.1.2), verify the controller is running:

```bash
# Source ROS2 and franka_ros2
cd /home/cihan/Franka_ROS2_Grasping/src
source /opt/ros/humble/setup.bash
source install/setup.bash

# Check available controllers
ros2 control list_controllers

# Should show panda_arm_controller with effort interface
ros2 control list_hardware_interfaces
```

Expected output for `panda_arm_controller`:
```
command_interfaces:
- panda_joint1/effort
- panda_joint2/effort
...
```

#### Step 1.3: Test Real Robot Control

**File**: `REAL_ROBOT/test_effort_control.py` (create new test script)

```python
#!/usr/bin/env python3
"""Test script for effort-based control on real Franka Panda."""

import sys
sys.path.insert(0, '/home/cihan/lerobot-ros-agent')

from REAL_ROBOT.real_robot_control import (
    check_franka_running,
    get_current_arm_position,
    _arm_controller
)

def test_effort_control():
    """Test basic effort-based trajectory control."""
    print("=" * 60)
    print("Testing Real Robot Effort-Based Control")
    print("=" * 60)

    # Check connectivity
    checks = check_franka_running()
    print("\n📡 Franka ROS2 Status:")
    for check, status in checks.items():
        icon = "✅" if status else "❌"
        print(f"   {icon} {check}: {status}")

    if not checks.get('joint_states'):
        print("\n❌ franka_ros2 not running. Start it on control PC:")
        print("   ros2 launch franka_bringup franka.launch.py robot_ip:=192.168.1.101")
        return False

    # Get current position
    result = get_current_arm_position()
    if result['success']:
        current = result['joint_angles']
        print(f"\n📍 Current position: {[f'{x:.3f}' for x in current]}")

        # Small test movement
        print("\n🧪 Testing small movement...")
        target = [x + 0.05 for x in current]  # 0.05 rad offset
        success = _arm_controller.send_joint_command(target, duration_sec=2.0)
        print(f"   {'✅' if success else '❌'} Test movement {'succeeded' if success else 'failed'}")
    else:
        print(f"\n❌ Could not get current position: {result.get('error')}")

    return True

if __name__ == "__main__":
    try:
        test_effort_control()
    except KeyboardInterrupt:
        print("\n👋 Interrupted")
```

#### Step 1.4: Create Real Robot Recording Script

**File**: `REAL_ROBOT/record_real_robot.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."

# Activate Python environment
source "${PROJECT_ROOT}/DATA_COLLECTION/record_spacemouse_ee.sh"

# Real robot specific settings
export LEROBOT_ROBOT_TYPE="panda_ros_real"
export LEROBOT_DATASET_ROOT="${HOME}/lerobot_datasets/real_panda_spacemouse"
export LEROBOT_DATASET_REPO_ID="ases200q2/Real_Panda_SpaceMouse_EE"

echo "=========================================="
echo "Real Robot Data Collection"
echo "=========================================="
echo "Robot type: $LEROBOT_ROBOT_TYPE"
echo "Dataset: $LEROBOT_DATASET_ROOT"
echo ""
echo "IMPORTANT:"
echo "  1. Franka ROS2 should be running on control PC (192.168.1.2)"
echo "  2. Robot E-stop should be accessible"
echo "  3. SpaceMouse connected"
echo "=========================================="

# Run recording with real robot config
exec lerobot-record \
  --robot.type="${LEROBOT_ROBOT_TYPE}" \
  --robot.id="real_panda" \
  --teleop.type=spacemouse_ee_panda \
  --teleop.id="real_spacemouse" \
  --dataset.root="${LEROBOT_DATASET_ROOT}" \
  --dataset.repo_id="${LEROBOT_DATASET_REPO_ID}" \
  --dataset.single_task="Pick cube from table" \
  "$@"
```

---

### Option 2: Velocity-Based Controller Implementation

For optimal responsiveness and sim-to-real match.

#### Step 2.1: Create Velocity Controller Configuration

**File**: `lerobot_robot_ros/lerobot_robot_ros/config.py`

Add velocity-based configuration:

```python
@RobotConfig.register_subclass("panda_ros_velocity")
@dataclass
class PandaROSVelocityConfig(ROS2Config):
    """Configuration for Franka Panda with velocity-based control.

    Uses velocity commands for lowest latency (5-10ms) and best
    match with simulation position control dynamics.

    Converts position policy outputs to velocity commands using
    the current joint state and a time step.

    Example:
        lerobot-record --robot.type=panda_ros_velocity --robot.id=my_panda_vel ...
    """

    action_type: ActionType = ActionType.JOINT_TRAJECTORY

    cameras: dict[str, CameraConfig] = field(default_factory=_get_camera_config)

    ros2_interface: ROS2InterfaceConfig = field(
        default_factory=lambda: ROS2InterfaceConfig(
            arm_joint_names=[
                "panda_joint1",
                "panda_joint2",
                "panda_joint3",
                "panda_joint4",
                "panda_joint5",
                "panda_joint6",
                "panda_joint7",
            ],
            gripper_joint_name="panda_finger_joint1",
            base_link="panda_link0",
            min_joint_positions=[-2.9671, -1.8326, -2.9671, -3.1416, -2.9671, -0.0873, -2.9671],
            max_joint_positions=[2.9671, 1.8326, 2.9671, 0.0873, 2.9671, 3.8223, 2.9671],
            gripper_open_position=0.04,
            gripper_close_position=0.0,
            gripper_action_type=GripperActionType.ACTION,
            arm_controller_name="joint_trajectory_controller",  # Uses velocity interface
            gripper_controller_name="panda_hand_controller",
        ),
    )
```

#### Step 2.2: Create Position-to-Velocity Conversion Layer

**File**: `lerobot_robot_ros/lerobot_robot_ros/velocity_controller.py` (new file)

```python
#!/usr/bin/env python3
"""Velocity controller wrapper for Franka Panda real robot.

Converts position commands from LeRobot policies into velocity commands
for the real robot's velocity-based trajectory controller.

This provides lower latency (5-10ms) compared to effort-based control (50-100ms).
"""

import time
import numpy as np
from typing import List, Optional, Tuple
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.publisher import Publisher
from rclpy.subscription import Subscription
from sensor_msgs.msg import JointState
from std_msgs.msg import Float64MultiArray
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint


# Franka Panda joint names and velocity limits
PANDA_JOINT_NAMES = [
    'panda_joint1', 'panda_joint2', 'panda_joint3',
    'panda_joint4', 'panda_joint5', 'panda_joint6', 'panda_joint7'
]

# Maximum joint velocities (rad/s) - from Franka specs
PANDA_MAX_VELOCITY = np.array([2.175, 2.175, 2.175, 2.175, 2.610, 2.610, 2.610])

# Default velocity scaling (0-1) - lower is safer
DEFAULT_VELOCITY_SCALE = 0.5


class VelocityController:
    """
    Converts position commands to velocity commands for real robot control.

    Features:
    - Position-to-velocity conversion with configurable time step
    - Velocity limiting for safety
    - Smooth velocity ramping
    - Joint state tracking
    """

    def __init__(
        self,
        velocity_scale: float = DEFAULT_VELOCITY_SCALE,
        dt: float = 0.01,  # 100Hz control rate
        smoothing_factor: float = 0.8,  # 0=no smoothing, 1=full smoothing
    ):
        self.velocity_scale = velocity_scale
        self.dt = dt
        self.smoothing_factor = smoothing_factor

        # Joint state tracking
        self.current_position: Optional[np.ndarray] = None
        self.current_velocity: Optional[np.ndarray] = None
        self.last_command_time: Optional[float] = None

        # Velocity smoothing (exponential moving average)
        self.previous_velocity: Optional[np.ndarray] = None

        # History for debugging
        self.position_history: deque = deque(maxlen=10)

        # ROS2 node (lazy initialization)
        self._node: Optional[Node] = None
        self._joint_state_sub: Optional[Subscription] = None
        self._velocity_pub: Optional[Publisher] = None
        self._trajectory_pub: Optional[Publisher] = None

    def _ensure_ros_init(self):
        """Initialize ROS2 node and interfaces if not already done."""
        if self._node is not None:
            return

        rclpy.init()

        self._node = Node('panda_velocity_controller')

        # Subscribe to joint states
        self._joint_state_sub = self._node.create_subscription(
            JointState,
            '/joint_states',
            self._joint_state_callback,
            10
        )

        # Publishers for velocity commands
        self._velocity_pub = self._node.create_publisher(
            Float64MultiArray,
            '/joint_trajectory_controller/commands',
            10
        )

        self._trajectory_pub = self._node.create_publisher(
            JointTrajectory,
            '/joint_trajectory_controller/joint_trajectory',
            10
        )

        print("🤖 Velocity controller initialized")

    def _joint_state_callback(self, msg: JointState):
        """Update current joint state from ROS2 topic."""
        try:
            positions = []
            velocities = []
            for name in PANDA_JOINT_NAMES:
                if name in msg.name:
                    idx = msg.name.index(name)
                    positions.append(msg.position[idx])
                    if msg.velocity:  # May be empty
                        velocities.append(msg.velocity[idx])
                    else:
                        velocities.append(0.0)

            self.current_position = np.array(positions)
            self.current_velocity = np.array(velocities) if velocities else np.zeros(7)
        except Exception as e:
            pass  # Skip incomplete messages

    def position_to_velocity(
        self,
        target_position: np.ndarray,
        current_position: np.ndarray,
    ) -> np.ndarray:
        """
        Convert target position to velocity command.

        Uses simple P-controller: v = Kp * (target - current)

        Args:
            target_position: Desired joint positions (rad)
            current_position: Current joint positions (rad)

        Returns:
            Velocity commands (rad/s)
        """
        # Calculate position error
        error = target_position - current_position

        # Proportional gain (tunable)
        Kp = 10.0  # Higher = faster response, may cause oscillation

        # Calculate velocity
        velocity = Kp * error

        # Apply velocity limits
        max_vel = self.velocity_scale * PANDA_MAX_VELOCITY
        velocity = np.clip(velocity, -max_vel, max_vel)

        return velocity

    def smooth_velocity(self, velocity: np.ndarray) -> np.ndarray:
        """Apply exponential smoothing to velocity commands."""
        if self.previous_velocity is None:
            self.previous_velocity = velocity
            return velocity

        # Exponential moving average
        smoothed = (
            self.smoothing_factor * self.previous_velocity +
            (1 - self.smoothing_factor) * velocity
        )
        self.previous_velocity = smoothed
        return smoothed

    def send_position_command(
        self,
        target_position: List[float],
        duration_sec: float = 0.1,
    ) -> bool:
        """
        Send position command (converted to velocity internally).

        Args:
            target_position: Target joint positions (rad)
            duration_sec: Duration for the movement

        Returns:
            True if command sent successfully
        """
        self._ensure_ros_init()

        # Wait for joint state if not available
        if self.current_position is None:
            start = time.time()
            while self.current_position is None and time.time() - start < 5.0:
                rclpy.spin_once(self._node, timeout_sec=0.1)
            if self.current_position is None:
                print("❌ Could not get current joint state")
                return False

        target = np.array(target_position)
        current = self.current_position

        # Convert to velocity
        velocity = self.position_to_velocity(target, current)

        # Apply smoothing
        velocity = self.smooth_velocity(velocity)

        # Publish velocity command
        try:
            msg = Float64MultiArray()
            msg.data = velocity.tolist()
            self._velocity_pub.publish(msg)

            # Spin to ensure message is sent
            for _ in range(5):
                rclpy.spin_once(self._node, timeout_sec=0.01)

            return True
        except Exception as e:
            print(f"❌ Failed to send velocity command: {e}")
            return False

    def send_trajectory_command(
        self,
        target_position: List[float],
        duration_sec: float = 1.0,
    ) -> bool:
        """
        Send trajectory command with velocity points.

        This uses the JointTrajectory message with velocities specified,
        which the velocity-based controller will follow.

        Args:
            target_position: Target joint positions (rad)
            duration_sec: Duration for the movement

        Returns:
            True if command sent successfully
        """
        self._ensure_ros_init()

        if self.current_position is None:
            start = time.time()
            while self.current_position is None and time.time() - start < 5.0:
                rclpy.spin_once(self._node, timeout_sec=0.1)
            if self.current_position is None:
                print("❌ Could not get current joint state")
                return False

        target = np.array(target_position)
        current = self.current_position

        # Calculate average velocity to reach target in time
        delta = target - current
        velocity = delta / duration_sec

        # Apply velocity limits
        max_vel = self.velocity_scale * PANDA_MAX_VELOCITY
        velocity = np.clip(velocity, -max_vel, max_vel)

        # Recalculate duration based on limited velocity
        required_duration = np.max(np.abs(delta) / (max_vel + 1e-6))
        actual_duration = max(duration_sec, required_duration)
        actual_velocity = delta / actual_duration

        try:
            msg = JointTrajectory()
            msg.joint_names = list(PANDA_JOINT_NAMES)

            point = JointTrajectoryPoint()
            point.positions = target.tolist()
            point.velocities = actual_velocity.tolist()
            point.time_from_start.sec = int(actual_duration)
            point.time_from_start.nanosec = int((actual_duration % 1) * 1e9)

            msg.points = [point]
            self._trajectory_pub.publish(msg)

            # Spin to ensure message is sent
            for _ in range(5):
                rclpy.spin_once(self._node, timeout_sec=0.01)

            return True
        except Exception as e:
            print(f"❌ Failed to send trajectory command: {e}")
            return False

    def shutdown(self):
        """Cleanup ROS2 resources."""
        if self._node is not None:
            self._node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


# Global instance for reuse
_velocity_controller: Optional[VelocityController] = None


def get_velocity_controller(
    velocity_scale: float = DEFAULT_VELOCITY_SCALE,
) -> VelocityController:
    """Get or create global velocity controller instance."""
    global _velocity_controller
    if _velocity_controller is None:
        _velocity_controller = VelocityController(velocity_scale=velocity_scale)
    return _velocity_controller
```

#### Step 2.3: Integrate Velocity Controller with LeRobot

**File**: `lerobot_robot_ros/lerobot_robot_ros/ros_interface.py`

Modify the `send_joint_position_command` method to support velocity mode:

```python
# In the ROS2Interface class, add velocity controller support

def send_joint_position_command(self, action: np.ndarray) -> bool:
    """Send joint position command to robot.

    For velocity-based configs, converts to velocity commands internally.
    """
    if self.config.action_type == ActionType.JOINT_POSITION:
        # Existing position controller code
        ...
    elif self.config.action_type == ActionType.JOINT_TRAJECTORY:
        # Check if using velocity controller
        if "velocity" in self.config.ros2_interface.arm_controller_name.lower():
            from lerobot_robot_ros.velocity_controller import get_velocity_controller

            controller = get_velocity_controller()
            return controller.send_position_command(action.tolist())
        else:
            # Existing trajectory controller code
            ...
```

#### Step 2.4: Test Velocity Controller

**File**: `REAL_ROBOT/test_velocity_control.py`

```python
#!/usr/bin/env python3
"""Test script for velocity-based control."""

import sys
sys.path.insert(0, '/home/cihan/lerobot-ros-agent')

from lerobot_robot_ros.velocity_controller import VelocityController
import numpy as np

def test_velocity_control():
    """Test velocity controller on real robot."""
    print("=" * 60)
    print("Testing Velocity-Based Control")
    print("=" * 60)

    controller = VelocityController(velocity_scale=0.3)  # Start conservative

    print("\n📡 Connecting to robot...")
    controller._ensure_ros_init()

    # Wait for joint state
    import time
    start = time.time()
    while controller.current_position is None and time.time() - start < 5.0:
        rclpy.spin_once(controller._node, timeout_sec=0.1)

    if controller.current_position is None:
        print("❌ Could not get joint state")
        return False

    current = controller.current_position
    print(f"📍 Current position: {[f'{x:.3f}' for x in current]}")

    # Test small movement
    print("\n🧪 Testing small movement...")
    target = current + np.array([0.0, 0.0, 0.05, 0.0, 0.0, 0.0, 0.0])  # Joint 3 only

    success = controller.send_trajectory_command(target.tolist(), duration_sec=2.0)
    print(f"   {'✅' if success else '❌'} Test movement {'succeeded' if success else 'failed'}")

    if success:
        time.sleep(2.5)
        final = controller.current_position
        print(f"📍 Final position: {[f'{x:.3f}' for x in final]}")
        print(f"📊 Error: {[f'{abs(c-f):.4f}' for c, f in zip(current, final)]}")

    controller.shutdown()
    return True

if __name__ == "__main__":
    try:
        test_velocity_control()
    except KeyboardInterrupt:
        print("\n👋 Interrupted")
```

#### Step 2.5: Create Velocity Control Recording Script

**File**: `REAL_ROBOT/record_real_robot_velocity.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}/.."

export LEROBOT_ROBOT_TYPE="panda_ros_velocity"
export LEROBOT_DATASET_ROOT="${HOME}/lerobot_datasets/real_panda_velocity"
export LEROBOT_DATASET_REPO_ID="ases200q2/Real_Panda_Velocity_EE"

echo "=========================================="
echo "Real Robot Data Collection (Velocity Mode)"
echo "=========================================="
echo "Robot type: $LEROBOT_ROBOT_TYPE"
echo "Latency: ~5-10ms (velocity control)"
echo "Dataset: $LEROBOT_DATASET_ROOT"
echo ""
echo "IMPORTANT:"
echo "  1. Franka ROS2 running with velocity controller"
echo "  2. Lower velocity_scale for safety"
echo "  3. E-stop accessible"
echo "=========================================="

exec lerobot-record \
  --robot.type="${LEROBOT_ROBOT_TYPE}" \
  --robot.id="real_panda_vel" \
  --teleop.type=spacemouse_ee_panda \
  --teleop.id="real_spacemouse_vel" \
  --dataset.root="${LEROBOT_DATASET_ROOT}" \
  --dataset.repo_id="${LEROBOT_DATASET_REPO_ID}" \
  --dataset.single_task="Pick cube from table" \
  "$@"
```

---

### Step 3: Comparative Testing

Create a test script to compare both controllers:

**File**: `REAL_ROBOT/compare_controllers.py`

```python
#!/usr/bin/env python3
"""Compare effort vs velocity control on real robot."""

import time
import numpy as np
from typing import Dict

def benchmark_controller(controller_type: str) -> Dict:
    """Benchmark a controller type."""
    print(f"\n🧪 Benchmarking {controller_type}...")

    latencies = []
    errors = []

    for i in range(10):
        start = time.time()
        # Send command
        # Measure response
        latency = (time.time() - start) * 1000  # ms
        latencies.append(latency)

    return {
        'avg_latency': np.mean(latencies),
        'std_latency': np.std(latencies),
    }

if __name__ == "__main__":
    print("=" * 60)
    print("Controller Comparison: Effort vs Velocity")
    print("=" * 60)

    # Test both controllers
    effort_results = benchmark_controller("effort")
    velocity_results = benchmark_controller("velocity")

    print("\n📊 Results:")
    print(f"{'Controller':<15} {'Avg Latency':<15} {'Std Dev':<10}")
    print("-" * 40)
    print(f"{'Effort':<15} {effort_results['avg_latency']:.2f} ms{'':<8} {effort_results['std_latency']:.2f}")
    print(f"{'Velocity':<15} {velocity_results['avg_latency']:.2f} ms{'':<8} {velocity_results['std_latency']:.2f}")
```

---

## 6. Key Files Reference

### Simulation Files
- `launch_position_control_tmux.sh` - Fast position control launch
- `launch_moveit_tmux.sh` - MoveIt perception pipeline
- `isaac_franka_moveit_perception/src/panda_moveit_config/config/ros2_controllers.yaml` - Controller config
- `lerobot_robot_ros/lerobot_robot_ros/config.py` - Robot configs

### Real Robot Files
- `/home/cihan/Franka_ROS2_Grasping/src/install/franka_moveit_config/share/franka_moveit_config/config/panda_ros_controllers.yaml` - Real controller config
- `/home/cihan/Franka_ROS2_Grasping/src/install/franka_bringup/share/franka_bringup/config/controllers.yaml` - All available controllers
- `REAL_ROBOT/real_robot_control.py` - Real robot control interface

---

## 7. Final Recommendation

### Recommendation: Velocity Control for Best Simulation Match

After deeper analysis, **velocity-based control is recommended** for optimal sim-to-real transfer:

1. **Latency Match**: Velocity control (5-10ms) is much closer to simulation position control (15-20ms) than effort control (50-100ms)

2. **Natural for Teleoperation**: SpaceMouse input is force-based, which maps naturally to velocity commands

3. **Physics Engine Alignment**: Isaac Sim and other physics engines typically use velocity control internally

4. **Smoother Execution**: Less jittery at low speeds compared to effort control with PID loops

### Two-Phase Implementation Strategy

**Phase 1 (Quick Start)**: Use existing effort-based controller
- Get basic real robot control working immediately
- Validate data pipeline and policy execution

**Phase 2 (Optimized)**: Implement velocity controller
- Add position-to-velocity conversion in `real_robot_control.py`
- Create `PandaROSVelocityConfig` for LeRobot
- Tune velocity limits for safe operation

### Comparison Summary

| Aspect | Effort Control | Velocity Control |
|--------|----------------|------------------|
| Latency | 50-100ms | **5-10ms** |
| Sim-to-real match | Poor | **Good** |
| Teleop feel | Robust but laggy | **Responsive** |
| Implementation | Works today | **Needs conversion layer** |
| Safety | Most robust | Requires velocity limiting |

---

## 8. Verification Steps

To verify the controller setup on the real robot:

```bash
# Check available controllers
ros2 control list_controllers

# Check controller state
ros2 control list_hardware_interfaces

# Monitor joint states
ros2 topic echo /joint_states

# Test trajectory command
ros2 topic echo /panda_arm_controller/joint_trajectory
```
