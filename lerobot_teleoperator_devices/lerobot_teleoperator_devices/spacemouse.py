import threading
import time
from typing import Any

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import Joy
from lerobot.teleoperators import Teleoperator
from lerobot.utils.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

from .config_spacemouse import SpaceMouseTeleopConfig


class SpaceMouseTeleop(Teleoperator):
    """
    Teleop class to use SpaceMouse (3D mouse) inputs for 6-DOF Cartesian velocity control.
    
    Subscribes to /joy topic where SpaceMouse publishes Joy messages.
    Converts SpaceMouse inputs to Cartesian velocity commands compatible with MoveIt Servo.
    
    Mapping:
    - Axes 0-2: Linear translation (x, y, z)
    - Axes 3-5: Angular rotation (rx, ry, rz)
    - Button 0: Grasp/close gripper
    - Button 1: Open/homing gripper
    """
    
    config_class = SpaceMouseTeleopConfig
    name = "spacemouse"
    
    def __init__(self, config: SpaceMouseTeleopConfig):
        super().__init__(config)
        self.config = config
        self.robot_type = config.type
        
        # ROS2 node and subscriber
        self._ros_node: Node | None = None
        self._joy_subscriber = None
        self._executor_thread: threading.Thread | None = None
        
        # Latest received joy message
        self._latest_joy: Joy | None = None
        self._joy_lock = threading.Lock()
        
        # Gripper state
        self._gripper_state = 1.0  # 1.0 = open, 0.0 = closed
        self._gripper_button_pressed = False
        
    @property
    def action_features(self) -> dict:
        """Return action feature structure for Cartesian velocity control."""
        if self.config.use_gripper:
            return {
                "dtype": "float32",
                "shape": (7,),
                "names": {
                    "linear_x.vel": 0,
                    "linear_y.vel": 1,
                    "linear_z.vel": 2,
                    "angular_x.vel": 3,
                    "angular_y.vel": 4,
                    "angular_z.vel": 5,
                    "gripper.pos": 6,
                },
            }
        else:
            return {
                "dtype": "float32",
                "shape": (6,),
                "names": {
                    "linear_x.vel": 0,
                    "linear_y.vel": 1,
                    "linear_z.vel": 2,
                    "angular_x.vel": 3,
                    "angular_y.vel": 4,
                    "angular_z.vel": 5,
                },
            }
    
    @property
    def feedback_features(self) -> dict:
        """No feedback features for SpaceMouse."""
        return {}
    
    @property
    def is_connected(self) -> bool:
        """Check if SpaceMouse is connected (ROS node is running)."""
        return self._ros_node is not None and rclpy.ok()
    
    @property
    def is_calibrated(self) -> bool:
        """SpaceMouse doesn't require calibration."""
        return True
    
    def connect(self) -> None:
        """Connect to SpaceMouse by subscribing to /joy topic."""
        if self.is_connected:
            raise DeviceAlreadyConnectedError(
                "SpaceMouse is already connected. Do not run `connect()` twice."
            )
        
        # Initialize ROS2 if not already initialized
        if not rclpy.ok():
            rclpy.init()
        
        # Create ROS2 node
        self._ros_node = Node("spacemouse_teleop_node")
        
        # Subscribe to joy topic
        self._joy_subscriber = self._ros_node.create_subscription(
            Joy,
            self.config.joy_topic,
            self._joy_callback,
            10
        )
        
        # Start executor in separate thread
        self._executor_thread = threading.Thread(
            target=self._run_executor,
            daemon=True
        )
        self._executor_thread.start()
        
        # Wait a bit for connection
        time.sleep(0.5)
    
    def _joy_callback(self, msg: Joy):
        """Callback for receiving Joy messages from SpaceMouse."""
        with self._joy_lock:
            self._latest_joy = msg
            
            # Handle gripper buttons
            if len(msg.buttons) >= 2:
                # Button 0: Grasp/close
                if msg.buttons[0] == 1 and not self._gripper_button_pressed:
                    self._gripper_state = 0.0  # Close
                    self._gripper_button_pressed = True
                # Button 1: Open
                elif msg.buttons[1] == 1 and not self._gripper_button_pressed:
                    self._gripper_state = 1.0  # Open
                    self._gripper_button_pressed = True
                # Reset button state when both released
                elif msg.buttons[0] == 0 and msg.buttons[1] == 0:
                    self._gripper_button_pressed = False
    
    def _run_executor(self):
        """Run ROS2 executor in separate thread."""
        executor = SingleThreadedExecutor()
        executor.add_node(self._ros_node)
        try:
            executor.spin()
        except Exception:
            pass  # Node destroyed
    
    def get_action(self) -> dict[str, Any]:
        """Get current action from SpaceMouse.
        
        Returns:
            dict: Action dictionary with linear/angular velocities and gripper position.
        """
        if not self.is_connected:
            raise DeviceNotConnectedError(
                "SpaceMouse is not connected. You need to run `connect()` before `get_action()`."
            )
        
        with self._joy_lock:
            if self._latest_joy is None:
                # Return zero action if no message received yet
                action = {
                    "linear_x.vel": 0.0,
                    "linear_y.vel": 0.0,
                    "linear_z.vel": 0.0,
                    "angular_x.vel": 0.0,
                    "angular_y.vel": 0.0,
                    "angular_z.vel": 0.0,
                }
                if self.config.use_gripper:
                    action["gripper.pos"] = self._gripper_state
                return action
            
            # Extract axes (normalized to [-1, 1])
            if len(self._latest_joy.axes) >= 6:
                orig_x, orig_y, orig_z, orig_rx, orig_ry, orig_rz = self._latest_joy.axes[:6]
            else:
                # Pad with zeros if not enough axes
                axes = list(self._latest_joy.axes) + [0.0] * (6 - len(self._latest_joy.axes))
                orig_x, orig_y, orig_z, orig_rx, orig_ry, orig_rz = axes[:6]
            
            # Apply frame transformation (panda frame mapping)
            # Default: [-y, -x, z, -ry, -rx, rz]
            x = -orig_y if self.config.invert_y else orig_y
            y = -orig_x if self.config.invert_x else orig_x
            z = orig_z if not self.config.invert_z else -orig_z
            rx = -orig_ry if self.config.invert_ry else orig_ry
            ry = -orig_rx if self.config.invert_rx else orig_rx
            rz = orig_rz if not self.config.invert_rz else -orig_rz
            
            # Apply dead zone
            def apply_deadzone(val, threshold):
                if abs(val) < threshold:
                    return 0.0
                return val
            
            x = apply_deadzone(x, self.config.dead_zone)
            y = apply_deadzone(y, self.config.dead_zone)
            z = apply_deadzone(z, self.config.dead_zone)
            rx = apply_deadzone(rx, self.config.dead_zone)
            ry = apply_deadzone(ry, self.config.dead_zone)
            rz = apply_deadzone(rz, self.config.dead_zone)
            
            # Scale to actual velocities
            linear_x = x * self.config.linear_scale
            linear_y = y * self.config.linear_scale
            linear_z = z * self.config.linear_scale
            angular_x = rx * self.config.angular_scale
            angular_y = ry * self.config.angular_scale
            angular_z = rz * self.config.angular_scale
            
            # Build action dictionary
            action = {
                "linear_x.vel": float(linear_x),
                "linear_y.vel": float(linear_y),
                "linear_z.vel": float(linear_z),
                "angular_x.vel": float(angular_x),
                "angular_y.vel": float(angular_y),
                "angular_z.vel": float(angular_z),
            }
            
            if self.config.use_gripper:
                action["gripper.pos"] = float(self._gripper_state)
            
            return action
    
    def disconnect(self) -> None:
        """Disconnect from SpaceMouse."""
        # Make disconnect idempotent - safe to call even if not connected
        if not self.is_connected and self._ros_node is None:
            return
        
        # Destroy subscriber
        if self._joy_subscriber is not None:
            try:
                self._joy_subscriber.destroy()
            except Exception:
                pass
            self._joy_subscriber = None
        
        # Destroy node
        if self._ros_node is not None:
            try:
                self._ros_node.destroy_node()
            except Exception:
                pass
            self._ros_node = None
        
        # Wait for executor thread to finish
        if self._executor_thread is not None:
            self._executor_thread.join(timeout=1.0)
            self._executor_thread = None
        
        # Note: Don't shutdown ROS2 here as other nodes might be using it
        # The teleoperate script will handle ROS2 shutdown
    
    def calibrate(self) -> None:
        """Calibrate SpaceMouse (no-op, doesn't require calibration)."""
        pass
    
    def configure(self) -> None:
        """Configure SpaceMouse (no additional configuration needed)."""
        pass
    
    def send_feedback(self, feedback: dict[str, Any]) -> None:
        """Send feedback to SpaceMouse (not supported)."""
        pass

