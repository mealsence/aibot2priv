#!/bin/bash
# HRC Robot Interface - Automated Setup Script
# This script automates the installation and configuration of the HRC Robot Interface

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

# Check if running with sudo when needed
check_sudo() {
    if [ "$EUID" -eq 0 ]; then
        print_error "Please do not run this script as root/sudo"
        print_info "The script will ask for sudo password when needed"
        exit 1
    fi
}

# Check Python version
check_python() {
    print_header "Checking Python Installation"

    if ! command -v python3 &> /dev/null; then
        print_error "Python3 is not installed"
        print_info "Please install Python 3.10 or higher"
        exit 1
    fi

    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
        print_error "Python version $PYTHON_VERSION is too old"
        print_info "Please install Python 3.10 or higher"
        exit 1
    fi

    print_success "Python $PYTHON_VERSION detected"
}

# Check and setup pip
check_pip() {
    print_header "Checking pip Installation"

    if ! command -v pip3 &> /dev/null; then
        print_warning "pip3 not found, installing..."
        sudo apt-get update
        sudo apt-get install -y python3-pip
    fi

    print_success "pip3 is available"
}

# Install system dependencies
install_system_deps() {
    print_header "Installing System Dependencies"

    print_info "Updating package lists..."
    sudo apt-get update

    print_info "Installing fonts for image annotation..."
    sudo apt-get install -y fonts-noto-cjk fonts-dejavu fonts-liberation

    print_info "Installing audio dependencies..."
    sudo apt-get install -y ffmpeg

    print_info "Installing build dependencies..."
    sudo apt-get install -y build-essential python3-dev

    print_success "System dependencies installed"
}

# Check ROS2 installation
check_ros2() {
    print_header "Checking ROS2 Installation"

    if [ -z "$ROS_DISTRO" ]; then
        print_warning "ROS2 environment not sourced"

        # Try to find ROS2 installation
        if [ -f "/opt/ros/humble/setup.bash" ]; then
            print_info "Found ROS2 Humble, sourcing..."
            source /opt/ros/humble/setup.bash
            export ROS_DISTRO="humble"
        elif [ -f "/opt/ros/iron/setup.bash" ]; then
            print_info "Found ROS2 Iron, sourcing..."
            source /opt/ros/iron/setup.bash
            export ROS_DISTRO="iron"
        else
            print_warning "ROS2 not found in standard location"
            print_info "Please install ROS2 or source your ROS2 installation manually"
            print_info "Visit: https://docs.ros.org/en/humble/Installation.html"
            return 1
        fi
    fi

    print_success "ROS2 $ROS_DISTRO detected"

    # Install ROS2 Python packages if available
    print_info "Installing ROS2 Python dependencies..."
    sudo apt-get install -y \
        ros-$ROS_DISTRO-cv-bridge \
        ros-$ROS_DISTRO-tf2-ros \
        ros-$ROS_DISTRO-sensor-msgs \
        ros-$ROS_DISTRO-geometry-msgs \
        ros-$ROS_DISTRO-control-msgs \
        ros-$ROS_DISTRO-trajectory-msgs \
        2>/dev/null || print_warning "Some ROS2 packages could not be installed"

    return 0
}

# Install Python dependencies
install_python_deps() {
    print_header "Installing Python Dependencies"

    if [ ! -f "requirements.txt" ]; then
        print_error "requirements.txt not found"
        exit 1
    fi

    print_info "Installing Python packages from requirements.txt..."
    print_warning "This may take several minutes..."

    pip3 install --upgrade pip
    pip3 install -r requirements.txt

    print_success "Python dependencies installed"
}

# Check API keys
check_api_keys() {
    print_header "Checking API Keys"

    local missing_keys=0

    if [ -z "$OPENAI_API_KEY" ]; then
        print_warning "OPENAI_API_KEY not set"
        missing_keys=1
    else
        print_success "OPENAI_API_KEY found"
    fi

    if [ -z "$GOOGLE_API_KEY" ]; then
        print_warning "GOOGLE_API_KEY not set"
        missing_keys=1
    else
        print_success "GOOGLE_API_KEY found"
    fi

    if [ $missing_keys -eq 1 ]; then
        print_info ""
        print_info "To set API keys, add these to your ~/.bashrc:"
        print_info "  export OPENAI_API_KEY=\"your-openai-key-here\""
        print_info "  export GOOGLE_API_KEY=\"your-google-key-here\""
        print_info "Then run: source ~/.bashrc"
    fi
}

# Create necessary directories
create_directories() {
    print_header "Creating Necessary Directories"

    if [ ! -d "detected_objects" ]; then
        mkdir -p detected_objects
        print_success "Created detected_objects directory"
    else
        print_info "detected_objects directory already exists"
    fi
}

# Verify installation
verify_installation() {
    print_header "Verifying Installation"

    print_info "Checking Python imports..."

    python3 -c "import numpy; import cv2; import PIL; import gradio" 2>/dev/null && \
        print_success "Core Python packages verified" || \
        print_error "Some Python packages failed to import"

    python3 -c "import openai" 2>/dev/null && \
        print_success "OpenAI package verified" || \
        print_warning "OpenAI package not available (install if using --llm openai)"

    python3 -c "from google import genai" 2>/dev/null && \
        print_success "Google GenAI package verified" || \
        print_warning "Google GenAI package not available (install if using --llm gemini)"

    python3 -c "import mbodied" 2>/dev/null && \
        print_success "MBodied package verified" || \
        print_error "MBodied package failed to import (required)"
}

# Add ROS2 source to bashrc
setup_bashrc() {
    print_header "Setting up Shell Environment"

    if [ -n "$ROS_DISTRO" ]; then
        local ros_source="source /opt/ros/$ROS_DISTRO/setup.bash"

        if ! grep -q "$ros_source" ~/.bashrc; then
            echo "" >> ~/.bashrc
            echo "# ROS2 Environment Setup (added by hrc_robot_interface setup)" >> ~/.bashrc
            echo "$ros_source" >> ~/.bashrc
            print_success "Added ROS2 sourcing to ~/.bashrc"
        else
            print_info "ROS2 already sourced in ~/.bashrc"
        fi
    fi
}

# Print post-installation instructions
print_instructions() {
    print_header "Setup Complete!"

    echo ""
    print_success "Installation completed successfully!"
    echo ""
    print_info "Next steps:"
    echo "  1. Set up your API keys (if not already done):"
    echo "     export OPENAI_API_KEY=\"your-key\""
    echo "     export GOOGLE_API_KEY=\"your-key\""
    echo ""
    echo "  2. Source your environment (if ROS2 was just installed):"
    echo "     source ~/.bashrc"
    echo ""
    echo "  3. Run the application:"
    echo "     python3 demo_tool_calling.py"
    echo ""
    echo "  4. Access the web interface at:"
    echo "     http://localhost:7868"
    echo ""
    print_info "For more information, see README.md"
    echo ""
}

# Main installation flow
main() {
    print_header "HRC Robot Interface - Automated Setup"
    print_info "This script will install all necessary dependencies"
    echo ""

    check_sudo
    check_python
    check_pip
    install_system_deps

    # ROS2 is optional but recommended
    check_ros2 || print_warning "Continuing without ROS2 (some features may be limited)"

    install_python_deps
    create_directories
    verify_installation
    setup_bashrc
    check_api_keys
    print_instructions
}

# Run main installation
main
