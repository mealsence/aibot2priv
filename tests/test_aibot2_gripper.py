from types import SimpleNamespace

from lerobot_robot_ros.aibot2_robot import Aibot2


def test_gripper_commands_clip_normalized_actions_before_mapping():
    robot = object.__new__(Aibot2)
    robot.config = SimpleNamespace(
        left_gripper_open_position=0.8,
        left_gripper_close_position=0.0,
        right_gripper_open_position=0.8,
        right_gripper_close_position=0.0,
    )

    sent = {}
    robot.interface = SimpleNamespace(
        send_left_gripper_command=lambda value: sent.setdefault("left", value),
        send_right_gripper_command=lambda value: sent.setdefault("right", value),
    )

    robot._send_gripper_commands(
        {
            "left_gripper.pos": -0.25,
            "right_gripper.pos": 1.25,
        }
    )

    assert sent["left"] == 0.8
    assert sent["right"] == 0.0
