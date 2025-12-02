# Isaac Franka MoveIt Perception

A ROS2-based perception pipeline for the Franka Panda robot using NVIDIA Isaac Sim for simulation and MoveIt for motion planning.

## Overview

This project implements a complete perception and manipulation pipeline for the Franka Panda robot, combining:
- **NVIDIA Isaac Sim**: High-fidelity physics simulation
- **ROS2 Humble**: Robot operating system for communication and control
- **MoveIt**: Motion planning framework
- **Perception Pipeline**: 3D vision processing for object detection and manipulation

## Features

- **Franka Panda Robot**: Complete URDF and MoveIt configuration
- **3D Perception**: Depth camera integration with point cloud processing
- **Pick and Place**: Automated manipulation tasks with grasp planning
- **Simulation Ready**: USD world files for Isaac Sim integration
- **ROS2 Integration**: Full ROS2 Humble compatibility

## Project Structure

```
isaac_franka_moveit_perception/
├── src/
│   ├── panda_description/          # Robot URDF and mesh files
│   ├── panda_moveit_config/       # MoveIt configuration and launch files
│   └── perception_pipeline/       # Perception and manipulation nodes
├── moveit_perceptoin_world.usd    # Isaac Sim world file
└── README.md
```

## Prerequisites

- **ROS2 Humble**: [Installation Guide](https://docs.ros.org/en/humble/Installation.html)
- **NVIDIA Isaac Sim**: [Download](https://developer.nvidia.com/isaac-sim)
- **Ubuntu 22.04**: Recommended operating system
- **Git**: Version control system

## Installation

1. **Clone the repository**:
   ```bash
   git clone <your-github-repo-url>
   cd isaac_franka_moveit_perception
   ```

2. **Build the workspace**:
   ```bash
   colcon build
   source install/setup.bash
   ```

3. **Install dependencies**:
   ```bash
   rosdep install --from-paths src --ignore-src -r -y
   ```

## Usage

### Launch MoveIt Demo
```bash
ros2 launch panda_moveit_config demo.launch.py
```

### Launch Perception Pipeline
```bash
ros2 launch perception_pipeline perception_pipeline_demo.launch.py
```

### Launch Pick and Place Demo
```bash
ros2 launch perception_pipeline pick_and_place.launch.py
```

## Configuration

### Robot Configuration
- **Joint Limits**: Configured in `panda_moveit_config/config/joint_limits.yaml`
- **Kinematics**: Multiple solvers available (BioIK, TracIK, CHOMP)
- **Controllers**: ROS2 control integration ready

### Perception Settings
- **3D Sensors**: Configured for Kinect-style depth cameras
- **Point Cloud Processing**: Optimized for real-time manipulation tasks

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- **Franka Emika**: For the Panda robot platform
- **NVIDIA**: For Isaac Sim simulation environment
- **ROS2 Community**: For the excellent robotics framework
- **MoveIt Team**: For motion planning capabilities

## Support

For issues and questions:
- Create an issue on GitHub
- Check the ROS2 documentation
- Review Isaac Sim documentation

## Roadmap

- [ ] Add more perception algorithms
- [ ] Implement advanced grasp planning
- [ ] Add multi-robot support
- [ ] Create comprehensive tutorials
- [ ] Performance optimization
noteId: "95bb389087e911f0ad39052844ea82ec"
tags: []

---

