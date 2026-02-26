#!/usr/bin/env python3
"""
RealSense to ROS2 Camera Publisher

Publishes frames from multiple Intel RealSense cameras to ROS2 topics.
Maintains compatibility with existing LeRobot data collection pipeline.

Usage:
    # Auto-detect all cameras
    python realsense_ros2_publisher.py

    # Use custom configuration
    python realsense_ros2_publisher.py --config camera_config.yaml

    # Specify cameras via JSON
    python realsense_ros2_publisher.py --cameras '{"camera_1": {"serial": "12345678"}}'

Environment Variables:
    LEROBOT_REALSENSE_CAMERAS: JSON camera configuration
    LEROBOT_REALSENSE_CONFIG_FILE: Path to YAML config file
    LEROBOT_REALSENSE_AUTO_DETECT: Auto-detect all cameras (default: true)
    LEROBOT_REALSENSE_DEFAULT_WIDTH: Default width (default: 640)
    LEROBOT_REALSENSE_DEFAULT_HEIGHT: Default height (default: 480)
    LEROBOT_REALSENSE_DEFAULT_FPS: Default FPS (default: 30)
"""

import argparse
import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from sensor_msgs.msg import Image

try:
    import pyrealsense2 as rs
except ImportError:
    print("Error: pyrealsense2 not installed. Install with: pip install pyrealsense2")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """Configuration for a single RealSense camera."""
    serial: str
    topic: str
    width: int = 640
    height: int = 480
    fps: int = 30
    color_mode: str = "RGB"  # RGB or BGR


class RealSenseCamera:
    """Manages a single RealSense camera."""

    def __init__(self, config: CameraConfig):
        self.config = config
        self.pipeline = None
        self.config_rs = None
        self.profile = None
        self.is_connected = False

    def connect(self) -> bool:
        """Connect to the RealSense camera."""
        try:
            self.pipeline = rs.pipeline()
            self.config_rs = rs.config()

            # Enable device by serial number
            self.config_rs.enable_device(self.config.serial)

            # Configure color stream
            self.config_rs.enable_stream(
                rs.stream.color,
                self.config.width,
                self.config.height,
                rs.format.rgb8,  # Always capture as RGB
                self.config.fps
            )

            # Start pipeline
            self.profile = self.pipeline.start(self.config_rs)

            # Warm up camera
            logger.info(f"Warming up camera {self.config.serial}...")
            for _ in range(30):
                self.pipeline.wait_for_frames()

            self.is_connected = True
            logger.info(f"Connected to camera {self.config.serial} -> {self.config.topic}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to camera {self.config.serial}: {e}")
            return False

    def get_frame(self) -> tuple[bool, Any | None]:
        """
        Get a frame from the camera.

        Returns:
            (success, frame_data): Tuple of success flag and frame data (RGB numpy array)
        """
        if not self.is_connected:
            return False, None

        try:
            frames = self.pipeline.wait_for_frames(timeout_ms=500)
            color_frame = frames.get_color_frame()

            if not color_frame:
                return False, None

            # Convert to numpy array
            import numpy as np
            frame_data = np.asanyarray(color_frame.get_data())

            # Convert to RGB if needed (RealSense gives RGB8)
            if self.config.color_mode == "BGR":
                import cv2
                frame_data = cv2.cvtColor(frame_data, cv2.COLOR_RGB2BGR)

            return True, frame_data

        except Exception as e:
            logger.warning(f"Error reading from camera {self.config.serial}: {e}")
            return False, None

    def disconnect(self):
        """Disconnect from the camera."""
        if self.pipeline:
            self.pipeline.stop()
            self.pipeline = None
            self.config_rs = None
            self.profile = None
            self.is_connected = False
            logger.info(f"Disconnected camera {self.config.serial}")


