#!/usr/bin/env python3
"""
SpaceMouse bridge for Franka Cartesian velocity control.

Reads /spacenav/twist and publishes scaled, deadzone-filtered velocities
to /cartesian_twist_controller/cmd_vel at 50 Hz.

Button 0 (rising edge) toggles enable/disable with 300ms debounce.
Publishes zeros when disabled or when SpaceMouse data is stale (> 0.5s).

Usage:
    python3 spacemouse_cartesian_vel.py

Requirements:
    ros2 run spacenav spacenav_node   # SpaceMouse driver
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Joy
import time


LINEAR_SCALE = 0.05   # m/s per unit input
ANGULAR_SCALE = 0.1   # rad/s per unit input
DEADZONE = 0.1        # applied per-axis before scaling
STALE_TIMEOUT = 0.5   # seconds before SpaceMouse is considered stale
PUBLISH_RATE = 50.0   # Hz
DEBOUNCE_TIME = 0.3   # seconds for button debounce


def apply_deadzone(value: float, threshold: float) -> float:
    if abs(value) < threshold:
        return 0.0
    # Scale so output starts from 0 at the deadzone boundary
    sign = 1.0 if value > 0.0 else -1.0
    return sign * (abs(value) - threshold) / (1.0 - threshold)


class SpaceMouseCartesianBridge(Node):
    def __init__(self):
        super().__init__('spacemouse_cartesian_vel')

        self.enabled = False
        self.last_twist_time = None
        self.last_button0_state = False
        self.last_button_toggle_time = 0.0

        # Latest SpaceMouse twist (raw)
        self.latest_linear = [0.0, 0.0, 0.0]
        self.latest_angular = [0.0, 0.0, 0.0]

        # Subscriptions
        self.twist_sub = self.create_subscription(
            Twist, '/spacenav/twist', self._twist_callback, 10)
        self.joy_sub = self.create_subscription(
            Joy, '/spacenav/joy', self._joy_callback, 10)

        # Publisher
        self.cmd_pub = self.create_publisher(
            Twist, '/cartesian_twist_controller/cmd_vel', 10)

        # Timer at 50 Hz
        self.timer = self.create_timer(1.0 / PUBLISH_RATE, self._publish_cmd)

        self.get_logger().info(
            'SpaceMouse bridge ready. Press Button 0 to enable/disable. '
            f'linear_scale={LINEAR_SCALE} m/s, angular_scale={ANGULAR_SCALE} rad/s, '
            f'deadzone={DEADZONE}'
        )

    def _twist_callback(self, msg: Twist):
        self.latest_linear = [msg.linear.x, msg.linear.y, msg.linear.z]
        self.latest_angular = [msg.angular.x, msg.angular.y, msg.angular.z]
        self.last_twist_time = time.monotonic()

    def _joy_callback(self, msg: Joy):
        if len(msg.buttons) < 1:
            return

        button0_pressed = bool(msg.buttons[0])
        now = time.monotonic()

        # Rising-edge detection with debounce
        if button0_pressed and not self.last_button0_state:
            if (now - self.last_button_toggle_time) >= DEBOUNCE_TIME:
                self.enabled = not self.enabled
                self.last_button_toggle_time = now
                state_str = 'ENABLED' if self.enabled else 'DISABLED'
                self.get_logger().info(f'Control {state_str}')

        self.last_button0_state = button0_pressed

    def _publish_cmd(self):
        cmd = Twist()

        if not self.enabled:
            self.cmd_pub.publish(cmd)  # publish zeros
            return

        # Check for stale SpaceMouse data
        if self.last_twist_time is None:
            self.cmd_pub.publish(cmd)
            return

        age = time.monotonic() - self.last_twist_time
        if age > STALE_TIMEOUT:
            self.get_logger().warn(
                f'SpaceMouse data stale ({age:.2f}s). Publishing zeros.',
                throttle_duration_sec=2.0)
            self.cmd_pub.publish(cmd)
            return

        # Apply deadzone and scale
        cmd.linear.x = apply_deadzone(self.latest_linear[0], DEADZONE) * LINEAR_SCALE
        cmd.linear.y = apply_deadzone(self.latest_linear[1], DEADZONE) * LINEAR_SCALE
        cmd.linear.z = apply_deadzone(self.latest_linear[2], DEADZONE) * LINEAR_SCALE
        cmd.angular.x = apply_deadzone(self.latest_angular[0], DEADZONE) * ANGULAR_SCALE
        cmd.angular.y = apply_deadzone(self.latest_angular[1], DEADZONE) * ANGULAR_SCALE
        cmd.angular.z = apply_deadzone(self.latest_angular[2], DEADZONE) * ANGULAR_SCALE

        self.cmd_pub.publish(cmd)


def main():
    rclpy.init()
    node = SpaceMouseCartesianBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # Publish zeros on shutdown for safety
        zero = Twist()
        node.cmd_pub.publish(zero)
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
