#!/usr/bin/env python3
#
# Copyright 2026 ROBOTIS CO., LTD.
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
#
# Author: Seongwoo Kim

"""Action node for rotating the mobile base by a specified angle."""

import math
import threading
import time
from typing import TYPE_CHECKING

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from physical_ai_bt.actions.base_action import BaseAction
from physical_ai_bt.actions.base_action import NodeStatus
from rclpy.qos import QoSProfile
from rclpy.qos import ReliabilityPolicy
from trajectory_msgs.msg import JointTrajectory

if TYPE_CHECKING:
    from rclpy.node import Node


class Rotate(BaseAction):
    """Action to rotate the mobile base by a target angle in degrees."""

    @staticmethod
    def angle_diff_deg(a, b):
        """Calculate the difference between two angles in degrees."""
        d = a - b
        while d > 180:
            d -= 360
        while d < -180:
            d += 360
        return d

    def __init__(
            self,
            node: 'Node',
            angle_deg: float = 90.0,
            topic_config: dict = None
    ):
        """Initialize the Rotate action."""
        super().__init__(node, name='Rotate')
        self.angle_deg = angle_deg
        self.topic_config = topic_config or {}
        if not isinstance(self.topic_config, dict):
            self.topic_config = {}
        self.angular_velocity = 0.2

        qos_profile = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE
        )

        self.publishers = {}
        if self.topic_config and 'topic_map' in self.topic_config:
            topic_map = self.topic_config['topic_map']
            for joint_group, topic in topic_map.items():
                if joint_group == 'leader_mobile':
                    pub = self.node.create_publisher(
                        Twist,
                        topic,
                        qos_profile
                    )
                    self.publishers[joint_group] = pub
        else:
            self.trajectory_pub = self.node.create_publisher(
                JointTrajectory,
                '/leader/joint_trajectory',
                qos_profile
            )

        self.odom_sub = self.node.create_subscription(
            Odometry,
            '/odom',
            self._odom_callback,
            qos_profile
        )
        self.odom_start_yaw = None
        self.odom_last_yaw = None

        self._thread = None
        self._thread_done = False
        self._thread_success = False
        self._control_rate = 100  # Hz

    def _odom_callback(self, msg):
        """Receive odometry updates and compute yaw angle."""
        q = msg.pose.pose.orientation
        siny_cosp = 2 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        if self.odom_start_yaw is None:
            self.odom_start_yaw = yaw
        self.odom_last_yaw = yaw

    def _control_loop(self):
        """Control loop that publishes velocity and monitors rotation."""
        rate_sleep = 1.0 / self._control_rate

        timeout_count = 0
        max_init_timeout = 500
        while (
            self.odom_start_yaw is None and timeout_count < max_init_timeout
        ):
            time.sleep(0.01)
            timeout_count += 1

        if self.odom_start_yaw is None:
            self.log_error('Timeout waiting for odom data')
            self._thread_done = True
            self._thread_success = False
            return

        while not self._thread_done:
            if self.odom_last_yaw is None:
                time.sleep(rate_sleep)
                continue

            start_deg = math.degrees(self.odom_start_yaw)
            last_deg = math.degrees(self.odom_last_yaw)
            delta_deg = self.angle_diff_deg(last_deg, start_deg)
            delta_deg_norm = ((delta_deg + 180) % 360) - 180

            tolerance = 0.1
            error = self.angle_deg - delta_deg_norm

            if abs(error) <= tolerance:
                self._stop_mobile()
                norm_str = f'{delta_deg_norm:.2f}'
                target_str = str(self.angle_deg)
                msg = (
                    f'[Thread] Rotation complete: {norm_str} deg '
                    f'(target: {target_str} deg)'
                )
                self.log_info(msg)
                self._thread_success = True
                self._thread_done = True
                break

            if error > 0:
                angular_z = self.angular_velocity
            else:
                angular_z = -self.angular_velocity

            if 'leader_mobile' in self.publishers:
                twist_msg = Twist()
                twist_msg.linear.x = 0.0
                twist_msg.linear.y = 0.0
                twist_msg.angular.z = angular_z
                self.publishers['leader_mobile'].publish(twist_msg)

            time.sleep(rate_sleep)

    def tick(self) -> NodeStatus:
        """Execute the action and return its status."""
        if self._thread is None:
            self.odom_start_yaw = None
            self.odom_last_yaw = None
            self._thread_done = False
            self._thread_success = False

            self._thread = threading.Thread(
                target=self._control_loop, daemon=True
            )
            self._thread.start()
            angle_str = str(self.angle_deg)
            self.log_info(f'Rotate thread started (target: {angle_str} deg)')
            return NodeStatus.RUNNING

        if self._thread_done:
            if self._thread_success:
                return NodeStatus.SUCCESS
            else:
                return NodeStatus.FAILURE

        return NodeStatus.RUNNING

    def _stop_mobile(self):
        """Stop the mobile base by publishing zero velocity."""
        if 'leader_mobile' in self.publishers:
            twist_msg = Twist()
            self.publishers['leader_mobile'].publish(twist_msg)
            self.log_info('Mobile base stopped')

    def reset(self):
        """Reset the action to its initial state."""
        super().reset()
        if self._thread is not None and self._thread.is_alive():
            self._thread_done = True
            self._thread.join(timeout=1.0)
        self._thread = None
        self._thread_done = False
        self._thread_success = False
        self.odom_start_yaw = None
        self.odom_last_yaw = None