class RealSensePublisherNode(Node):
    """ROS2 node that publishes RealSense camera frames."""

    def __init__(self, cameras: dict[str, CameraConfig]):
        super().__init__('realsense_camera_publisher')

        self.cameras: dict[str, RealSenseCamera] = {}
        self.camera_publishers: dict[str, Any] = {}
        self.running = False
        self.threads: list[threading.Thread] = []

        # Initialize cameras
        for cam_name, cam_config in cameras.items():
            camera = RealSenseCamera(cam_config)
            if camera.connect():
                self.cameras[cam_name] = camera

                # Create ROS2 publisher
                self.camera_publishers[cam_name] = self.create_publisher(
                    Image,
                    cam_config.topic,
                    10
                )
                logger.info(f"Created publisher for {cam_name} on topic {cam_config.topic}")

        if not self.cameras:
            logger.error("No cameras connected successfully!")
            return

        self.running = True

        # Start publisher thread for each camera
        for cam_name in self.cameras.keys():
            thread = threading.Thread(
                target=self._publish_loop,
                args=(cam_name,),
                daemon=True,
                name=f"publisher_{cam_name}"
            )
            thread.start()
            self.threads.append(thread)

        logger.info(f"Started {len(self.threads)} camera publisher threads")

    def _publish_loop(self, cam_name: str):
        """Publisher loop for a single camera."""
        camera = self.cameras[cam_name]
        publisher = self.camera_publishers[cam_name]
        frame_count = 0
        last_log_time = time.time()

        while self.running and rclpy.ok():
            success, frame_data = camera.get_frame()

            if success and frame_data is not None:
                # Create ROS2 Image message
                msg = Image()
                msg.header.stamp = self.get_clock().now().to_msg()
                msg.header.frame_id = cam_name
                msg.height = frame_data.shape[0]
                msg.width = frame_data.shape[1]
                msg.encoding = "rgb8" if camera.config.color_mode == "RGB" else "bgr8"
                msg.step = frame_data.shape[1] * 3  # Width * 3 channels
                msg.data = frame_data.tobytes()

                # Publish
                publisher.publish(msg)
                frame_count += 1

                # Log FPS every 5 seconds
                current_time = time.time()
                if current_time - last_log_time >= 5.0:
                    fps = frame_count / (current_time - last_log_time)
                    logger.info(f"{cam_name}: {fps:.1f} FPS")
                    frame_count = 0
                    last_log_time = current_time

    def stop(self):
        """Stop all publishers and disconnect cameras."""
        logger.info("Stopping publishers...")
        self.running = False

        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=2.0)

        # Disconnect cameras
        for camera in self.cameras.values():
            camera.disconnect()

        logger.info("All publishers stopped")


def detect_realsense_cameras() -> list[dict[str, Any]]:
    """Detect all connected RealSense cameras."""
    try:
        context = rs.context()
        devices = context.query_devices()

        cameras = []
        for device in devices:
            serial = device.get_info(rs.camera_info.serial_number)
            name = device.get_info(rs.camera_info.name)
            product_line = device.get_info(rs.camera_info.product_line)

            cameras.append({
                "serial": serial,
                "name": name,
                "product_line": product_line
            })

        return cameras

    except Exception as e:
        logger.error(f"Error detecting cameras: {e}")
        return []


def load_camera_config_from_yaml(config_path: str) -> dict[str, CameraConfig]:
    """Load camera configuration from YAML file."""
    try:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        cameras = {}
        for cam_name, cam_config in config.get('cameras', {}).items():
            cameras[cam_name] = CameraConfig(
                serial=cam_config['serial'],
                topic=cam_config.get('topic', f'/rgb/{cam_name}'),
                width=cam_config.get('width', 640),
                height=cam_config.get('height', 480),
                fps=cam_config.get('fps', 30),
                color_mode=cam_config.get('color_mode', 'RGB')
            )

        return cameras

    except ImportError:
        logger.error("PyYAML not installed. Install with: pip install pyyaml")
        return {}
    except Exception as e:
        logger.error(f"Error loading config from {config_path}: {e}")
        return {}


def load_camera_config_from_json(json_str: str) -> dict[str, CameraConfig]:
    """Load camera configuration from JSON string."""
    try:
        config = json.loads(json_str)

        cameras = {}
        for cam_name, cam_config in config.items():
            cameras[cam_name] = CameraConfig(
                serial=cam_config['serial'],
                topic=cam_config.get('topic', f'/rgb/{cam_name}'),
                width=cam_config.get('width', 640),
                height=cam_config.get('height', 480),
                fps=cam_config.get('fps', 30),
                color_mode=cam_config.get('color_mode', 'RGB')
            )

        return cameras

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error loading config from JSON: {e}")
        return {}


