"""ROS2 camera that converts Image/CompressedImage messages without cv_bridge.

cv_bridge from ROS2 humble is compiled against numpy 1.x and crashes with numpy 2.x.
This module does the Image → numpy conversion manually, avoiding the dependency.

Supports both raw topics (sensor_msgs/Image) and compressed topics
(sensor_msgs/CompressedImage, topic ending in /compressed).
"""

import logging
from dataclasses import dataclass
from threading import Event, Lock
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage, Image

from lerobot.cameras.camera import Camera
from lerobot.cameras.configs import CameraConfig, ColorMode
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

logger = logging.getLogger(__name__)

# Encoding → (numpy dtype, channels)
_ENCODING_INFO = {
    "rgb8": (np.uint8, 3),
    "bgr8": (np.uint8, 3),
    "rgba8": (np.uint8, 4),
    "bgra8": (np.uint8, 4),
    "mono8": (np.uint8, 1),
    "8UC1": (np.uint8, 1),
    "8UC3": (np.uint8, 3),
    "16UC1": (np.uint16, 1),
    "32FC1": (np.float32, 1),
}


def imgmsg_to_numpy(msg: Image, target_encoding: str = "rgb8") -> NDArray:
    """Convert sensor_msgs/Image to numpy array without cv_bridge."""
    enc = msg.encoding
    if enc not in _ENCODING_INFO:
        raise ValueError(f"Unsupported encoding: {enc}")

    dtype, channels = _ENCODING_INFO[enc]
    img = np.frombuffer(msg.data, dtype=dtype).reshape(msg.height, msg.width, channels)

    # Convert color if needed
    if target_encoding == "rgb8":
        if enc == "bgr8":
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        elif enc == "bgra8":
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        elif enc == "rgba8":
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
    elif target_encoding == "bgr8":
        if enc == "rgb8":
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    return img


@CameraConfig.register_subclass("aibot2_camera")
@dataclass(kw_only=True)
class Aibot2CameraConfig(CameraConfig):
    """Camera config for aibot2 — uses manual Image conversion (no cv_bridge)."""
    topic: str
    color_mode: ColorMode = ColorMode.RGB


class Aibot2Camera(Camera):
    """ROS2 camera without cv_bridge dependency."""

    def __init__(self, config: Aibot2CameraConfig):
        super().__init__(config)
        self.config = config
        self.topic = config.topic
        self.color_mode = config.color_mode
        self.node: Node | None = None
        self.subscription = None
        self.frame_lock = Lock()
        self.latest_frame: NDArray[Any] | None = None
        self.new_frame_event = Event()
        self.frames_received = 0

    def __str__(self) -> str:
        return f"Aibot2Camera({self.topic})"

    @property
    def is_connected(self) -> bool:
        return self.node is not None and self.subscription is not None

    def connect(self, warmup: bool = True) -> None:
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")

        import rclpy
        if not rclpy.ok():
            rclpy.init()

        node_name = f'cam_{self.topic.replace("/", "_").strip("_")}'
        self.node = Node(node_name)

        self._compressed = self.topic.endswith("/compressed")
        if self._compressed:
            self.subscription = self.node.create_subscription(
                CompressedImage, self.topic, self._compressed_image_callback, 10
            )
        else:
            self.subscription = self.node.create_subscription(
                Image, self.topic, self._image_callback, 10
            )
        logger.info("%s connected to %s (%s)", self, self.topic,
                    "compressed" if self._compressed else "raw")

        if warmup:
            logger.info("%s waiting for first frame...", self)
            if not self.new_frame_event.wait(timeout=5.0):
                logger.warning("%s no frame within 5s", self)
            else:
                logger.info("%s first frame received", self)

    def _image_callback(self, msg: Image) -> None:
        try:
            target = "rgb8" if self.color_mode == ColorMode.RGB else "bgr8"
            img = imgmsg_to_numpy(msg, target_encoding=target)

            if self.width and self.height:
                if img.shape[1] != self.width or img.shape[0] != self.height:
                    img = cv2.resize(img, (self.width, self.height), interpolation=cv2.INTER_AREA)

            with self.frame_lock:
                self.latest_frame = img
                self.frames_received += 1
            self.new_frame_event.set()
        except Exception as e:
            logger.error("%s failed to convert image: %s", self, e)

    def _compressed_image_callback(self, msg: CompressedImage) -> None:
        try:
            buf = np.frombuffer(msg.data, dtype=np.uint8)
            img = cv2.imdecode(buf, cv2.IMREAD_COLOR)  # always decodes to BGR
            if img is None:
                logger.error("%s failed to decode compressed image", self)
                return

            if self.color_mode == ColorMode.RGB:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            if self.width and self.height:
                if img.shape[1] != self.width or img.shape[0] != self.height:
                    img = cv2.resize(img, (self.width, self.height), interpolation=cv2.INTER_AREA)

            with self.frame_lock:
                self.latest_frame = img
                self.frames_received += 1
            self.new_frame_event.set()
        except Exception as e:
            logger.error("%s failed to convert compressed image: %s", self, e)

    def read(self, color_mode: ColorMode | None = None) -> NDArray[Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected")
        if not self.new_frame_event.wait(timeout=1.0):
            raise TimeoutError(f"{self} no frame within 1s")
        with self.frame_lock:
            if self.latest_frame is None:
                raise ValueError(f"{self} no frame available")
            frame = self.latest_frame.copy()
        return frame

    def async_read(self, timeout_ms: float = 200) -> NDArray[Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected")
        if not self.new_frame_event.wait(timeout=timeout_ms / 1000.0):
            raise TimeoutError(f"{self} no frame within {timeout_ms}ms")
        with self.frame_lock:
            if self.latest_frame is None:
                raise ValueError(f"{self} no frame available")
            frame = self.latest_frame.copy()
        return frame

    def disconnect(self) -> None:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected")
        if self.node and self.subscription:
            self.node.destroy_subscription(self.subscription)
        if self.node:
            self.node.destroy_node()
        self.node = None
        self.subscription = None
        with self.frame_lock:
            self.latest_frame = None
        self.new_frame_event.clear()
        logger.info("%s disconnected (%d frames)", self, self.frames_received)

    @staticmethod
    def find_cameras() -> list[dict[str, Any]]:
        import rclpy
        if not rclpy.ok():
            rclpy.init()
        temp_node = Node("camera_finder")
        try:
            image_types = {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"}
            return [
                {"topic": name, "type": next(t for t in types if t in image_types)}
                for name, types in temp_node.get_topic_names_and_types()
                if any(t in image_types for t in types)
            ]
        finally:
            temp_node.destroy_node()
