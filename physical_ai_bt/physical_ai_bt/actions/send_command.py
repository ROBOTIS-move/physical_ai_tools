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

"""Action node for calling SendCommand service on physical_ai_server."""

import threading
import time
from typing import TYPE_CHECKING

from physical_ai_bt.actions.base_action import BaseAction
from physical_ai_bt.bt_core import NodeStatus
from physical_ai_interfaces.msg import TaskInfo
from physical_ai_interfaces.msg import TaskStatus
from physical_ai_interfaces.srv import SendCommand
from rclpy.qos import QoSProfile
from rclpy.qos import ReliabilityPolicy

if TYPE_CHECKING:
    from rclpy.node import Node

COMMAND_MAP = {
    'START_INFERENCE': SendCommand.Request.START_INFERENCE,
    'STOP_INFERENCE': SendCommand.Request.STOP_INFERENCE,
    'RESUME_INFERENCE': SendCommand.Request.RESUME_INFERENCE,
    'START_RECORD': SendCommand.Request.START_RECORD,
    'STOP': SendCommand.Request.STOP,
    'START_INFERENCE_RECORD': SendCommand.Request.START_INFERENCE_RECORD,
    'STOP_INFERENCE_RECORD': SendCommand.Request.STOP_INFERENCE_RECORD,
}

SERVICE_CALL_TIMEOUT_SEC = 30.0
LOADING_TIMEOUT_SEC = 120.0
LOADING_POLL_INTERVAL_SEC = 0.5


class SendCommandAction(BaseAction):
    """Action to call SendCommand service on physical_ai_server."""

    def __init__(
        self,
        node: 'Node',
        command: str = 'STOP_INFERENCE',
        policy_path: str = '',
        task_instruction: str = '',
        task_name: str = '',
        wait_until_ready: bool = False,
        service_name: str = '/task/command',
    ):
        """Initialize the SendCommand action."""
        super().__init__(node, name='SendCommand')
        self.command_str = command
        self.policy_path = policy_path
        self.task_instruction = task_instruction
        self.task_name = task_name
        self.wait_until_ready = wait_until_ready

        self._client = self.node.create_client(SendCommand, service_name)

        self._latest_phase = None
        self._phase_lock = threading.Lock()
        if self.wait_until_ready:
            qos = QoSProfile(
                depth=10,
                reliability=ReliabilityPolicy.RELIABLE,
            )
            self._status_sub = self.node.create_subscription(
                TaskStatus,
                '/task/status',
                self._status_callback,
                qos,
            )
        else:
            self._status_sub = None

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = None
        self._result = None

    def _status_callback(self, msg: TaskStatus):
        """Receive TaskStatus updates for wait_until_ready polling."""
        with self._phase_lock:
            self._latest_phase = msg.phase

    def _execute(self):
        """Background thread: call service and optionally wait for ready."""
        command_val = COMMAND_MAP.get(self.command_str)
        if command_val is None:
            self.log_error(f'Unknown command: {self.command_str}')
            with self._lock:
                self._result = False
            return

        if not self._client.wait_for_service(timeout_sec=SERVICE_CALL_TIMEOUT_SEC):
            self.log_error('SendCommand service not available')
            with self._lock:
                self._result = False
            return

        req = SendCommand.Request()
        req.command = command_val

        if self.command_str in ('START_INFERENCE', 'RESUME_INFERENCE'):
            req.task_info = TaskInfo()
            req.task_info.policy_path = self.policy_path
            req.task_info.task_name = self.task_name
            if self.task_instruction:
                req.task_info.task_instruction = [self.task_instruction]

        future = self._client.call_async(req)

        start_time = time.monotonic()
        while not future.done():
            if self._stop_event.is_set():
                future.cancel()
                return
            if time.monotonic() - start_time > SERVICE_CALL_TIMEOUT_SEC:
                self.log_error('Service call timed out')
                future.cancel()
                with self._lock:
                    self._result = False
                return
            time.sleep(0.05)

        response = future.result()
        if response is None or not response.success:
            msg = response.message if response else 'No response'
            self.log_error(f'SendCommand failed: {msg}')
            with self._lock:
                self._result = False
            return

        self.log_info(f'SendCommand {self.command_str}: {response.message}')

        if self.wait_until_ready and self.command_str == 'START_INFERENCE':
            if not self._wait_for_loading_complete():
                with self._lock:
                    self._result = False
                return

        with self._lock:
            self._result = True

    def _wait_for_loading_complete(self) -> bool:
        """Poll TaskStatus topic until phase leaves LOADING."""
        start_time = time.monotonic()
        self.log_info('Waiting for model loading to complete...')

        while not self._stop_event.is_set():
            elapsed = time.monotonic() - start_time
            if elapsed > LOADING_TIMEOUT_SEC:
                self.log_error('Model loading timed out')
                return False

            with self._phase_lock:
                phase = self._latest_phase

            if phase is not None and phase != TaskStatus.LOADING:
                if phase in (TaskStatus.INFERENCING, TaskStatus.PAUSED):
                    self.log_info(f'Model loaded (phase={phase})')
                    return True
                elif phase == TaskStatus.READY:
                    pass
                else:
                    self.log_warn(f'Unexpected phase {phase} during loading')

            time.sleep(LOADING_POLL_INTERVAL_SEC)

        return False

    def tick(self) -> NodeStatus:
        """Execute the action and return its status."""
        if self._thread is None:
            self._stop_event.clear()
            with self._lock:
                self._result = None

            self._thread = threading.Thread(
                target=self._execute, daemon=True
            )
            self._thread.start()
            self.log_info(
                f'SendCommand thread started (command={self.command_str})'
            )
            return NodeStatus.RUNNING

        with self._lock:
            result = self._result

        if result is None:
            return NodeStatus.RUNNING
        return NodeStatus.SUCCESS if result else NodeStatus.FAILURE

    def reset(self):
        """Reset the action to its initial state."""
        super().reset()
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        with self._lock:
            self._result = None