def auto_detect_cameras(default_width: int = 640, default_height: int = 480, default_fps: int = 30) -> dict[str, CameraConfig]:
    """Auto-detect all RealSense cameras and create default configuration."""
    detected_cameras = detect_realsense_cameras()

    if not detected_cameras:
        logger.warning("No RealSense cameras detected!")
        return {}

    cameras = {}
    for i, cam_info in enumerate(detected_cameras, start=1):
        cam_name = f"camera_{i}"
        cameras[cam_name] = CameraConfig(
            serial=cam_info['serial'],
            topic=f'/rgb/{cam_name}',
            width=default_width,
            height=default_height,
            fps=default_fps,
            color_mode='RGB'
        )
        logger.info(f"Auto-detected: {cam_name} = {cam_info['name']} (SN: {cam_info['serial']})")

    return cameras


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Publish RealSense camera frames to ROS2 topics'
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Path to YAML camera configuration file'
    )
    parser.add_argument(
        '--cameras',
        type=str,
        help='JSON string with camera configuration'
    )
    parser.add_argument(
        '--no-auto-detect',
        action='store_true',
        help='Disable auto-detection of cameras'
    )
    parser.add_argument(
        '--width',
        type=int,
        default=int(os.getenv('LEROBOT_REALSENSE_DEFAULT_WIDTH', '640')),
        help='Default camera width'
    )
    parser.add_argument(
        '--height',
        type=int,
        default=int(os.getenv('LEROBOT_REALSENSE_DEFAULT_HEIGHT', '480')),
        help='Default camera height'
    )
    parser.add_argument(
        '--fps',
        type=int,
        default=int(os.getenv('LEROBOT_REALSENSE_DEFAULT_FPS', '30')),
        help='Default camera FPS'
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_arguments()

    # Get configuration
    cameras: dict[str, CameraConfig] = {}

    # Priority 1: Command line --config
    if args.config:
        logger.info(f"Loading config from {args.config}")
        cameras = load_camera_config_from_yaml(args.config)

    # Priority 2: Environment variable config file
    if not cameras:
        config_file = os.getenv('LEROBOT_REALSENSE_CONFIG_FILE')
        if config_file:
            logger.info(f"Loading config from {config_file}")
            cameras = load_camera_config_from_yaml(config_file)

    # Priority 3: Command line --cameras JSON
    if not cameras and args.cameras:
        logger.info("Loading config from command line JSON")
        cameras = load_camera_config_from_json(args.cameras)

    # Priority 4: Environment variable JSON
    if not cameras:
        cameras_json = os.getenv('LEROBOT_REALSENSE_CAMERAS')
        if cameras_json:
            logger.info("Loading config from environment variable JSON")
            cameras = load_camera_config_from_json(cameras_json)

    # Priority 5: Auto-detect
    if not cameras and not args.no_auto_detect:
        auto_detect = os.getenv('LEROBOT_REALSENSE_AUTO_DETECT', 'true').lower() == 'true'
        if auto_detect:
            logger.info("Auto-detecting cameras...")
            cameras = auto_detect_cameras(args.width, args.height, args.fps)

    if not cameras:
        logger.error("No camera configuration available!")
        logger.error("Please provide config via --config, --cameras, or enable auto-detect")
        sys.exit(1)

    # Print camera configuration
    print("\n" + "="*60)
    print("RealSense to ROS2 Camera Publisher")
    print("="*60)
    for cam_name, cam_config in cameras.items():
        print(f"\n{cam_name}:")
        print(f"  Serial: {cam_config.serial}")
        print(f"  Topic: {cam_config.topic}")
        print(f"  Resolution: {cam_config.width}x{cam_config.height}")
        print(f"  FPS: {cam_config.fps}")
    print("="*60 + "\n")

    # Initialize ROS2
    rclpy.init()

    # Create publisher node
    node = RealSensePublisherNode(cameras)

    if not node.cameras:
        logger.error("No cameras connected successfully!")
        rclpy.shutdown()
        sys.exit(1)

    # Spin in multi-threaded executor
    executor = MultiThreadedExecutor()
    executor.add_node(node)

    try:
        logger.info("Publisher running. Press Ctrl+C to stop.")
        executor.spin()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        node.stop()
        node.destroy_node()
        executor.shutdown()
        try:
            rclpy.shutdown()
        except:
            pass


if __name__ == '__main__':
    main()
