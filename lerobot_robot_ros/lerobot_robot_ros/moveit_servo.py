# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging

from geometry_msgs.msg import TwistStamped
from rclpy import qos
from rclpy.callback_groups import CallbackGroup
from rclpy.node import Node
from std_srvs.srv import SetBool, Trigger

# Conditional import for ROS2 Jazzy compatibility (not available in Humble)
try:
    from moveit_msgs.srv import ServoCommandType
    SERVO_COMMAND_TYPE_AVAILABLE = True
except ImportError:
    SERVO_COMMAND_TYPE_AVAILABLE = False
    ServoCommandType = None

logger = logging.getLogger(__name__)


class MoveIt2Servo:
    """
    Python interface for MoveIt2 Servo.
    """

    def __init__(
        self,
        node: "Node",
        frame_id: str,
        callback_group: "CallbackGroup",
    ):
        self._node = node
        self._frame_id = frame_id
        self._enabled = False

        # Log which version we're using
        if SERVO_COMMAND_TYPE_AVAILABLE:
            logger.info("MoveIt Servo: Running with Jazzy/Rolling API (dynamic command type switching)")
        else:
            logger.info("MoveIt Servo: Running with Humble API (static TWIST command configuration)")
            logger.info("Make sure your servo YAML is configured to accept TWIST commands on /servo_node/delta_twist_cmds")

        self._twist_pub = node.create_publisher(
            TwistStamped,
            "/servo_node/delta_twist_cmds",
            qos.QoSProfile(
                durability=qos.QoSDurabilityPolicy.VOLATILE,
                reliability=qos.QoSReliabilityPolicy.RELIABLE,
                history=qos.QoSHistoryPolicy.KEEP_ALL,
            ),
            callback_group=callback_group,
        )
        
        # In Humble, use Trigger services; in Jazzy+, use SetBool for pause_servo
        if SERVO_COMMAND_TYPE_AVAILABLE:
            # Jazzy+ API: pause_servo uses SetBool
            self._pause_srv = node.create_client(
                SetBool, "/servo_node/pause_servo", callback_group=callback_group
            )
            self._enable_req = SetBool.Request(data=False)
            self._disable_req = SetBool.Request(data=True)
        else:
            # Humble API: use start_servo/stop_servo/pause_servo with Trigger
            self._start_srv = node.create_client(
                Trigger, "/servo_node/start_servo", callback_group=callback_group
            )
            self._stop_srv = node.create_client(
                Trigger, "/servo_node/stop_servo", callback_group=callback_group
            )
            self._pause_srv = node.create_client(
                Trigger, "/servo_node/pause_servo", callback_group=callback_group
            )
            self._enable_req = Trigger.Request()
            self._disable_req = Trigger.Request()

        # Command type switching service (only available in Jazzy+)
        if SERVO_COMMAND_TYPE_AVAILABLE:
            self._cmd_type_srv = node.create_client(
                ServoCommandType, "/servo_node/switch_command_type", callback_group=callback_group
            )
            self._twist_type_req = ServoCommandType.Request(command_type=ServoCommandType.Request.TWIST)
        else:
            self._cmd_type_srv = None
            self._twist_type_req = None

        self._twist_msg = TwistStamped()

    def enable(self, wait_for_server_timeout_sec=1.0) -> bool:
        if SERVO_COMMAND_TYPE_AVAILABLE:
            # Jazzy+ API: use pause_servo with SetBool and command type switching
            if not self._pause_srv.wait_for_service(timeout_sec=wait_for_server_timeout_sec):
                logger.warning("Pause service not available.")
                return False
            if not self._cmd_type_srv.wait_for_service(timeout_sec=wait_for_server_timeout_sec):
                logger.warning("Command type service not available.")
                return False
            result = self._pause_srv.call(self._enable_req)
            if not result or not result.success:
                logger.error(f"Enable failed: {getattr(result, 'message', '')}")
                self._enabled = False
                return False
            cmd_result = self._cmd_type_srv.call(self._twist_type_req)
            if not cmd_result or not cmd_result.success:
                logger.error("Switch to TWIST command type failed.")
                self._enabled = False
                return False
        else:
            # Humble API: use start_servo with Trigger (no command type switching)
            if not self._start_srv.wait_for_service(timeout_sec=wait_for_server_timeout_sec):
                logger.warning("Start service not available.")
                return False
            result = self._start_srv.call(self._enable_req)
            if not result or not result.success:
                logger.error(f"Enable failed: {getattr(result, 'message', '')}")
                self._enabled = False
                return False
        
        logger.info("MoveIt Servo enabled.")
        self._enabled = True
        return True

    def disable(self, wait_for_server_timeout_sec=1.0) -> bool:
        if SERVO_COMMAND_TYPE_AVAILABLE:
            # Jazzy+ API: use pause_servo with SetBool
            if not self._pause_srv.wait_for_service(timeout_sec=wait_for_server_timeout_sec):
                logger.warning("Pause service not available.")
                return False
            result = self._pause_srv.call(self._disable_req)
        else:
            # Humble API: use stop_servo with Trigger
            if not self._stop_srv.wait_for_service(timeout_sec=wait_for_server_timeout_sec):
                logger.warning("Stop service not available.")
                return False
            result = self._stop_srv.call(self._disable_req)
        
        self._enabled = not (result and result.success)
        return bool(result and result.success)

    def servo(self, linear=(0.0, 0.0, 0.0), angular=(0.0, 0.0, 0.0), enable_if_disabled=True):
        if not self._enabled and enable_if_disabled and not self.enable():
            logger.warning("Dropping servo command because MoveIt2 Servo is not enabled.")
            return

        self._twist_msg.header.frame_id = self._frame_id
        self._twist_msg.header.stamp = self._node.get_clock().now().to_msg()
        self._twist_msg.twist.linear.x = float(linear[0])
        self._twist_msg.twist.linear.y = float(linear[1])
        self._twist_msg.twist.linear.z = float(linear[2])
        self._twist_msg.twist.angular.x = float(angular[0])
        self._twist_msg.twist.angular.y = float(angular[1])
        self._twist_msg.twist.angular.z = float(angular[2])
        self._twist_pub.publish(self._twist_msg)
