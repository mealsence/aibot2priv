# Docker Setup for LeRobot ROS 2 Humble

This directory contains Docker configuration for running LeRobot with ROS 2 Humble, eliminating OS compatibility issues.

## Prerequisites

- **Docker**: [Install Docker](https://docs.docker.com/engine/install/)
- **Docker Compose**: `pip install docker-compose` or [Install from Docker docs](https://docs.docker.com/compose/install/)
- **4GB+ disk space** for Docker image
- **GPU support** (optional): [NVIDIA Container Toolkit](https://github.com/NVIDIA/nvidia-container-toolkit)

## Quick Start

### Step 1: Build the Docker Image

```bash
# Make script executable
chmod +x docker-build.sh

# Build the image
./docker-build.sh

# Or using docker-compose directly
docker-compose build
```

### Step 2: Start the Container

```bash
# Start in detached mode (background)
docker-compose up -d

# Or start interactively (see output)
docker-compose up
```

### Step 3: Attach to Container

```bash
# Open bash shell in the running container
docker-compose exec lerobot-ros2 bash

# Or directly run a command
docker-compose exec lerobot-ros2 source /opt/ros/humble/setup.bash && ros2 --version
```

### Step 4: Install Project Dependencies

Inside the container:

```bash
# Navigate to workspace
cd /ws

# Install Python dependencies using uv
uv venv .venv
source .venv/bin/activate
uv pip install --index-strategy unsafe-best-match -e .

# Install ROS2 packages
cd ros2/isaac_franka_moveit_perception
colcon build --symlink-install
source install/setup.bash
```

## Common Commands

### View running containers
```bash
docker-compose ps
```

### Stop the container
```bash
docker-compose stop
```

### Remove container and image
```bash
docker-compose down --rmi all
```

### View container logs
```bash
docker-compose logs -f lerobot-ros2
```

### Execute command in container
```bash
docker-compose exec lerobot-ros2 <command>
```

### Multiple shells
```bash
# Terminal 1: Start container
docker-compose up

# Terminal 2: Attach shell
docker-compose exec lerobot-ros2 bash

# Terminal 3: Another shell
docker-compose exec lerobot-ros2 bash
```

## GPU Support

### NVIDIA GPU (CUDA)

1. **Install NVIDIA Container Toolkit**:
   ```bash
   # Ubuntu/Debian
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/ubuntu24.04/libnvidia-container.list | \
     sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
     sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update
   sudo apt-get install -y nvidia-container-toolkit
   ```

2. **Restart Docker daemon**:
   ```bash
   sudo systemctl restart docker
   ```

3. **Update docker-compose.yml** (uncomment GPU section):
   ```yaml
   runtime: nvidia
   environment:
     - NVIDIA_VISIBLE_DEVICES=all
   ```

4. **Rebuild and start**:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

5. **Verify GPU access inside container**:
   ```bash
   docker-compose exec lerobot-ros2 nvidia-smi
   ```

## File Structure

```
lerobot-ros-agent/
├── Dockerfile              # Container definition
├── docker-compose.yml      # Multi-container orchestration
├── docker-build.sh         # Build helper script
├── DOCKER.md              # This file
├── .venv/                 # (Created inside container)
├── ros2/                  # ROS2 packages
│   ├── isaac_franka_moveit_perception/
│   ├── lerobot_robot_ros/
│   └── lerobot_teleoperator_devices/
├── lerobot/               # LeRobot submodule
└── pyproject.toml         # Python dependencies
```

## Troubleshooting

### Container won't start
```bash
# Check logs
docker-compose logs lerobot-ros2

# Rebuild from scratch
docker-compose down --rmi all
docker-compose up -d
```

### Permission issues
```bash
# Run with sudo if needed
sudo docker-compose exec lerobot-ros2 bash
```

### Out of disk space
```bash
# Clean up old images
docker image prune -a

# Check disk usage
docker system df
```

### ROS2 command not found inside container
```bash
# Make sure ROS2 setup is sourced
source /opt/ros/humble/setup.bash
ros2 --version
```

### Port conflicts
If port 11311 (ROS2 default) is in use, change `ROS_DOMAIN_ID`:
```bash
export ROS_DOMAIN_ID=1  # Use different ID
```

## Development Workflow

### Typical session:

```bash
# Terminal 1: Start container
docker-compose up -d

# Terminal 2: Work in container
docker-compose exec lerobot-ros2 bash
cd /ws
source .venv/bin/activate
source install/setup.bash

# Terminal 3: Another bash
docker-compose exec lerobot-ros2 bash
cd /ws/ros2
colcon build

# Terminal 4: Monitor logs
docker-compose logs -f
```

### Editing code on host

Files in `/home/kwankenghei/Desktop/lerobot-ros-agent-aibot2` are automatically synced to `/ws` inside the container. Edit on your host system and changes appear in the container instantly.

## Building PyTorch in Docker

Inside the container, for GPU support:

```bash
# CUDA 12.8 (RTX 40/50)
uv pip install torch torchvision torchaudio \
  --index-strategy unsafe-best-match \
  --extra-index-url https://download.pytorch.org/whl/cu128 \
  --extra-index-url https://pypi.nvidia.com

# CUDA 12.4 (RTX 30)
uv pip install torch torchvision torchaudio \
  --index-strategy unsafe-best-match \
  --extra-index-url https://download.pytorch.org/whl/cu124 \
  --extra-index-url https://pypi.nvidia.com
```

## Next Steps

1. [Read UV_INSTALL.md for detailed Python setup](INSTALL/UV_INSTALL.md)
2. [Follow ROS2 build instructions](ros2/README.md)
3. [Launch Isaac Sim or physical robot](README.md)

## Resources

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [ROS 2 Humble Documentation](https://docs.ros.org/en/humble/)
- [NVIDIA Container Toolkit](https://github.com/NVIDIA/nvidia-container-toolkit)
- [LeRobot Documentation](https://github.com/huggingface/lerobot)
