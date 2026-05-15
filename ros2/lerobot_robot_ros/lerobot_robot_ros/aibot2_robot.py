import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import cached_property
from typing import Any

from lerobot.cameras.utils import make_cameras_from_configs
from lerobot.robots import Robot
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from .aibot2_config import Aibot2Config
from .aibot2_interface import Aibot2Interface

try:
    from .aibot2_camera import Aibot2Camera
except (ImportError, AttributeError):
    Aibot2Camera = None  # type: ignore

logger = logging.getLogger(__name__)


class Aibot2(Robot):
    """Aibot2 (alphabot2) dual-arm robot with Cartesian pose control.

    Action space: absolute EE pose (x,y,z,qx,qy,qz,qw) per arm + gripper per arm = 16 DOF.
    Observation: joint positions (7 per arm + 1 gripper per arm) + camera images.
    """

    config_class = Aibot2Config
    name = "aibot2"

    def __init__(self, config: Aibot2Config):
        super().__init__(config)
        self.config = config
        self.interface = Aibot2Interface(config)
        self.cameras = make_cameras_from_configs(config.cameras)
        self._camera_read_pool: ThreadPoolExecutor | None = None

    @property
    def _cameras_ft(self) -> dict[str, tuple]:
        return {
            cam: (self.config.cameras[cam].height, self.config.cameras[cam].width, 3)
            for cam in self.cameras
        }

    @cached_property
    def observation_features(self) -> dict[str, type | tuple]:
        obs = {}
        # Left arm joints
        for joint in self.config.left_arm_joint_names:
            obs[f"{joint}.pos"] = float
        # Right arm joints
        for joint in self.config.right_arm_joint_names:
            obs[f"{joint}.pos"] = float
        # Grippers
        obs[f"{self.config.left_gripper_joint_name}.pos"] = float
        obs[f"{self.config.right_gripper_joint_name}.pos"] = float
        # Cameras
        obs.update(self._cameras_ft)
        return obs

    @cached_property
    def action_features(self) -> dict[str, type]:
        return {
            # Left arm EE pose
            "left_arm.x": float,
            "left_arm.y": float,
            "left_arm.z": float,
            "left_arm.qx": float,
            "left_arm.qy": float,
            "left_arm.qz": float,
            "left_arm.qw": float,
            # Right arm EE pose
            "right_arm.x": float,
            "right_arm.y": float,
            "right_arm.z": float,
            "right_arm.qx": float,
            "right_arm.qy": float,
            "right_arm.qz": float,
            "right_arm.qw": float,
            # Grippers (normalized 0=open, 1=closed)
            "left_gripper.pos": float,
            "right_gripper.pos": float,
        }

    @property
    def is_connected(self) -> bool:
        return self.interface.is_connected and all(cam.is_connected for cam in self.cameras.values())

    @property
    def is_calibrated(self) -> bool:
        return True

    def calibrate(self) -> None:
        pass

    def configure(self) -> None:
        pass

    def connect(self, calibrate: bool = True) -> None:
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")

        self.interface.connect()

        if Aibot2Camera is not None:
            for cam in self.cameras.values():
                cam.connect(warmup=False)
                if isinstance(cam, Aibot2Camera):
                    self.interface.add_camera_node(cam.node)
                    logger.info("Added %s to Aibot2Interface executor", cam)
        else:
            for cam in self.cameras.values():
                cam.connect()

        for cam in self.cameras.values():
            logger.info("%s waiting for first frame...", cam)
            try:
                cam.async_read(timeout_ms=5000)
                logger.info("%s first frame received", cam)
            except Exception as e:
                logger.warning("%s no frame within 5s: %s", cam, e)

        if len(self.cameras) > 1:
            self._camera_read_pool = ThreadPoolExecutor(
                max_workers=len(self.cameras),
                thread_name_prefix="aibot2_cam_read",
            )

    def get_observation(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        obs_dict: dict[str, Any] = {}

        joint_state = self.interface.joint_state
        if joint_state is None:
            raise ValueError("Joint state is not available yet.")

        obs_dict.update({f"{joint}.pos": pos for joint, pos in joint_state["position"].items()})
        self._normalize_gripper_observation_inplace(obs_dict)

        def read_camera(cam_key: str, cam) -> tuple[str, Any, float]:
            start = time.perf_counter()
            try:
                image = cam.async_read(timeout_ms=300)
            except Exception as e:
                logger.error("Failed to read camera %s: %s", cam_key, e)
                image = None
            dt_ms = (time.perf_counter() - start) * 1e3
            return cam_key, image, dt_ms

        if self._camera_read_pool is not None:
            futures = [
                self._camera_read_pool.submit(read_camera, cam_key, cam)
                for cam_key, cam in self.cameras.items()
            ]
            for future in as_completed(futures):
                cam_key, image, dt_ms = future.result()
                obs_dict[cam_key] = image
                logger.debug("%s read %s: %.1fms", self, cam_key, dt_ms)
        else:
            for cam_key, cam in self.cameras.items():
                cam_key, image, dt_ms = read_camera(cam_key, cam)
                obs_dict[cam_key] = image
                logger.debug("%s read %s: %.1fms", self, cam_key, dt_ms)

        return obs_dict

    def _normalize_gripper_observation_inplace(self, obs_dict: dict[str, Any]) -> None:
        """Optionally normalize gripper observation to action convention: 0=open, 1=closed."""
        if not self.config.normalize_gripper_observation:
            return

        left_key = f"{self.config.left_gripper_joint_name}.pos"
        right_key = f"{self.config.right_gripper_joint_name}.pos"

        if left_key in obs_dict:
            obs_dict[left_key] = self._normalize_gripper_position(
                raw_value=float(obs_dict[left_key]),
                open_position=float(self.config.left_gripper_open_position),
                close_position=float(self.config.left_gripper_close_position),
            )
        if right_key in obs_dict:
            obs_dict[right_key] = self._normalize_gripper_position(
                raw_value=float(obs_dict[right_key]),
                open_position=float(self.config.right_gripper_open_position),
                close_position=float(self.config.right_gripper_close_position),
            )

    @staticmethod
    def _normalize_gripper_position(raw_value: float, open_position: float, close_position: float) -> float:
        if open_position == close_position:
            return 0.0
        normalized = (open_position - raw_value) / (open_position - close_position)
        return float(max(0.0, min(1.0, normalized)))

    def send_action(self, action: dict[str, float]) -> dict[str, float]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        if not self.config.execute_actions:
            return action

        if self.config.action_output_mode == "control_poses_target":
            self.interface.send_control_poses_target(
                left_pose={
                    "x": float(action["left_arm.x"]),
                    "y": float(action["left_arm.y"]),
                    "z": float(action["left_arm.z"]),
                    "qx": float(action["left_arm.qx"]),
                    "qy": float(action["left_arm.qy"]),
                    "qz": float(action["left_arm.qz"]),
                    "qw": float(action["left_arm.qw"]),
                },
                right_pose={
                    "x": float(action["right_arm.x"]),
                    "y": float(action["right_arm.y"]),
                    "z": float(action["right_arm.z"]),
                    "qx": float(action["right_arm.qx"]),
                    "qy": float(action["right_arm.qy"]),
                    "qz": float(action["right_arm.qz"]),
                    "qw": float(action["right_arm.qw"]),
                },
            )
            self._send_gripper_commands(action)
            return action

        if self.config.action_output_mode != "direct":
            raise ValueError(f"Unsupported AIBOT2 action_output_mode: {self.config.action_output_mode!r}")

        # Send left arm pose
        self.interface.send_left_arm_pose(
            x=float(action["left_arm.x"]),
            y=float(action["left_arm.y"]),
            z=float(action["left_arm.z"]),
            qx=float(action["left_arm.qx"]),
            qy=float(action["left_arm.qy"]),
            qz=float(action["left_arm.qz"]),
            qw=float(action["left_arm.qw"]),
        )

        # Send right arm pose
        self.interface.send_right_arm_pose(
            x=float(action["right_arm.x"]),
            y=float(action["right_arm.y"]),
            z=float(action["right_arm.z"]),
            qx=float(action["right_arm.qx"]),
            qy=float(action["right_arm.qy"]),
            qz=float(action["right_arm.qz"]),
            qw=float(action["right_arm.qw"]),
        )

        self._send_gripper_commands(action)

        return action

    def _send_gripper_commands(self, action: dict[str, float]) -> None:
        # Send gripper commands (unnormalize 0=open, 1=closed to actual range).
        left_grip = max(0.0, min(1.0, float(action.get("left_gripper.pos", 0.0))))
        left_actual = (
            self.config.left_gripper_open_position
            + left_grip * (self.config.left_gripper_close_position - self.config.left_gripper_open_position)
        )
        self.interface.send_left_gripper_command(left_actual)

        right_grip = max(0.0, min(1.0, float(action.get("right_gripper.pos", 0.0))))
        right_actual = (
            self.config.right_gripper_open_position
            + right_grip * (self.config.right_gripper_close_position - self.config.right_gripper_open_position)
        )
        self.interface.send_right_gripper_command(right_actual)

    def disconnect(self) -> None:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        for cam in self.cameras.values():
            cam.disconnect()
        if self._camera_read_pool is not None:
            self._camera_read_pool.shutdown(wait=True)
            self._camera_read_pool = None
        self.interface.disconnect()
        logger.info("%s disconnected.", self)
