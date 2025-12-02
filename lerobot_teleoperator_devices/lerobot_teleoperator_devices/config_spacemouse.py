from dataclasses import dataclass, field

from lerobot.teleoperators.config import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("spacemouse")
@dataclass
class SpaceMouseTeleopConfig(TeleoperatorConfig):
    """Configuration for SpaceMouse teleoperator.
    
    SpaceMouse publishes Joy messages to /joy topic with:
    - axes[0-5]: Translation (x, y, z) and rotation (rx, ry, rz)
    - buttons[0]: Grasp button
    - buttons[1]: Homing/open button
    """
    
    # ROS topic for SpaceMouse input
    # Note: spacenav_node publishes to /spacenav/joy by default
    # Either remap: ros2 run spacenav spacenav_node --ros-args -r /spacenav/joy:=/joy
    # Or set joy_topic="/spacenav/joy" in your config
    joy_topic: str = "/spacenav/joy"
    
    # Scale factors for velocity commands (normalized [-1, 1] to actual velocities)
    linear_scale: float = 0.4  # Max linear velocity [m/s]
    angular_scale: float = 0.8  # Max angular velocity [rad/s]
    
    # Enable gripper control
    use_gripper: bool = True
    
    # Frame transformation (SpaceMouse axes to robot frame)
    # Default: panda frame mapping [-y, -x, z, -ry, -rx, rz]
    invert_x: bool = True
    invert_y: bool = True
    invert_z: bool = False
    invert_rx: bool = True
    invert_ry: bool = True
    invert_rz: bool = False
    
    # 4DoF control mode (only x, y, z, rz) with automatic rx/ry compensation
    four_dof_control: bool = False
    
    # Dead zone threshold (ignore small movements)
    dead_zone: float = 0.05

