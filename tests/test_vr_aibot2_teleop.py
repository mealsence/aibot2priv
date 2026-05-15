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


def test_hand_states_use_first_value_left_second_value_right():
    teleop = VRAibot2Teleop(VRAibot2TeleopConfig(id="test"))

    teleop._hand_state_callback(
        SimpleNamespace(
            data=[800, 0],
        )
    )

    # hand_states defaults: open=800 -> 0.0, close=0 -> 1.0
    assert teleop._latest_action["left_gripper.pos"] == 0.0
    assert teleop._latest_action["right_gripper.pos"] == 1.0


def test_hand_state_normalization_clips_to_normalized_action_range():
    teleop = VRAibot2Teleop(VRAibot2TeleopConfig(id="test"))

    teleop._hand_state_callback(
        SimpleNamespace(
            data=[1000, -200],
        )
    )

    assert teleop._latest_action["left_gripper.pos"] == 0.0
    assert teleop._latest_action["right_gripper.pos"] == 1.0


def test_control_pose_callback_preserves_hand_state_gripper_action():
    teleop = VRAibot2Teleop(VRAibot2TeleopConfig(id="test"))
    teleop._hand_state_callback(SimpleNamespace(data=[0, 800]))

    teleop._target_callback(
        SimpleNamespace(
            poses=[
                _pose(0.58, 0.39, 0.82, 0.18, 0.03, 0.10, 0.97),
                _pose(0.69, -0.29, 0.86, 0.01, -0.15, 0.02, 0.98),
            ]
        )
    )

    assert teleop._latest_action["left_gripper.pos"] == 1.0
    assert teleop._latest_action["right_gripper.pos"] == 0.0
