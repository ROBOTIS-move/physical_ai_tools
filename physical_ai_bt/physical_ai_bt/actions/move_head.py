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


import threading
import time
from typing import TYPE_CHECKING, List
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
from physical_ai_bt.actions.base_action import NodeStatus, BaseAction
from rclpy.qos import QoSProfile, ReliabilityPolicy

if TYPE_CHECKING:
    from rclpy.node import Node

class MoveHead(BaseAction):
    def __init__(
            self,
            node: 'Node',
            head_positions: List[float] = None,
            position_threshold: float = 0.01,
        ):
        super().__init__(node, name="MoveHead")
        self.head_joint_names = ["head_joint1", "head_joint2"]
        self.head_positions = head_positions if head_positions else [0.0, 0.0]
        self.position_threshold = position_threshold

        qos_profile = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self.head_pub = self.node.create_publisher(
            JointTrajectory,
            "/leader/joystick_controller_left/joint_trajectory",
            qos_profile
        )

        self.joint_state = None
        from sensor_msgs.msg import JointState
        self.joint_state_sub = self.node.create_subscription(
            JointState,
            "/joint_states",
            self._joint_state_callback,
            qos_profile
        )

        self._thread = None
        self._thread_done = False
        self._thread_success = False
        self._control_rate = 100  # Hz

    def _joint_state_callback(self, msg):
        self.joint_state = msg

    def _control_loop(self):
        rate_sleep = 1.0 / self._control_rate

        self.log_info(f'Publishing head trajectory: {self.head_positions}')

        head_traj = JointTrajectory()
        head_traj.joint_names = self.head_joint_names
        head_point = JointTrajectoryPoint()
        head_point.positions = self.head_positions
        head_point.time_from_start.sec = 5
        head_traj.points.append(head_point)
        self.head_pub.publish(head_traj)

        self.log_info("Head trajectory published")

        timeout_count = 0
        while not self._thread_done and timeout_count < 1000:
            if self.joint_state is None:
                time.sleep(rate_sleep)
                timeout_count += 1
                continue

            name_to_idx = {n: i for i, n in enumerate(self.joint_state.name)}
            all_reached = True

            for jname, target in zip(self.head_joint_names, self.head_positions):
                idx = name_to_idx.get(jname)
                if idx is not None:
                    pos = self.joint_state.position[idx]
                    if abs(pos - target) > self.position_threshold:
                        all_reached = False
                        break

            if all_reached:
                self.log_info("Head reached target positions")
                self._thread_success = True
                self._thread_done = True
                break

            time.sleep(rate_sleep)
            timeout_count += 1

        if not self._thread_success and not self._thread_done:
            self.log_error("Head timeout waiting for target positions")
            self._thread_done = True

    def tick(self) -> NodeStatus:
        if self._thread is None:
            self.joint_state = None
            self._thread_done = False
            self._thread_success = False

            self._thread = threading.Thread(target=self._control_loop, daemon=True)
            self._thread.start()
            self.log_info(f"MoveHead started with positions: {self.head_positions}")
            return NodeStatus.RUNNING

        if self._thread_done:
            return NodeStatus.SUCCESS if self._thread_success else NodeStatus.FAILURE

        return NodeStatus.RUNNING

    def reset(self):
        super().reset()
        if self._thread is not None and self._thread.is_alive():
            self._thread_done = True
            self._thread.join(timeout=1.0)
        self._thread = None
        self._thread_done = False
        self._thread_success = False
        self.joint_state = None
