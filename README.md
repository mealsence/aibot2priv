# LeRobot ROS Agent

A comprehensive integration of [LeRobot](https://github.com/huggingface/lerobot) with ROS2 for robotic manipulation, featuring Franka Panda robot control, teleoperation, data collection, training, and Vision-Language-Action (VLA) inference capabilities.

## 🚀 Features

- **Robot Control**: Support for Franka Panda robot via ROS2 with trajectory and position control modes
- **Teleoperation**: Multiple teleoperation modes (keyboard joint control, keyboard end-effector control, SpaceMouse)
- **Data Collection**: Automated data collection scripts for training datasets
- **Training**: Multi-GPU training support with LeRobot policies
- **Inference**: Async policy inference server and client implementations
- **Gradio Agent**: Voice-controlled robot agent with LLM integration (OpenAI, Gemini)
- **Isaac Sim Integration**: Full support for NVIDIA Isaac Sim simulation environment
- **MoveIt Integration**: Complete MoveIt2 integration for motion planning

## 📋 Prerequisites

- **ROS2 Humble** (or compatible distro)
- **NVIDIA Isaac Sim** (for simulation)
- **Python 3.10 or 3.11**
- **CUDA-capable GPU** (recommended: RTX 40/50 series with CUDA 12.8)
- **SpaceMouse** (optional, for 3D teleoperation)

## 🔧 Installation

### Option 1: UV Installation (Recommended - Fast)

Use [uv](https://docs.astral.sh/uv/) for a fast, reproducible installation:

```bash
# Clone with submodules
git clone --recursive https://github.com/your-username/lerobot-ros-agent.git
cd lerobot-ros-agent

# Run automated setup (CUDA 12.8 for RTX 40/50 series)
./INSTALL/setup_with_uv.sh --cuda128

# Activate environment
source activate_env.sh
```

See [misc/INSTALL/UV_INSTALL.md](misc/INSTALL/UV_INSTALL.md) for detailed instructions.

### Option 2: Conda Installation

```bash
# Use existing conda setup script
./INSTALL/setup_lerobot_rtx5090_venv.sh
```

### Build ROS2 Packages

```bash
cd ros2/isaac_franka_moveit_perception
colcon build --symlink-install
source install/setup.bash
```

### Install Custom Policies

To install a custom VLA policy, add the policy to the `vla/policies` directory and install using `uv`:

```bash
# Navigate to the policy directory
cd vla/policies/{policy_name}

# Install the policy in editable mode
uv pip install -e .
```

**Example: Installing WallX policy**

```bash
cd vla/policies/lerobot_policy_wallx
uv pip install -e .
```

This installs the policy package in editable mode, making it available for both training and inference. The policy will be auto-discovered when you run `lerobot-teleoperate` or other lerobot commands.

### Git Submodules

The `lerobot` directory is a git submodule. When cloning:
- Use `git clone --recursive` to clone with all submodules, OR
- Run `git submodule update --init --recursive` after cloning

## 🎮 Quick Start

### Option A: Isaac Sim Simulation

#### 1. Start Isaac Sim

1. Open Isaac Sim and load the USD file from `isaac_franka_moveit_perception/isaacsim/`
2. Run the simulation

#### 2. Launch ROS2 Controller

```bash
./scripts/launch_position_control_tmux.sh
```

#### 3. Move to Home Position

```bash
python3 ros2/isaac_franka_moveit_perception/move_to_joint_angles.py
```

### Option B: Real Franka Panda Robot

#### Prerequisites

- **Control PC** (192.168.1.2): Connected to robot via Ethernet, runs `franka_ros2` 
- **Workstation** (this machine): On same network, runs control scripts
- **Robot**: Franka Panda with FCI interface at 192.168.1.101

#### 1. Start Controllers

Start the Robot Control Menu:

```bash
./scripts/robot_control_menu.sh 
```

#### 2. Move Robot to Joint Angles

```bash
# example: home position
ros2 param set /move_to_home_lerobot goal_position "[-0.034, -0.436, -0.076, -2.581, -0.038, 2.145, 0.703]"

# switch controller
./switch_controller.sh home
```

#### 3. RealSense Camera Setup

```bash
cd REAL_ROBOT
./launch_realsense_camera.sh --config camera_config.yaml
```

See [REAL_ROBOT/CAMERA_SETUP.md](REAL_ROBOT/CAMERA_SETUP.md) for serial number configuration.



## 📹 Data Collection

### SpaceMouse End-Effector Control

```bash
./vla/DATA_COLLECTION/record_spacemouse_ee_fast.sh
```

For more recording options, see:
- `./vla/DATA_COLLECTION/record_spacemouse_ee.sh` - Standard recording script
- See [HOW TO RUN](HOW%20TO%20RUN) for detailed teleoperation options

## 🎯 Teleoperation Options

### Option 1: Joint Space Control

Control individual joints with keyboard:
- **Keys**: `Q/A` (joint1), `W/S` (joint2), `E/D` (joint3), `R/F` (joint4),
- **Keys**: `T/G` (joint5), `Y/H` (joint6), `U/J` (joint7), `O/L` (gripper)

```bash
lerobot-teleoperate \
  --robot.type=panda_ros \
  --robot.id=my_panda_follower \
  --teleop.type=keyboard_joint_panda \
  --teleop.id=my_panda_leader \
  --display_data=true
```

### Option 2: Keyboard End-Effector Control

IK-based Cartesian position control:
- **Keys**: `W/S` move forward/backward (Y), `A/D` left/right (X), `Q/E` down/up (Z)
- **Keys**: `L` closes gripper, `O` opens it

```bash
lerobot-teleoperate \
  --robot.type=panda_ros \
  --robot.id=my_panda_follower \
  --teleop.type=keyboard_ee_panda \
  --teleop.id=my_panda_leader \
  --display_data=true
```

### Option 3: SpaceMouse End-Effector Control

Analog 3D control with SpaceMouse:

1. **Start SpaceMouse driver**:
   ```bash
   ros2 run spacenav spacenav_node --ros-args -r /spacenav/joy:=/joy
   ```

2. **Run teleoperation**:
   ```bash
   # Trajectory control (smooth motion, ~100ms latency)
   lerobot-teleoperate \
     --robot.type=panda_ros \
     --robot.id=my_panda_follower \
     --teleop.type=spacemouse_ee_panda \
     --teleop.id=my_spacemouse_leader \
     --display_data=true
   
   # Position control (fast, ~15-20ms latency)
   lerobot-teleoperate \
     --robot.type=panda_ros_position \
     --robot.id=my_panda_follower \
     --teleop.type=spacemouse_ee_panda \
     --teleop.id=my_spacemouse_leader \
     --display_data=true
   ```

**Key Parameters**:
- `--teleop.config.linear_step_m=0.01` - Step size (default: 1cm per full deflection)
- `--teleop.config.dead_zone=0.05` - Dead zone to filter hand tremor
- `--teleop.config.orientation_weight=0.05` - Wrist stability weight

See [HOW TO RUN](HOW%20TO%20RUN) for detailed teleoperation documentation.

## 🧪 Evaluation

```bash
./vla/EVALUATION/eval.sh <model_checkpoint>
```

## 🤖 Gradio Agent (Voice-Controlled Robot)

Run the voice-controlled robot agent with LLM integration:

```bash
cd ui/gradio_agent
python demo_tool_calling.py
```

**Options**:
- `--llm openai` or `--llm gemini` - Choose LLM provider
- `--transcriber openai|gemini|meralion` - Choose transcription service
- `--preload-policy` - Preload VLA policy for faster inference
- `--discover-arm-server` - Enable action server discovery

The interface will be available at `http://0.0.0.0:7868`

See [ui/gradio_agent/README.md](ui/gradio_agent/README.md) for detailed documentation.

## 📁 Project Structure

```
lerobot-ros-agent/
├── scripts/               # Launch and control scripts
├── vla/
│   ├── DATA_COLLECTION/   # Recording and dataset scripts
│   └── EVALUATION/        # Evaluation scripts
├── ui/
│   └── gradio_agent/      # Gradio-based voice agent
└── ros2/
  ├── isaac_franka_moveit_perception/  # ROS2 packages
  ├── lerobot_robot_ros/               # LeRobot ROS2 robot interface
  └── lerobot_teleoperator_devices/    # Teleoperation devices
```

## 🔍 Camera Configuration

Default camera settings (640×480 VGA - standard for LeRobot datasets):

```bash
export LEROBOT_CAMERA_TOPIC=/rgb/camera_1
export LEROBOT_CAMERA_WIDTH=640
export LEROBOT_CAMERA_HEIGHT=480
export LEROBOT_CAMERA_FPS=30
```

## 🛠️ Troubleshooting

### ROS2 Issues

- **RTPS/SHM errors**: Run `./FIX/fix_rtps_shm_errors.sh`
- **ROS2 daemon issues**: Run `./FIX/fix_ros2_daemon.sh`
- **Cleanup**: Run `./FIX/cleanup_ros2.sh`

### CUDA/PyTorch Issues

- **CUDA compatibility**: Run `./FIX/fix_pytorch_cuda.sh`
- **RTX 5090 setup**: See `./INSTALL/fix_rtx5090_venv.sh`

### Kill All ROS2 Processes

```bash
./RUN/kill_all_ros2.sh
```

## 📚 Additional Documentation

- [HOW TO RUN](HOW%20TO%20RUN) - Detailed usage instructions
- [ui/gradio_agent/README.md](ui/gradio_agent/README.md) - Gradio agent documentation
- [ui/gradio_agent/POLICY_CONFIG_README.md](ui/gradio_agent/POLICY_CONFIG_README.md) - Policy configuration guide
- [misc/INSTALL/UV_INSTALL.md](misc/INSTALL/UV_INSTALL.md) - UV installation guide

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📝 License

Apache 2.0 License - see LICENSE file for details.

## 🙏 Acknowledgments

- [LeRobot](https://github.com/huggingface/lerobot) - The base framework
- [ROS2](https://docs.ros.org/en/humble/) - Robot Operating System 2
- [MoveIt2](https://moveit.ros.org/) - Motion planning framework
- [NVIDIA Isaac Sim](https://developer.nvidia.com/isaac-sim) - Simulation environment
