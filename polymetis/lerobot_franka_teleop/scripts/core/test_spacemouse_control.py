import argparse
import logging
import time
from pathlib import Path

import yaml
from lerobot_robot_franka import Franka, FrankaConfig
from lerobot_teleoperator_franka import SpacemouseTeleopConfig, create_teleop


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def _load_record_cfg(cfg_path: Path) -> dict:
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["record"]


def _make_teleop_config(record_cfg: dict) -> SpacemouseTeleopConfig:
    sm_cfg = record_cfg.get("teleop", {}).get("spacemouse_config", {})
    return SpacemouseTeleopConfig(
        use_gripper=sm_cfg.get("use_gripper", True),
        pose_scaler=sm_cfg.get("pose_scaler", [1.0, 1.0]),
        channel_signs=sm_cfg.get("channel_signs", [1, 1, 1, 1, 1, 1]),
    )


def _make_robot_config(record_cfg: dict) -> FrankaConfig:
    robot_cfg = record_cfg["robot"]
    return FrankaConfig(
        robot_ip=robot_cfg["ip"],
        use_gripper=robot_cfg["use_gripper"],
        close_threshold=robot_cfg["close_threshold"],
        gripper_reverse=robot_cfg["gripper_reverse"],
        gripper_bin_threshold=robot_cfg["gripper_bin_threshold"],
        gripper_max_open=robot_cfg.get("gripper_max_open", 0.08),
        control_mode="spacemouse",
        debug=False,
        cameras={},
    )


def run_test(cfg_path: Path, hz: float, teleop_only: bool) -> None:
    record_cfg = _load_record_cfg(cfg_path)
    teleop = create_teleop(_make_teleop_config(record_cfg))
    robot = None
    period = 1.0 / hz

    try:
        teleop.connect()
        logger.info("[TEST] SpaceMouse connected.")

        if not teleop_only:
            robot = Franka(_make_robot_config(record_cfg))
            robot.connect()
            logger.info("[TEST] Franka connected in spacemouse mode.")
            logger.info("[TEST] Streaming SpaceMouse actions to Franka. Press Ctrl+C to stop.")
        else:
            logger.info("[TEST] Teleop-only mode. Move SpaceMouse to inspect actions. Press Ctrl+C to stop.")

        while True:
            action = teleop.get_action()
            if teleop_only:
                compact = {k: round(float(v), 4) for k, v in action.items()}
                logger.info(f"[ACTION] {compact}")
            else:
                robot.send_action(action)
            time.sleep(period)

    except KeyboardInterrupt:
        logger.info("\n[TEST] Interrupted by user.")
    finally:
        if robot is not None:
            robot.disconnect()
            logger.info("[TEST] Franka disconnected.")
        teleop.disconnect()
        logger.info("[TEST] SpaceMouse disconnected.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simple SpaceMouse control test for Polymetis Franka teleoperation."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "config" / "record_cfg.yaml",
        help="Path to record_cfg.yaml",
    )
    parser.add_argument(
        "--hz",
        type=float,
        default=20.0,
        help="Control loop frequency.",
    )
    parser.add_argument(
        "--teleop-only",
        action="store_true",
        help="Only print SpaceMouse actions without commanding Franka.",
    )
    args = parser.parse_args()

    if args.hz <= 0:
        raise ValueError("--hz must be > 0")

    run_test(cfg_path=args.config, hz=args.hz, teleop_only=args.teleop_only)


if __name__ == "__main__":
    main()
