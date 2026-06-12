# ROS 2 Humble base image with LeRobot setup
FROM osrf/ros:humble-desktop

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    ROS_DISTRO=humble

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build essentials
    build-essential \
    cmake \
    git \
    wget \
    curl \
    # Python development
    python3-dev \
    python3-pip \
    python3-venv \
    # Additional tools
    nano \
    vim \
    tmux \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# Install colcon and rosdep
RUN pip install --no-cache-dir colcon-common-extensions \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3-rosdep \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast Python dependency management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Create workspace directory
WORKDIR /ws

# Set up entrypoint to source ROS2 setup
RUN echo '#!/bin/bash\n\
set -e\n\
source /opt/ros/humble/setup.bash\n\
if [ -f /ws/install/setup.bash ]; then\n\
  source /ws/install/setup.bash\n\
fi\n\
exec "$@"' > /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
