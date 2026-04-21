from __future__ import annotations

import sys
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

import numpy as np

from lerobot.configs.types import FeatureType, PipelineFeatureType, PolicyFeature
from lerobot.model.kinematics import RobotKinematics
from lerobot.processor import factory as _factory_module
from lerobot.processor.core import TransitionKey
from lerobot.processor.pipeline import ProcessorStepRegistry, RobotActionProcessorStep
from lerobot.teleoperators.keyboard.configuration_keyboard import KeyboardEndEffectorTeleopConfig

if TYPE_CHECKING:  # pragma: no cover
    from ..config_keyboard_ee_panda import KeyboardEEPandaTeleopConfig


_CACHE_DIR = Path(__file__).resolve().parent / "_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _repo_root() -> Path:
    """lerobot_teleoperator_devices/processors/delta_to_joints.py -> parents[4] == repo root."""
    return Path(__file__).resolve().parents[4]


def _colcon_src_roots(repo_root: Path) -> list[Path]:
    """Paths where ROS packages live (this repo uses ros2/isaac_franka_moveit_perception/src)."""
    candidates = [
        repo_root / "ros2" / "isaac_franka_moveit_perception" / "src",
        repo_root / "isaac_franka_moveit_perception" / "src",
    ]
    return [p for p in candidates if p.is_dir()]


def _to_numpy(array_like: Sequence[float]) -> np.ndarray:
    arr = np.asarray(array_like, dtype=float)
    if arr.shape != (3,):
        raise ValueError("Workspace bounds must contain exactly three values (x, y, z).")
    return arr


@ProcessorStepRegistry.register("keyboard_ee_delta_to_joints")
@dataclass
class KeyboardEEDeltaToJointStep(RobotActionProcessorStep):
    """Convert end-effector deltas into Panda joint commands via IK."""

    kinematics: RobotKinematics
    joint_names: Sequence[str]
    gripper_joint_name: str
    position_weight: float
    orientation_weight: float
    workspace_min: np.ndarray
    workspace_max: np.ndarray
    gripper_limits: tuple[float, float]
    gripper_step: float
    _current_pose: np.ndarray | None = field(default=None, init=False, repr=False)
    _current_gripper: float | None = field(default=None, init=False, repr=False)

    def action(self, action: dict[str, float]) -> dict[str, float]:
        observation = self.transition.get(TransitionKey.OBSERVATION)
        if observation is None:
            raise ValueError("Robot observation is required for end-effector teleoperation.")

        joint_obs = []
        for joint in self.joint_names:
            key = f"{joint}.pos"
            if key not in observation:
                raise ValueError(f"Observation missing joint position for '{joint}'.")
            joint_obs.append(float(observation[key]))
        joint_obs_rad = np.asarray(joint_obs, dtype=float)
        joint_obs_deg = np.rad2deg(joint_obs_rad)

        if self._current_pose is None:
            self._current_pose = self.kinematics.forward_kinematics(joint_obs_deg)

        delta_vector = np.array(
            [
                float(action.pop("delta_x", 0.0)),
                float(action.pop("delta_y", 0.0)),
                float(action.pop("delta_z", 0.0)),
            ],
            dtype=float,
        )
        if delta_vector.shape != (3,):
            raise ValueError("Delta vector must contain exactly three elements.")

        desired_pose = self._current_pose.copy()
        desired_translation = desired_pose[:3, 3] + delta_vector
        desired_translation = np.clip(desired_translation, self.workspace_min, self.workspace_max)
        desired_pose[:3, 3] = desired_translation

        q_target_deg = self.kinematics.inverse_kinematics(
            joint_obs_deg,
            desired_pose,
            position_weight=self.position_weight,
            orientation_weight=self.orientation_weight,
        )
        q_target_rad = np.deg2rad(q_target_deg[: len(self.joint_names)])
        self._current_pose = self.kinematics.forward_kinematics(q_target_deg)

        for joint, value in zip(self.joint_names, q_target_rad):
            action[f"{joint}.pos"] = float(value)

        gripper_delta = float(action.pop("gripper_delta", 0.0))

        lower_limit, upper_limit = sorted(self.gripper_limits)
        span = upper_limit - lower_limit

        if self._current_gripper is None:
            observed_gripper = float(
                observation.get(f"{self.gripper_joint_name}.pos", lower_limit)
            )
            self._current_gripper = float(
                np.clip(observed_gripper, lower_limit, upper_limit)
            )

        gripper_state = action.pop("gripper", None)
        state_applied = False
        if gripper_state is not None:
            gripper_state = float(gripper_state)
            if gripper_state <= 0.5:
                self._current_gripper = lower_limit
                state_applied = True
            elif gripper_state >= 1.5:
                self._current_gripper = upper_limit
                state_applied = True

        if not state_applied and gripper_delta != 0.0:
            self._current_gripper = float(
                np.clip(self._current_gripper + gripper_delta, lower_limit, upper_limit)
            )

        if span <= 0:
            normalized_gripper = 0.0
        else:
            normalized_gripper = (self._current_gripper - lower_limit) / span
        action["gripper.pos"] = float(np.clip(normalized_gripper, 0.0, 1.0))

        return action

    def transform_features(
        self, features: dict[PipelineFeatureType, dict[str, PolicyFeature]]
    ) -> dict[PipelineFeatureType, dict[str, PolicyFeature]]:
        action_features = features.setdefault(PipelineFeatureType.ACTION, {})
        for key in ["delta_x", "delta_y", "delta_z", "gripper_delta", "gripper"]:
            action_features.pop(key, None)

        for joint in self.joint_names:
            action_features[f"{joint}.pos"] = PolicyFeature(type=FeatureType.ACTION, shape=(1,))
        action_features["gripper.pos"] = PolicyFeature(type=FeatureType.ACTION, shape=(1,))
        return features

    def reset(self) -> None:
        self._current_pose = None
        self._current_gripper = None


