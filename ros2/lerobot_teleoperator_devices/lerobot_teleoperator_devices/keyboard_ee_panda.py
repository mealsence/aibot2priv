from __future__ import annotations

from typing import Any

from lerobot.teleoperators.keyboard.teleop_keyboard import KeyboardEndEffectorTeleop
from lerobot.utils.errors import DeviceNotConnectedError

from .config_keyboard_ee_panda import KeyboardEEPandaTeleopConfig
from .processors.delta_to_joints import set_active_keyboard_ee_config


class KeyboardEEPandaTeleop(KeyboardEndEffectorTeleop):
    """Keyboard teleoperation device for Panda end-effector control.

    This teleoperator uses a letter-key mapping (W/S, A/D, Q/E, L/O) to produce
    Cartesian deltas, which are later converted into joint targets via the Panda
    IK processor pipeline.
    """

    config_class = KeyboardEEPandaTeleopConfig
    name = "keyboard_ee_panda"

    _AXIS_BINDINGS: dict[str, tuple[str, float]] = {
        "w": ("delta_y", -1.0),  # forward
        "s": ("delta_y", 1.0),  # backward
        "a": ("delta_x", 1.0),  # left
        "d": ("delta_x", -1.0),  # right
        "q": ("delta_z", -1.0),  # down
        "e": ("delta_z", 1.0),  # up
    }

    _GRIPPER_BINDINGS: dict[str, float] = {
        "o": 2.0,  # open
        "l": 0.0,  # close
    }

    def __init__(self, config: KeyboardEEPandaTeleopConfig):
        super().__init__(config)
        self.config = config
        set_active_keyboard_ee_config(config)

    def get_action(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(
                "KeyboardTeleop is not connected. You need to run `connect()` before `get_action()`."
            )

        self._drain_pressed_keys()

        delta_x = 0.0
        delta_y = 0.0
        delta_z = 0.0
        gripper_state = 1.0

        for key, is_pressed in self.current_pressed.items():
            if not is_pressed or key is None:
                continue

            key_lower = key.lower()

            if key_lower in self._AXIS_BINDINGS:
                axis_name, direction = self._AXIS_BINDINGS[key_lower]
                if axis_name == "delta_x":
                    delta_x = direction
                elif axis_name == "delta_y":
                    delta_y = direction
                elif axis_name == "delta_z":
                    delta_z = direction
            elif self.config.use_gripper and key_lower in self._GRIPPER_BINDINGS:
                gripper_state = self._GRIPPER_BINDINGS[key_lower]

        self.current_pressed.clear()

        action = {
            "delta_x": delta_x * self.config.linear_step_m,
            "delta_y": delta_y * self.config.linear_step_m,
            "delta_z": delta_z * self.config.linear_step_m,
        }

        if self.config.use_gripper:
            action["gripper"] = gripper_state

        return action
