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

"""Action node for moving both robot arms to specified joint positions."""

import threading
import time
from typing import List
from typing import TYPE_CHECKING

from physical_ai_bt.actions.base_action import BaseAction
from physical_ai_bt.actions.base_action import NodeStatus
from rclpy.qos import QoSProfile
from rclpy.qos import ReliabilityPolicy
from trajectory_msgs.msg import JointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint

if TYPE_CHECKING:
    from rclpy.node import Node


class MoveArms(BaseAction):
    """Action to move both robot arms to target joint positions."""

    def __init__(
            self,
            node: 'Node',
            left_positions: List[float],
            right_positions: List[float],
            position_threshold: float = 0.01,
            duration: float = 2.0,
    ):
        """Initialize the MoveArms action."""
        super().__init__(node, name='MoveArms')
        self.left_joint_names = [
            'arm_l_joint1', 'arm_l_joint2', 'arm_l_joint3', 'arm_l_joint4',
            'arm_l_joint5', 'arm_l_joint6', 'arm_l_joint7',
            'gripper_l_joint1'
        ]
        self.right_joint_names = [
            'arm_r_joint1', 'arm_r_joint2', 'arm_r_joint3', 'arm_r_joint4',
            'arm_r_joint5', 'arm_r_joint6', 'arm_r_joint7',
            'gripper_r_joint1'
        ]
        self.left_positions = left_positions
        self.right_positions = right_positions
        self.position_threshold = position_threshold
        self.duration = duration
        qos_profile = QoSProfile(
            depth=10, reliability=ReliabilityPolicy.RELIABLE
        )
        topic_left = (
            '/leader/joint_trajectory_command_broadcaster_left/'
            'joint_trajectory'
        )
        self.left_pub = self.node.create_publisher(
            JointTrajectory,
            topic_left,
            qos_profile
        )
        topic_right = (
            '/leader/joint_trajectory_command_broadcaster_right/'
            'joint_trajectory'
        )
        self.right_pub = self.node.create_publisher(
            JointTrajectory,
            topic_right,
            qos_profile
        )
        self.command_sent = False
        self.start_time = None
        self.joint_state = None
        from sensor_msgs.msg import JointState
        self.joint_state_sub = self.node.create_subscription(
            JointState,
            '/joint_states',
            self._joint_state_callback,
            qos_profile
        )

        self._thread = None
        self._thread_done = False
        self._thread_success = False
        self._control_rate = 100  # Hz

    def _joint_state_callback(self, msg):
        """Receive joint state updates."""
        self.joint_state = msg

    def _control_loop(self):
        """Control loop that publishes trajectories and monitors progress."""
        rate_sleep = 1.0 / self._control_rate

        left_traj = JointTrajectory()
        left_traj.joint_names = self.left_joint_names
        left_point = JointTrajectoryPoint()
        left_point.positions = self.left_positions
        left_point.time_from_start.sec = int(self.duration)
        left_traj.points.append(left_point)
        self.left_pub.publish(left_traj)

        right_traj = JointTrajectory()
        right_traj.joint_names = self.right_joint_names
        right_point = JointTrajectoryPoint()
        right_point.positions = self.right_positions
        right_point.time_from_start.sec = int(self.duration)
        right_traj.points.append(right_point)
        self.right_pub.publish(right_traj)

        self.log_info('Arms trajectory published')

        timeout_count = 0
        while not self._thread_done and timeout_count < 1500:  # 30s timeout
            if self.joint_state is None:
                time.sleep(rate_sleep)
                timeout_count += 1
                continue

            name_to_idx = {
                n: i for i, n in enumerate(self.joint_state.name)
            }
            all_reached = True

            for jname, target in zip(
                self.left_joint_names, self.left_positions
            ):
                idx = name_to_idx.get(jname)
                if idx is not None:
                    pos = self.joint_state.position[idx]
                    if abs(pos - target) > self.position_threshold:
                        all_reached = False
                        break
                else:
                    all_reached = False
                    break

            if all_reached:
                for jname, target in zip(
                    self.right_joint_names, self.right_positions
                ):
                    idx = name_to_idx.get(jname)
                    if idx is not None:
                        pos = self.joint_state.position[idx]
                        if abs(pos - target) > self.position_threshold:
                            all_reached = False
                            break
                    else:
                        all_reached = False
                        break

            if all_reached:
                self.log_info('Arms reached target positions')
                self._thread_success = True
                self._thread_done = True
                break

            time.sleep(rate_sleep)
            timeout_count += 1

        if not self._thread_success and not self._thread_done:
            self.log_error('Arms timeout waiting for target positions')
            self._thread_done = True

    def tick(self) -> NodeStatus:
        """Execute the action and return its status."""
        if self._thread is None:
            self.joint_state = None
            self._thread_done = False
            self._thread_success = False

            self._thread = threading.Thread(
                target=self._control_loop, daemon=True
            )
            self._thread.start()
            self.log_info('Arms thread started')
            return NodeStatus.RUNNING

        if self._thread_done:
            if self._thread_success:
                return NodeStatus.SUCCESS
            else:
                return NodeStatus.FAILURE

        return NodeStatus.RUNNING

    def reset(self):
        """Reset the action to its initial state."""
        super().reset()
        if self._thread is not None and self._thread.is_alive():
            self._thread_done = True
            self._thread.join(timeout=1.0)
        self._thread = None
        self._thread_done = False
        self._thread_success = False
        self.joint_state = None
