# RealSense Camera Setup Guide

Complete guide for setting up Intel RealSense cameras for real robot data collection.

## Table of Contents

1. [Hardware Requirements](#hardware-requirements)
2. [Software Installation](#software-installation)
3. [Finding Camera Serial Numbers](#finding-camera-serial-numbers)
4. [Configuration](#configuration)
5. [Running the Publisher](#running-the-publisher)
6. [Verification](#verification)
7. [Data Collection](#data-collection)
8. [Troubleshooting](#troubleshooting)

---

## Hardware Requirements

### Supported RealSense Cameras

- RealSense D400 Series: D415, D435, D435i, D455
- RealSense D500 Series: D505C, D535
- RealSense SR300 (legacy, may have limited support)

### Requirements

- USB 3.0 port (required for high-resolution/high-fps operation)
- Sufficient bandwidth when using multiple cameras
- Stable mount to prevent camera movement during recording

---

## Software Installation

### 1. Install RealSense SDK

**Ubuntu/Debian**:
```bash
# Register Intel's server
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-key F6E65AC044F831AC80A06380C8B3A55A6F3EFCDE
sudo add-apt-repository "deb https://librealsense.intel.com/Debian/apt-repo $(lsb_release -cs) main"

# Install
sudo apt update
sudo apt install librealsense2-utils librealsense2-dev
```

**Verify installation**:
```bash
realsense-viewer
```

### 2. Install Python Bindings

```bash
# In your lerobot environment
pip install pyrealsense2
```

### 3. Install ROS2

ROS2 Humble should already be installed for robot control. Verify:
```bash
source /opt/ros/humble/setup.bash
ros2 --version
```

---

## Finding Camera Serial Numbers

### Method 1: Using lerobot-find-cameras (Recommended)

```bash
lerobot-find-cameras realsense
```

**Output example**:
```
Found 2 RealSense cameras:

Camera 1:
  Type: RealSense
  Serial: 1234567890
  Name: Intel RealSense D435
  Product Line: D400
  USB Type: USB3.0
  Default Stream: 640x480 @ 30fps (RGB8)

Camera 2:
  Type: RealSense
  Serial: 0987654321
  Name: Intel RealSense D455
  Product Line: D400
  USB Type: USB3.0
  Default Stream: 640x480 @ 30fps (RGB8)
```

### Method 2: Using realsense-viewer

```bash
realsense-viewer
```

1. Launch the viewer
2. Select "Info" tab for each connected camera
3. Copy the serial number

### Method 3: Using rs-enumerate-devices

```bash
rs-enumerate-devices | grep Serial
```

---

## Configuration

### Option 1: Configuration File (Recommended for Multiple Cameras)

Create or edit `REAL_ROBOT/camera_config.yaml`:

```yaml
cameras:
  camera_1:
    serial: "1234567890"  # Replace with actual serial
    topic: "/rgb/camera_1"
    width: 640
    height: 480
    fps: 30
    color_mode: "RGB"

  camera_2:
    serial: "0987654321"  # Replace with actual serial
    topic: "/rgb/camera_2"
    width: 640
    height: 480
    fps: 30
    color_mode: "RGB"
```

### Option 2: Environment Variable

```bash
export LEROBOT_REALSENSE_CAMERAS='{
  "camera_1": {"serial": "1234567890"},
  "camera_2": {"serial": "0987654321"}
}'
```

### Option 3: Auto-Detection (Simplest)

Just run the launch script without configuration:
```bash
./launch_realsense_camera.sh
```

Cameras will be automatically assigned to `camera_1`, `camera_2`, etc.

### Resolution and FPS Guidelines

| Use Case | Resolution | FPS | Notes |
|----------|------------|-----|-------|
| Standard data collection | 640x480 | 30 | Default, balanced performance |
| High-quality dataset | 1280x720 | 30 | Better detail, more storage |
| Fast motion capture | 640x480 | 60 | Smoother motion, more CPU |
| Maximum quality | 1920x1080 | 30 | Best quality, most storage |

**Important**: Ensure your USB bandwidth can support multiple cameras at high resolution/FPS.

---

## Running the Publisher

### Basic Usage

```bash
cd REAL_ROBOT
./launch_realsense_camera.sh
```

### With Configuration File

```bash
./launch_realsense_camera.sh --config camera_config.yaml
```

### With Custom Resolution

```bash
./launch_realsense_camera.sh --width 1280 --height 720 --fps 30
```

### Expected Output

```
Activating conda environment: lerobot-ros
Checking dependencies...
✅ Dependencies OK

Detecting RealSense cameras...
Auto-detected: camera_1 = Intel RealSense D435 (SN: 1234567890)
Auto-detected: camera_2 = Intel RealSense D455 (SN: 0987654321)

Launching RealSense to ROS2 publisher...
Press Ctrl+C to stop

============================================================
RealSense to ROS2 Camera Publisher
============================================================

camera_1:
  Serial: 1234567890
  Topic: /rgb/camera_1
  Resolution: 640x480
  FPS: 30

camera_2:
  Serial: 0987654321
  Topic: /rgb/camera_2
  Resolution: 640x480
  FPS: 30
============================================================

Connected to camera 1234567890 -> /rgb/camera_1
Connected to camera 0987654321 -> /rgb/camera_2
Started 2 camera publisher threads
camera_1: 30.0 FPS
camera_2: 30.0 FPS
```

---

## Verification

### 1. Check ROS2 Topics

```bash
ros2 topic list | grep "/rgb/camera"
```

Expected output:
```
/rgb/camera_1
/rgb/camera_2
```

### 2. Check Topic Info

```bash
ros2 topic info /rgb/camera_1
```

### 3. Check FPS

```bash
ros2 topic hz /rgb/camera_1
ros2 topic hz /rgb/camera_2
```

Expected: ~30 FPS (or your configured FPS)

### 4. Visual Inspection

Install and run image viewer:
```bash
sudo apt install ros-humble-image-tools
ros2 run image_tools showimage --ros-args -r image:=/rgb/camera_1
```

### 5. Test All Cameras

```bash
# Check FPS on all cameras in parallel
for topic in /rgb/camera_*; do
    echo "Checking $topic..."
    timeout 5 ros2 topic hz "$topic" &
done
wait
```

---

## Data Collection

### Recording with RealSense Cameras

1. **Start the camera publisher**:
   ```bash
   cd REAL_ROBOT
   ./launch_realsense_camera.sh
   ```

2. **Record data** (in another terminal):
   ```bash
   LEROBOT_ROBOT_TYPE=panda_ros ./DATA_COLLECTION/record_spacemouse_ee.sh
   ```

### Dataset Structure

Your dataset will contain images from all cameras:

```
~/lerobot_datasets/spacemouse-ee-teleop/
├── episode_0/
│   ├── images/
│   │   ├── camera_1/
│   │   │   ├── frame_0000.png
│   │   │   ├── frame_0001.png
│   │   │   └── ...
│   │   └── camera_2/
│   │       ├── frame_0000.png
│   │       ├── frame_0001.png
│   │       └── ...
│   └── episode_data.parquet
└── ...
```

### Multi-Camera Considerations

- **Storage**: Each camera adds ~500MB-2GB per hour (depending on resolution/FPS)
- **CPU**: More cameras = more encoding overhead
- **USB Bandwidth**: Multiple cameras at high res may exceed USB 3.0 bandwidth
- **Synchronization**: Cameras run independently, not hardware-synchronized

---

## Troubleshooting

### No cameras detected

**Symptoms**:
```
No RealSense cameras detected!
```

**Solutions**:
1. Check physical connections:
   ```bash
   lsusb | grep Intel
   ```
2. Test with RealSense tools:
   ```bash
   realsense-viewer
   ```
3. Check permissions:
   ```bash
   # Add user to video group
   sudo usermod -aG video $USER
   # Log out and back in
   ```
4. Try different USB port (preferably USB 3.0)

### Camera connection fails

**Symptoms**:
```
Failed to connect to camera 1234567890
```

**Solutions**:
1. Verify serial number is correct
2. Check if camera is already in use:
   ```bash
   fuser /dev/video*
   ```
3. Reset camera:
   ```bash
   rs-reset
   ```
4. Try reconnecting USB cable

### Low FPS or frame drops

**Symptoms**:
```
camera_1: 15.2 FPS  (expected 30)
```

**Solutions**:
1. Check USB bandwidth:
   ```bash
   lsusb -t  # Look for "500M" instead of "5000M"
   ```
2. Reduce resolution or FPS
3. Use separate USB controller for multiple cameras
4. Close other high-bandwidth USB devices

### ROS2 topic not receiving images

**Symptoms**:
```bash
ros2 topic hz /rgb/camera_1
# No output or very low rate
```

**Solutions**:
1. Verify publisher is running:
   ```bash
   ros2 node list | grep realsense
   ```
2. Check for errors in publisher output
3. Verify topic name matches configuration
4. Test with different topic name

### Images are corrupted or distorted

**Solutions**:
1. Try different USB cable (use provided cable)
2. Reduce resolution
3. Check camera calibration:
   ```bash
   rs-enumerate-devices
   ```

### Multiple cameras not working

**Symptoms**:
Only one camera works, or FPS is very low on multiple cameras

**Solutions**:
1. Check USB bandwidth distribution:
   ```bash
   sudo lsusb -t
   ```
2. Use cameras on separate USB controllers
3. Reduce per-camera resolution/FPS
4. Add USB 3.0 PCIe expansion card for desktop

### Permission errors

**Symptoms**:
```
Permission denied: /dev/video0
```

**Solutions**:
```bash
# Add udev rules for RealSense
sudo cp ~/.local/share/lerobot/realsense/99-realsense-libusb.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && udevadm trigger

# Or add user to video group
sudo usermod -aG video $USER
# Then log out and back in
```

---

## Advanced Topics

### Camera Naming Convention

Recommended naming for different viewpoints:

| Camera Name | Use Case | Example Position |
|-------------|----------|------------------|
| `camera_1` | Primary view | Front of workspace, wide view |
| `camera_2` | Secondary view | Side angle, different perspective |
| `wrist_cam` | Gripper view | Mounted on robot wrist |
| `overhead` | Top-down | Ceiling-mounted overview |

### Hardware Synchronization

For applications requiring precise multi-camera synchronization:
- Use hardware sync cables (available on some RealSense models)
- Consider external trigger setup
- Note: Current implementation doesn't support hardware sync

### Depth Data


Depth capture is now supported:
1. Set `use_depth: true` in your camera config (YAML or JSON) for any camera you want to publish depth images for.
2. The publisher will automatically create `/depth/camera_*` topics for each enabled camera.
3. Update your robot configuration or data collection scripts to subscribe to these depth topics as needed.
4. Depth frames will be published as 16UC1 ROS2 Image messages, matching the color image resolution and FPS.

---

## Performance Benchmarks

Approximate data rates and storage requirements:

| Configuration | Data Rate | Storage/Hour |
|---------------|-----------|--------------|
| 1 camera @ 640x480, 30fps | ~250 Mbps | ~110 GB |
| 2 cameras @ 640x480, 30fps | ~500 Mbps | ~220 GB |
| 1 camera @ 1280x720, 30fps | ~560 Mbps | ~250 GB |
| 2 cameras @ 1280x720, 30fps | ~1.1 Gbps | ~500 GB |

**Note**: Actual usage may vary based on scene complexity and compression.

---

## Additional Resources

- [Intel RealSense Documentation](https://dev.intelrealsense.com/docs)
- [LeRobot Camera Documentation](https://github.com/huggingface/lerobot)
- [ROS2 Sensor Messages](https://docs.ros.org/en/humble/api/sensor_msgs/)
- [RealSense GitHub Issues](https://github.com/IntelRealSense/librealsense/issues)