_ACTIVE_CONFIG: KeyboardEndEffectorTeleopConfig | None = None
_ORIGINAL_MAKE_DEFAULT_TELEOP_PROCESSOR = _factory_module.make_default_teleop_action_processor


def set_active_keyboard_ee_config(config: KeyboardEndEffectorTeleopConfig | None) -> None:
    """Store config so that the processor factory can attach the IK step."""

    global _ACTIVE_CONFIG
    _ACTIVE_CONFIG = config


def _resolve_urdf_path(urdf_path: str) -> str:
    """Return a URDF path with ROS package URLs resolved to absolute file paths."""

    repo_root = _repo_root()
    src_roots = _colcon_src_roots(repo_root)

    if urdf_path.startswith("package://"):
        # Resolve package://panda_description/... under colcon src (ros2/.../src)
        package_prefix = "package://"
        package_path = urdf_path[len(package_prefix) :]
        parts = package_path.split("/", 1)
        package_name = parts[0]
        relative_path = parts[1] if len(parts) > 1 else ""

        resolved_path: Path | None = None
        for src in src_roots:
            candidate = (src / package_name / relative_path) if relative_path else (src / package_name)
            if candidate.exists():
                resolved_path = candidate
                break
        if resolved_path is None:
            legacy = repo_root / package_name / relative_path if relative_path else repo_root / package_name
            resolved_path = legacy
    else:
        resolved_path = Path(urdf_path).expanduser().resolve()

    if not resolved_path.exists():
        raise FileNotFoundError(f"URDF path does not exist: {resolved_path}")

    # Always process URDF contents to resolve package:// mesh references
    urdf_text = resolved_path.read_text()

    # Check if the URDF contains any package:// references that need resolving
    if "package://" in urdf_text:
        cache_path = _CACHE_DIR / (resolved_path.stem + "_resolved.urdf")

        # Replace package://pkg/ with absolute paths for each package under colcon src
        if not src_roots:
            raise FileNotFoundError(
                "URDF references package:// meshes but no Isaac/MoveIt source tree was found. "
                f"Expected one of: "
                f"{repo_root / 'ros2' / 'isaac_franka_moveit_perception' / 'src'}, "
                f"{repo_root / 'isaac_franka_moveit_perception' / 'src'}"
            )
        for isaac_workspace in src_roots:
            if not isaac_workspace.is_dir():
                continue
            for package_dir in isaac_workspace.iterdir():
                if package_dir.is_dir():
                    pkg = package_dir.name
                    urdf_text = urdf_text.replace(
                        f"package://{pkg}/",
                        f"{package_dir.as_posix()}/",
                    )

        cache_path.write_text(urdf_text)
        return str(cache_path)

    return str(resolved_path)


def _build_keyboard_ee_step(config: KeyboardEndEffectorTeleopConfig) -> KeyboardEEDeltaToJointStep:
    kinematics = RobotKinematics(
        urdf_path=_resolve_urdf_path(config.urdf_path),
        target_frame_name=config.ee_frame,
        joint_names=list(config.joint_names),
    )
    return KeyboardEEDeltaToJointStep(
        kinematics=kinematics,
        joint_names=tuple(config.joint_names),
        gripper_joint_name=config.gripper_joint_name,
        position_weight=config.position_weight,
        orientation_weight=config.orientation_weight,
        workspace_min=_to_numpy(config.workspace_min),
        workspace_max=_to_numpy(config.workspace_max),
        gripper_limits=(float(config.gripper_limits[0]), float(config.gripper_limits[1])),
        gripper_step=float(config.gripper_step),
    )


@wraps(_ORIGINAL_MAKE_DEFAULT_TELEOP_PROCESSOR)
def _make_default_teleop_action_processor_with_keyboard_patch():
    teleop_processor = _ORIGINAL_MAKE_DEFAULT_TELEOP_PROCESSOR()

    global _ACTIVE_CONFIG
    config = _ACTIVE_CONFIG
    if config is not None:
        if not any(isinstance(step, KeyboardEEDeltaToJointStep) for step in teleop_processor.steps):
            steps = list(teleop_processor.steps)
            steps.append(_build_keyboard_ee_step(config))
            teleop_processor.steps = steps
        _ACTIVE_CONFIG = None

    return teleop_processor


if not getattr(_factory_module.make_default_teleop_action_processor, "_keyboard_ee_panda_wrapped", False):
    _factory_module.make_default_teleop_action_processor = (
        _make_default_teleop_action_processor_with_keyboard_patch
    )
    setattr(_factory_module.make_default_teleop_action_processor, "_keyboard_ee_panda_wrapped", True)

    # Ensure the package-level alias points to the patched function.
    import lerobot.processor as _processor_pkg

    _processor_pkg.make_default_teleop_action_processor = _make_default_teleop_action_processor_with_keyboard_patch

    # Update already-imported modules (e.g., teleoperation script) to use the patched function.
    teleop_module = sys.modules.get("lerobot.scripts.lerobot_teleoperate")
    if teleop_module is not None:
        setattr(
            teleop_module,
            "make_default_teleop_action_processor",
            _make_default_teleop_action_processor_with_keyboard_patch,
        )
