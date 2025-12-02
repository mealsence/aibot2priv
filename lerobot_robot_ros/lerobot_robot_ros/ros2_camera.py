# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Provides the ROS2Camera class for capturing frames from ROS2 image topics.
"""

import logging
from dataclasses import dataclass
from threading import Event, Lock
from typing import Any

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from numpy.typing import NDArray
from rclpy.node import Node
from sensor_msgs.msg import Image

from lerobot.cameras.camera import Camera
from lerobot.cameras.configs import CameraConfig, ColorMode
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

logger = logging.getLogger(__name__)


@CameraConfig.register_subclass("ros2_topic")
@dataclass(kw_only=True)
class ROS2CameraConfig(CameraConfig):
    """Configuration for ROS2 image topic camera.

    Attributes:
        topic: ROS2 image topic to subscribe to (e.g., "/camera_1", "/camera/rgb")
        color_mode: Color format for the output frame (RGB or BGR). Default is RGB.
        fps: Target frames per second (for compatibility with LeRobot recording)
        width: Image width in pixels
        height: Image height in pixels

    Example:
        ```python
        from lerobot_robot_ros.ros2_camera import ROS2CameraConfig

        config = ROS2CameraConfig(
            topic="/camera_1",
            width=1280,
            height=720,
            fps=30,
            color_mode=ColorMode.RGB
        )
        ```
    """
    topic: str
    color_mode: ColorMode = ColorMode.RGB


class ROS2Camera(Camera):
    """
    Camera implementation that subscribes to ROS2 image topics.

    This class provides integration between LeRobot's camera interface and ROS2's
    sensor_msgs/Image messages. It subscribes to a specified image topic and caches
    the latest frame for efficient reading during teleoperation or data collection.

    The camera uses cv_bridge to convert ROS2 Image messages to numpy arrays,
    and implements thread-safe frame caching to avoid blocking the ROS2 callback thread.

    Example:
        ```python
        from lerobot_robot_ros.ros2_camera import ROS2Camera, ROS2CameraConfig

        # Create configuration
        config = ROS2CameraConfig(
            topic="/camera_1",
            width=1280,
            height=720,
            fps=30
        )

        # Create and connect camera
        camera = ROS2Camera(config)
        camera.connect()

        # Read frames
        frame = camera.async_read(timeout_ms=300)
        print(frame.shape)  # (720, 1280, 3)

        # Disconnect when done
        camera.disconnect()
        ```

    Note:
        The ROS2 node created by this camera should be added to an existing
        executor (such as the one in ROS2Interface) to avoid spinning a separate
        thread for each camera.
    """

    def __init__(self, config: ROS2CameraConfig):
        """
        Initializes the ROS2Camera instance.

        Args:
            config: The configuration settings for the camera.
        """
        super().__init__(config)

        self.config = config
        self.topic = config.topic
        self.color_mode = config.color_mode

        # ROS2 components
        self.bridge = CvBridge()
        self.node: Node | None = None
        self.subscription = None

        # Thread-safe frame caching
        self.frame_lock = Lock()
        self.latest_frame: NDArray[Any] | None = None
        self.new_frame_event = Event()

        # Statistics
        self.frames_received = 0

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.topic})"

    @property
    def is_connected(self) -> bool:
        """Checks if the camera is currently connected and receiving frames."""
        return self.node is not None and self.subscription is not None

    def connect(self, warmup: bool = True) -> None:
        """
        Connects to the ROS2 image topic.

        Creates a ROS2 node and subscribes to the specified image topic. If warmup
        is True, waits for the first frame to arrive before returning.

        Args:
            warmup: If True (default), waits for the first frame before returning.
                   This ensures the camera is ready to provide images immediately
                   after connection.

        Raises:
            DeviceAlreadyConnectedError: If the camera is already connected.
            TimeoutError: If warmup is True and no frame is received within 5 seconds.
        """
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")

        # Initialize ROS2 if needed
        if not rclpy.ok():
            rclpy.init()

        # Create node with unique name
        node_name = f'camera_{self.topic.replace("/", "_").strip("_")}'
        self.node = Node(node_name)

        # Subscribe to image topic
        self.subscription = self.node.create_subscription(
            Image,
            self.topic,
            self._image_callback,
            10  # QoS queue size
        )

        logger.info(f"{self} connected to topic {self.topic}")

        if warmup:
            # Wait for first frame
            logger.info(f"{self} waiting for first frame...")
            if not self.new_frame_event.wait(timeout=5.0):
                logger.warning(f"{self} did not receive a frame within 5 seconds")
            else:
                logger.info(f"{self} received first frame")

    def _image_callback(self, msg: Image) -> None:
        """
        ROS2 callback to store latest image.

        This callback is invoked by ROS2's executor when a new image message arrives.
        It converts the ROS2 Image message to a numpy array, resizes if necessary,
        and caches it for subsequent read operations.

        Args:
            msg: ROS2 Image message from the subscribed topic.
        """
        try:
            # Convert ROS Image to OpenCV/numpy format
            if self.color_mode == ColorMode.RGB:
                cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='rgb8')
            else:  # BGR
                cv_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

            # Resize if configured dimensions don't match actual image size
            if self.width and self.height:
                if cv_image.shape[1] != self.width or cv_image.shape[0] != self.height:
                    cv_image = cv2.resize(cv_image, (self.width, self.height), interpolation=cv2.INTER_AREA)

            # Cache the frame with thread safety
            with self.frame_lock:
                self.latest_frame = cv_image
                self.frames_received += 1

            # Signal that new frame is available
            self.new_frame_event.set()

        except Exception as e:
            logger.error(f"{self} failed to convert ROS image: {e}")

    def read(self, color_mode: ColorMode | None = None) -> NDArray[Any]:
        """
        Synchronously read the latest frame from the camera.

        This method blocks until a new frame arrives, making it suitable for
        applications that need guaranteed fresh frames.

        Args:
            color_mode: Desired color mode for the output frame. If None,
                       uses the camera's configured color mode. Currently not
                       implemented for runtime color conversion.

        Returns:
            np.ndarray: Captured frame as a numpy array with shape (H, W, 3).

        Raises:
            DeviceNotConnectedError: If the camera is not connected.
            TimeoutError: If no frame is received within 1 second.
        """
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected")

        # Wait for a new frame
        if not self.new_frame_event.wait(timeout=1.0):
            raise TimeoutError(f"{self} no frame received within 1 second")

        # Get the frame
        with self.frame_lock:
            if self.latest_frame is None:
                raise ValueError(f"{self} no frame available")
            frame = self.latest_frame.copy()

        # Clear the event to wait for next frame
        self.new_frame_event.clear()

        return frame

    def async_read(self, timeout_ms: float = 200) -> NDArray[Any]:
        """
        Asynchronously read the latest cached frame from the camera.

        This method returns the most recently received frame without blocking,
        making it suitable for high-frequency teleoperation and data collection.

        Args:
            timeout_ms: Maximum time to wait for a frame in milliseconds.
                       Default is 200ms.

        Returns:
            np.ndarray: Captured frame as a numpy array with shape (H, W, 3).

        Raises:
            DeviceNotConnectedError: If the camera is not connected.
            TimeoutError: If no frame has been received within the timeout period.
        """
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected")

        # Wait for a frame with timeout
        if not self.new_frame_event.wait(timeout=timeout_ms / 1000.0):
            raise TimeoutError(f"{self} no frame received within {timeout_ms}ms")

        # Get the latest frame (don't clear the event, so multiple reads can succeed)
        with self.frame_lock:
            if self.latest_frame is None:
                raise ValueError(f"{self} no frame available")
            frame = self.latest_frame.copy()

        return frame

    def disconnect(self) -> None:
        """
        Disconnect from the ROS2 topic and release resources.

        Destroys the subscription and node, and resets internal state.

        Raises:
            DeviceNotConnectedError: If the camera is not connected.
        """
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected")

        # Clean up ROS2 components
        if self.node and self.subscription:
            self.node.destroy_subscription(self.subscription)

        if self.node:
            self.node.destroy_node()

        self.node = None
        self.subscription = None

        # Reset state
        with self.frame_lock:
            self.latest_frame = None
        self.new_frame_event.clear()

        logger.info(f"{self} disconnected (received {self.frames_received} frames)")

    @staticmethod
    def find_cameras() -> list[dict[str, Any]]:
        """
        Find available ROS2 image topics.

        This method queries the ROS2 graph for available topics that publish
        sensor_msgs/Image messages.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries containing information
                                  about each discovered image topic.

        Example:
            ```python
            available_cameras = ROS2Camera.find_cameras()
            for cam in available_cameras:
                print(f"Topic: {cam['topic']}, Type: {cam['type']}")
            ```
        """
        if not rclpy.ok():
            rclpy.init()

        # Create temporary node to query topics
        temp_node = Node('camera_finder')

        try:
            topic_list = temp_node.get_topic_names_and_types()

            cameras = []
            for topic_name, topic_types in topic_list:
                # Check if topic publishes Image messages
                if 'sensor_msgs/msg/Image' in topic_types:
                    cameras.append({
                        'topic': topic_name,
                        'type': 'sensor_msgs/msg/Image'
                    })

            return cameras

        finally:
            temp_node.destroy_node()
