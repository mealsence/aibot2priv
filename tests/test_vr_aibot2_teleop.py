from types import SimpleNamespace

from lerobot_teleoperator_devices.config_vr_aibot2 import VRAibot2TeleopConfig
from lerobot_teleoperator_devices.vr_aibot2 import VRAibot2Teleop


def _pose(x, y, z, qx, qy, qz, qw):
    return SimpleNamespace(
        position=SimpleNamespace(x=x, y=y, z=z),
        orientation=SimpleNamespace(x=qx, y=qy, z=qz, w=qw),
    )


def test_control_poses_target_maps_first_pose_to_left_and_second_to_right():
    teleop = VRAibot2Teleop(VRAibot2TeleopConfig(id="test"))

    msg = SimpleNamespace(
        poses=[
            _pose(0.58, 0.39, 0.82, 0.18, 0.03, 0.10, 0.97),
            _pose(0.69, -0.29, 0.86, 0.01, -0.15, 0.02, 0.98),
            _pose(0.01, 0.01, 1.22, -0.00, -0.10, 0.07, 0.99),
        ]
    )

    left_pose, right_pose = teleop._extract_poses(msg)

    assert left_pose is msg.poses[0]
    assert right_pose is msg.poses[1]


def test_gripper_joint_states_normalize_point_8_open_and_0_closed():
    teleop = VRAibot2Teleop(VRAibot2TeleopConfig(id="test"))

    teleop._gripper_joint_state_callback(
        SimpleNamespace(
            name=["2FEG_l_Joint1", "2FEG_r_Joint1"],
            position=[0.8, 0.0],
        )
    )

    assert teleop._latest_action["left_gripper.pos"] == 0.0
    assert teleop._latest_action["right_gripper.pos"] == 1.0
