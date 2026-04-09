from lerobot_teleoperator_devices.processors.delta_to_joints import _make_default_teleop_action_processor_with_keyboard_patch
from typing import Dict
from lerobot.model.kinematics import RobotKinematics
from pathlib import Path
import tempfile
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]

urdf_candidates = [
    PROJECT_ROOT / "ros2" / "isaac_franka_moveit_perception" / "src" / "panda_description" / "urdf" / "panda.urdf",
    PROJECT_ROOT / "isaac_franka_moveit_perception" / "src" / "panda_description" / "urdf" / "panda.urdf",
]
original_urdf = next((path for path in urdf_candidates if path.exists()), None)
if original_urdf is None:
    raise FileNotFoundError(f"Could not locate panda.urdf. Tried: {urdf_candidates}")

urdf_text = original_urdf.read_text()

package_dir = str(original_urdf.parent.parent)
urdf_text = urdf_text.replace("package://panda_description", package_dir)

temp_urdf = tempfile.NamedTemporaryFile(mode="w", suffix=".urdf", delete=False)
temp_urdf.write(urdf_text)
temp_urdf.flush()

kinematics_engine = RobotKinematics(
    urdf_path=temp_urdf.name,
    target_frame_name="panda_hand",
    joint_names=[
        "panda_joint1", "panda_joint2", "panda_joint3",
        "panda_joint4", "panda_joint5", "panda_joint6", "panda_joint7"
    ]
)

def move_robot_arm_delta(cur_joint_pos: list, dx: float, dy: float, dz: float, speed: float = 1.0) -> Dict:
    """Move the robot arm by given positional deltas.

    Args:
        cur_joint_pos: current joint angles
        dx: delta in X-coordinate in meters, + is forward, - is backward
        dy: delta in Y-coordinate in meters, + is forward, - is backward
        dz: delta in Z-coordinate in meters, + is forward, - is backward
        speed: Movement speed (0.1-2.0)
    
    Returns:
        Dictionary with success status and position
    """
    joint_obs_deg = np.rad2deg(np.array(cur_joint_pos, dtype=float))
    current_pose = kinematics_engine.forward_kinematics(joint_obs_deg)

    desired_pose = current_pose.copy()
    desired_pose[:3, 3] += np.array([dx, dy, dz], dtype=float)

    target_joint_deg = kinematics_engine.inverse_kinematics(
        joint_obs_deg,
        desired_pose,
        position_weight=1.0,
        orientation_weight=0.05
    )
    
    target_joint_rad = np.deg2rad(target_joint_deg[:7]).tolist()

    return {
        "success": True,
        "target_joint_positions": target_joint_rad,
        "speed": speed
    }

print(move_robot_arm_delta([0,0,0,0,0,0,0], 0, 0, 1))