from dataclasses import dataclass, field
import os

from lerobot.cameras import CameraConfig
from lerobot.robots import RobotConfig


def _get_aibot2_camera_config() -> dict[str, CameraConfig]:
    """Get camera configuration for aibot2 from environment variables or defaults.

    Uses Aibot2Camera (no cv_bridge) to avoid numpy 1.x/2.x incompatibility.
    Camera topics: /camera/camera_{front,left,right,top}/color/image_raw/compressed
    """
    try:
        from .aibot2_camera import Aibot2CameraConfig
        from lerobot.cameras.configs import ColorMode

        camera_width = int(os.getenv("LEROBOT_CAMERA_WIDTH", "320"))
        camera_height = int(os.getenv("LEROBOT_CAMERA_HEIGHT", "240"))
        camera_fps = int(os.getenv("LEROBOT_CAMERA_FPS", "25"))

        default_cameras = {
            "camera_front": "/camera/camera_front/color/image_raw/compressed",
            "camera_left": "/camera/camera_left/color/image_raw/compressed",
            "camera_right": "/camera/camera_right/color/image_raw/compressed",
            "camera_top": "/camera/camera_top/color/image_raw/compressed",
        }

        camera_count = int(os.getenv("LEROBOT_CAMERA_COUNT", str(len(default_cameras))))
        configs = {}
        for i, (name, default_topic) in enumerate(default_cameras.items()):
            if i >= camera_count:
                break
            topic_env = f"LEROBOT_CAMERA_{i+1}_TOPIC"
            topic = os.getenv(topic_env, default_topic)
            configs[name] = Aibot2CameraConfig(
                topic=topic,
                width=camera_width,
                height=camera_height,
                fps=camera_fps,
                color_mode=ColorMode.RGB,
            )
        return configs

    except ImportError:
        return {}


@RobotConfig.register_subclass("aibot2")
@dataclass
class Aibot2Config(RobotConfig):
    """Configuration for the aibot2 (alphabot2) dual-arm humanoid robot.

    Uses Cartesian pose control: publishes geometry_msgs/PoseStamped to each arm.
    Grippers are controlled via std_msgs/Float64.

    Action space: 7 pose values per arm (x,y,z,qx,qy,qz,qw) + 1 gripper per arm = 16 DOF
    Observation: 7 joint positions per arm + 1 gripper per arm + cameras = 16 + images

    Example:
        lerobot-record --robot.type=aibot2 ...
    """

    cameras: dict[str, CameraConfig] = field(default_factory=_get_aibot2_camera_config)

    # --- Joint names for observation (from /joint_states topic) ---
    left_arm_joint_names: list[str] = field(
        default_factory=lambda: [
            "ZPF_left_Joint1",
            "ZPF_left_Joint2",
            "ZPF_left_Joint3",
            "ZPF_left_Joint4",
            "ZPF_left_Joint5",
            "ZPF_left_Joint6",
            "ZPF_left_Joint7",
        ]
    )
    right_arm_joint_names: list[str] = field(
        default_factory=lambda: [
            "ZPF_right_Joint1",
            "ZPF_right_Joint2",
            "ZPF_right_Joint3",
            "ZPF_right_Joint4",
            "ZPF_right_Joint5",
            "ZPF_right_Joint6",
            "ZPF_right_Joint7",
        ]
    )
    left_gripper_joint_name: str = "2FEG_l_Joint1"
    right_gripper_joint_name: str = "2FEG_r_Joint1"

    # --- Command topics ---
    left_arm_cmd_topic: str = "/left_arm_cartesian_direct_cmd"
    right_arm_cmd_topic: str = "/right_arm_cartesian_direct_cmd"
    left_gripper_cmd_topic: str = "/left_gripper_direct_cmd"
    right_gripper_cmd_topic: str = "/right_gripper_direct_cmd"

    # If False, send_action() records/returns actions but does not publish robot
    # commands. Use this when an external VR/internal controller already executes
    # the target poses while LeRobot only records data.
    execute_actions: bool = True
    # How send_action() executes arm pose actions:
    # - "direct": publish separate PoseStamped commands to each arm.
    # - "control_poses_target": publish a PoseArray to the VR/internal driver path.
    action_output_mode: str = "direct"
    control_poses_target_topic: str = "/control_poses_target"
    control_poses_target_frame_id: str = "base_link"

    # --- Joint state topic ---
    joint_state_topic: str = "/joint_states"

    # --- Gripper range (raw joint values from /joint_states) ---
    left_gripper_open_position: float = 0.0
    left_gripper_close_position: float = 1.0
    right_gripper_open_position: float = 0.0
    right_gripper_close_position: float = 1.0
