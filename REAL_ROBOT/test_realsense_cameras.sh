#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_section() {
    echo ""
    echo -e "${GREEN}▶ $1${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

activate_python_env() {
    if [ -n "${CONDA_PREFIX:-}" ]; then
        echo "Using existing conda environment: ${CONDA_DEFAULT_ENV:-${CONDA_PREFIX}}"
        return
    fi

    if [ -n "${VIRTUAL_ENV:-}" ]; then
        echo "Using existing virtual environment: ${VIRTUAL_ENV}"
        return
    fi

    if command -v conda >/dev/null 2>&1; then
        local conda_base
        conda_base="$(conda info --base)"
        # shellcheck disable=SC1090
        source "${conda_base}/etc/profile.d/conda.sh"
        local candidate_envs
        candidate_envs="${LEROBOT_CONDA_ENVS:-lerobot-ros-isaac lerobot-ros}"
        for env_name in ${candidate_envs}; do
            if conda env list | awk '{print $1}' | grep -x "${env_name}" >/dev/null 2>&1; then
                conda activate "${env_name}"
                echo "Activated conda environment: ${env_name}"
                return
            fi
        done
    fi

    if [ -f "${PROJECT_ROOT}/.venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source "${PROJECT_ROOT}/.venv/bin/activate"
        echo "Activated virtual environment at ${PROJECT_ROOT}/.venv"
        return
    fi

    echo "Warning: No matching conda env or .venv found. Continuing with system Python." >&2
}

# ============================================================================
# MAIN TEST SEQUENCE
# ============================================================================

print_header "RealSense Camera Test Suite"

# Activate Python environment
activate_python_env
echo ""

# Test 1: Check dependencies
print_section "Test 1: Checking Dependencies"

MISSING_DEPS=0

# Check pyrealsense2
if python -c "import pyrealsense2" 2>/dev/null; then
    RS_VERSION=$(python -c "import pyrealsense2; print(pyrealsense2.__version__)" 2>/dev/null || echo "unknown")
    print_success "pyrealsense2 installed (version: $RS_VERSION)"
else
    print_error "pyrealsense2 not installed"
    echo "  Install with: pip install pyrealsense2"
    MISSING_DEPS=1
fi

# Check rclpy (ROS2)
if python -c "import rclpy" 2>/dev/null; then
    print_success "rclpy (ROS2) installed"
else
    print_error "rclpy (ROS2) not installed"
    echo "  Install ROS2 Humble: https://docs.ros.org/en/humble/Installation.html"
    MISSING_DEPS=1
fi

# Check numpy
if python -c "import numpy" 2>/dev/null; then
    print_success "numpy installed"
else
    print_error "numpy not installed"
    echo "  Install with: pip install numpy"
    MISSING_DEPS=1
fi

# Check cv2 (optional, for BGR conversion)
if python -c "import cv2" 2>/dev/null; then
    print_success "opencv-python installed (for BGR color mode)"
else
    print_warning "opencv-python not installed (required for BGR color mode)"
    echo "  Install with: pip install opencv-python"
fi

# Check PyYAML (optional, for config files)
if python -c "import yaml" 2>/dev/null; then
    print_success "pyyaml installed (for YAML config files)"
else
    print_warning "pyyaml not installed (required for YAML config files)"
    echo "  Install with: pip install pyyaml"
fi

if [ $MISSING_DEPS -eq 1 ]; then
    print_error "Missing required dependencies. Please install them first."
    exit 1
fi

# Test 2: Check USB devices
print_section "Test 2: Checking USB Devices"

if command -v lsusb >/dev/null 2>&1; then
    RS_DEVICES=$(lsusb | grep -i "intel\|realsense" || true)
    if [ -n "$RS_DEVICES" ]; then
        print_success "Found RealSense USB devices:"
        echo "$RS_DEVICES" | while read -r line; do
            echo "  $line"
        done
    else
        print_warning "No RealSense devices found via lsusb"
        echo "  Check physical connections and try a different USB port"
    fi

    # Check USB speed
    echo ""
    echo "USB connection speed check:"
    lsusb -t 2>/dev/null | grep -i "intel\|realsense" | while read -r line; do
        if echo "$line" | grep -q "5000M"; then
            echo -e "  ${GREEN}$line${NC} (USB 3.0 - Good)"
        elif echo "$line" | grep -q "480M"; then
            echo -e "  ${YELLOW}$line${NC} (USB 2.0 - May have issues)"
        else
            echo "  $line"
        fi
    done
else
    print_warning "lsusb not available, skipping USB device check"
fi

# Test 3: Check RealSense SDK tools
print_section "Test 3: Checking RealSense SDK Tools"

if command -v rs-enumerate-devices >/dev/null 2>&1; then
    print_success "librealsense2-tools installed"

    echo ""
    echo "Enumerating RealSense devices:"
    if rs-enumerate-devices 2>/dev/null; then
        print_success "RealSense devices detected by SDK"
    else
        print_warning "No RealSense devices detected by SDK"
    fi
else
    print_warning "librealsense2-tools not installed"
    echo "  Install with: sudo apt install librealsense2-utils"
fi

# Test 4: pyrealsense2 camera detection
print_section "Test 4: Detecting Cameras with pyrealsense2"

python3 - << 'PYTHON_SCRIPT'
import sys

try:
    import pyrealsense2 as rs

    # Create a context and query for devices
    context = rs.context()
    devices = context.query_devices()

    num_devices = len(devices)

    if num_devices == 0:
        print("\033[0;31m✗ No RealSense cameras detected\033[0m")
        print("  Troubleshooting:")
        print("    - Check USB connections")
        print("    - Try a different USB port (preferably USB 3.0)")
        print("    - Run: realsense-viewer (to test manually)")
        print("    - Check user permissions: sudo usermod -aG video $USER")
        sys.exit(1)

    print(f"\033[0;32m✓ Found {num_devices} RealSense camera(s)\033[0m")
    print("")

    for i, device in enumerate(devices, 1):
        serial = device.get_info(rs.camera_info.serial_number)
        name = device.get_info(rs.camera_info.name)
        product_line = device.get_info(rs.camera_info.product_line)
        firmware_version = device.get_info(rs.camera_info.firmware_version)

        print(f"  Camera {i}:")
        print(f"    Name: {name}")
        print(f"    Serial: {serial}")
        print(f"    Product Line: {product_line}")
        print(f"    Firmware: {firmware_version}")

        # Get supported stream configurations
        print(f"    Supported Streams:")
        for sensor in device.query_sensors():
            for stream_profile in sensor.get_stream_profiles():
                if stream_profile.is_video_stream_profile():
                    vp = stream_profile.as_video_stream_profile()
                    stream_type = "Color" if vp.stream_type() == rs.stream.color else "Depth"
                    fmt = vp.format()
                    print(f"      - {stream_type}: {vp.width()}x{vp.height()} @ {vp.fps()}fps ({fmt})")
        print("")

except Exception as e:
    print(f"\033[0;31m✗ Error detecting cameras: {e}\033[0m")
    sys.exit(1)
PYTHON_SCRIPT

if [ $? -ne 0 ]; then
    print_error "Camera detection failed"
    exit 1
fi

# Test 5: Test frame capture from each camera
print_section "Test 5: Testing Frame Capture"

python3 - << 'PYTHON_SCRIPT'
import sys
import time

try:
    import pyrealsense2 as rs
    import numpy as np

    # Create a context and query for devices
    context = rs.context()
    devices = context.query_devices()

    num_devices = len(devices)

    if num_devices == 0:
        print("\033[0;31m✗ No cameras to test\033[0m")
        sys.exit(1)

    print(f"Testing frame capture from {num_devices} camera(s)...")
    print("")

    success_count = 0

    for i, device in enumerate(devices, 1):
        serial = device.get_info(rs.camera_info.serial_number)
        name = device.get_info(rs.camera_info.name)

        print(f"  Camera {i} ({name}, SN: {serial}):")

        try:
            # Create pipeline
            pipeline = rs.pipeline()
            config = rs.config()

            # Enable device by serial
            config.enable_device(serial)

            # Configure color stream
            config.enable_stream(
                rs.stream.color,
                640, 480,
                rs.format.rgb8,
                30
            )

            # Start pipeline
            profile = pipeline.start(config)

            # Warm up
            for _ in range(30):
                pipeline.wait_for_frames()

            # Capture a few test frames
            frame_times = []
            for j in range(10):
                start = time.time()
                frames = pipeline.wait_for_frames(timeout_ms=1000)
                color_frame = frames.get_color_frame()

                if color_frame:
                    frame_data = np.asanyarray(color_frame.get_data())
                    elapsed = time.time() - start
                    frame_times.append(elapsed)
                else:
                    print(f"    ✗ Frame {j+1}: No color frame received")
                    pipeline.stop()
                    raise Exception("No color frame")

            avg_time = sum(frame_times) / len(frame_times)
            fps = 1.0 / avg_time if avg_time > 0 else 0

            print(f"    ✓ Captured {len(frame_times)} frames")
            print(f"    ✓ Frame size: {frame_data.shape}")
            print(f"    ✓ Average latency: {avg_time*1000:.1f}ms")
            print(f"    ✓ Effective FPS: {fps:.1f}")

            # Stop pipeline
            pipeline.stop()
            success_count += 1

        except Exception as e:
            print(f"    ✗ Failed: {e}")

        print("")

    if success_count == num_devices:
        print(f"\033[0;32m✓ All cameras passed frame capture test\033[0m")
    else:
        print(f"\033[0;33m⚠ {success_count}/{num_devices} cameras passed\033[0m")
        sys.exit(1)

except Exception as e:
    print(f"\033[0;31m✗ Frame capture test failed: {e}\033[0m")
    sys.exit(1)
PYTHON_SCRIPT

if [ $? -ne 0 ]; then
    print_error "Frame capture test failed"
    exit 1
fi

# Test 6: Generate camera config
print_section "Test 6: Generating Camera Configuration"

python3 - << 'PYTHON_SCRIPT'
import sys
import os

try:
    import pyrealsense2 as rs

    # Create a context and query for devices
    context = rs.context()
    devices = context.query_devices()

    if len(devices) == 0:
        print("\033[0;31m✗ No cameras found\033[0m")
        sys.exit(1)

    print("Generated camera_config.yaml:")
    print("")
    print("cameras:")

    for i, device in enumerate(devices, 1):
        serial = device.get_info(rs.camera_info.serial_number)
        cam_name = f"camera_{i}"
        print(f"  {cam_name}:")
        print(f"    serial: \"{serial}\"")
        print(f"    topic: \"/rgb/{cam_name}\"")
        print(f"    width: 640")
        print(f"    height: 480")
        print(f"    fps: 30")
        print(f"    color_mode: \"RGB\"")
        print("")

except Exception as e:
    print(f"\033[0;31m✗ Error generating config: {e}\033[0m")
    sys.exit(1)
PYTHON_SCRIPT

# Test 7: ROS2 check
print_section "Test 7: Checking ROS2 Environment"

if command -v ros2 >/dev/null 2>&1; then
    ROS_VERSION=$(ros2 --version 2>/dev/null || echo "unknown")
    print_success "ROS2 installed: $ROS_VERSION"

    # Check if ROS_DOMAIN_ID is set
    if [ -n "${ROS_DOMAIN_ID:-}" ]; then
        print_success "ROS_DOMAIN_ID is set to: $ROS_DOMAIN_ID"
    else
        print_warning "ROS_DOMAIN_ID not set (using default: 0)"
    fi

    # Try to source ROS2 if not already sourced
    if ! ros2 topic list >/dev/null 2>&1; then
        print_warning "ROS2 daemon not running or not sourced"
        echo "  Source ROS2: source /opt/ros/humble/setup.bash"
        echo "  Start daemon: ros2 daemon start"
    else
        print_success "ROS2 daemon is running"
    fi
else
    print_warning "ROS2 not found in PATH"
    echo "  Install ROS2 Humble: https://docs.ros.org/en/humble/Installation.html"
fi

# ============================================================================
# SUMMARY
# ============================================================================

print_header "Test Summary"

echo "All tests completed! Your RealSense cameras are ready to use."
echo ""
echo "Next steps:"
echo "  1. Start the camera publisher:"
echo "     cd REAL_ROBOT && ./launch_realsense_camera.sh"
echo ""
echo "  2. Verify ROS2 topics:"
echo "     ros2 topic list | grep '/rgb/camera'"
echo ""
echo "  3. Check FPS:"
echo "     ros2 topic hz /rgb/camera_1"
echo ""
echo "  4. View camera feed:"
echo "     ros2 run image_tools showimage --ros-args -r image:=/rgb/camera_1"
echo ""
