#!/usr/bin/env python3
#
# Copyright 2025 ROBOTIS CO., LTD.
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
# Author: Physical AI Team

"""
ZenohGR00TClient - ROS2 Service Client for GR00T Docker communication.

Uses ROS2 standard Service Client with rmw_zenoh middleware.
rmw_zenoh automatically handles Zenoh protocol conversion, enabling
communication with GR00T Docker container's zenoh_ros2_sdk server.

Architecture:
- physical_ai_server uses ROS2 + rmw_zenoh (standard ROS2 API)
- groot container uses zenoh_ros2_sdk (no ROS2 installed)
- rmw_zenoh converts ROS2 messages to Zenoh protocol = COMPATIBLE
"""

import logging
from typing import Optional

from physical_ai_interfaces.srv import (
    GetActionChunk,
    StartInference,
    StopTraining,
)
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.node import Node

from physical_ai_server.communication.zenoh_lerobot_client import LeRobotResponse

logger = logging.getLogger(__name__)


class ZenohGR00TClient:
    """Client for communicating with GR00T Docker container via ROS2 + rmw_zenoh."""

    SERVICE_INFER = "/groot/infer"
    SERVICE_STOP = "/groot/stop"
    SERVICE_GET_ACTION_CHUNK = "/groot/get_action_chunk"

    def __init__(self, node: Node, timeout_sec: float = 30.0):
        self._node = node
        self.timeout_sec = timeout_sec
        self._connected = False
        self._callback_group: Optional[MutuallyExclusiveCallbackGroup] = None

        self._infer_client = None
        self._stop_client = None
        self._action_chunk_client = None

    def connect(self) -> bool:
        """Create ROS2 service clients for GR00T container."""
        if self._connected:
            return True

        if self._node is None:
            logger.error("No ROS2 node provided")
            return False

        try:
            self._callback_group = MutuallyExclusiveCallbackGroup()

            self._infer_client = self._node.create_client(
                StartInference,
                self.SERVICE_INFER,
                callback_group=self._callback_group,
            )
            self._stop_client = self._node.create_client(
                StopTraining,
                self.SERVICE_STOP,
                callback_group=self._callback_group,
            )
            self._action_chunk_client = self._node.create_client(
                GetActionChunk,
                self.SERVICE_GET_ACTION_CHUNK,
                callback_group=self._callback_group,
            )

            self._connected = True
            logger.info("Connected to GR00T services via ROS2 rmw_zenoh")
            return True
        except Exception as e:
            logger.error(f"GR00T connection failed: {e}")
            return False

    def disconnect(self):
        """Destroy service clients."""
        clients = [
            ("_infer_client", self._infer_client),
            ("_stop_client", self._stop_client),
            ("_action_chunk_client", self._action_chunk_client),
        ]
        for name, client in clients:
            if client is not None:
                try:
                    self._node.destroy_client(client)
                except Exception as e:
                    logger.debug(f"Error destroying client {name}: {e}")

        self._infer_client = None
        self._stop_client = None
        self._action_chunk_client = None
        self._connected = False

    def _call_service(
        self, client, request, service_name: str, timeout_sec: float = None
    ) -> LeRobotResponse:
        """Call a ROS2 service and return LeRobotResponse."""
        if not self._connected:
            return LeRobotResponse(
                success=False,
                message="Not connected to GR00T services",
                data={},
                request_id="",
            )

        if client is None:
            return LeRobotResponse(
                success=False,
                message=f"Service client not initialized: {service_name}",
                data={},
                request_id="",
            )

        timeout = timeout_sec or self.timeout_sec

        try:
            if not client.wait_for_service(timeout_sec=5.0):
                return LeRobotResponse(
                    success=False,
                    message=f"Service not available: {service_name}",
                    data={},
                    request_id="",
                )

            logger.debug(f"Calling GR00T service {service_name}")
            future = client.call_async(request)

            import rclpy
            rclpy.spin_until_future_complete(
                self._node, future, timeout_sec=timeout
            )

            if future.done():
                response = future.result()
                if response is not None:
                    return LeRobotResponse.from_service_response(response)
                else:
                    return LeRobotResponse(
                        success=False,
                        message=f"Service call returned None: {service_name}",
                        data={},
                        request_id="",
                    )
            else:
                return LeRobotResponse(
                    success=False,
                    message=f"Service call timed out: {service_name}",
                    data={},
                    request_id="",
                )
        except Exception as e:
            logger.error(f"Service call to {service_name} failed: {e}")
            return LeRobotResponse(
                success=False,
                message=f"Service call failed: {str(e)}",
                data={},
                request_id="",
            )

    def start_inference(
        self,
        model_path: str,
        embodiment_tag: str,
        camera_topic_map: list,
        joint_topic_map: list,
        task_instruction: str = "",
    ) -> LeRobotResponse:
        """Call /groot/infer to setup model + subscribers."""
        request = StartInference.Request()
        request.model_path = model_path
        request.embodiment_tag = embodiment_tag
        request.camera_topic_map = camera_topic_map
        request.joint_topic_map = joint_topic_map
        request.task_instruction = task_instruction

        return self._call_service(
            self._infer_client, request, self.SERVICE_INFER
        )

    def get_action_chunk(self, task_instruction: str = "") -> LeRobotResponse:
        """Call /groot/get_action_chunk for on-demand inference."""
        request = GetActionChunk.Request()
        request.task_instruction = task_instruction

        return self._call_service(
            self._action_chunk_client,
            request,
            self.SERVICE_GET_ACTION_CHUNK,
            timeout_sec=5.0,  # Inference is 100-500ms, 5s is generous
        )

    def stop_inference(self) -> LeRobotResponse:
        """Call /groot/stop to stop inference."""
        request = StopTraining.Request()
        return self._call_service(
            self._stop_client, request, self.SERVICE_STOP
        )
