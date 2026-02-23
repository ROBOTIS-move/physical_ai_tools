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
# Author: Dongyun Kim

"""
InferenceManager - Action chunk based async inference manager.

Generic manager that works with any inference container (GR00T, LeRobot, etc.)
by parameterizing the service prefix.

Manages action buffer, background chunk requests via ZenohServiceClient,
L2-based chunk alignment, and action-to-JointTrajectory conversion.

Architecture:
    10Hz timer (physical_ai_server)
        -> pop_action() from buffer
        -> convert to JointTrajectory messages
        -> communicator.publish_action()

    Background thread:
        -> /{prefix}/get_action_chunk service call
        -> align & enqueue into buffer
"""

import collections
import logging
import threading
from typing import Optional

import numpy as np
from rclpy.node import Node
from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint

from physical_ai_server.communication.zenoh_service_client import ZenohServiceClient

logger = logging.getLogger(__name__)


class InferenceManager:
    """Action chunk based async inference manager.

    Works with any inference container (GR00T, LeRobot, etc.)
    via the service_prefix parameter.
    """

    BUFFER_REFILL_THRESHOLD = 1  # Request new chunk when buffer < this
    ACTION_FREQ_HZ = 10.0       # Joint command publish frequency

    def __init__(
        self,
        node: Node,
        joint_topic_types: dict,
        joint_order: dict,
        service_prefix: str = "/groot",
    ):
        """
        Args:
            node: ROS2 node for creating service clients.
            joint_topic_types: {group_name: msg_type} from communicator.
            joint_order: {group_name: [joint_names]} from robot config.
                Keys are like "joint_order.leader_arm_left".
            service_prefix: Service prefix for the inference container
                (e.g., "/groot", "/lerobot").
        """
        self._node = node
        self._joint_topic_types = joint_topic_types
        self._joint_order = joint_order
        self._service_prefix = service_prefix
        self._action_joint_map: dict = {}

        # Action buffer (deque of 1D np arrays, each length = total action DOF)
        self._action_buffer: collections.deque = collections.deque()
        self._buffer_lock = threading.Lock()

        # Zenoh service client for inference container
        self._client: Optional[ZenohServiceClient] = None

        # Background inference thread
        self._inference_thread: Optional[threading.Thread] = None
        self._running = False
        self._requesting = False  # Prevent duplicate requests

        # Chunk alignment
        self._last_action: Optional[np.ndarray] = None

        # Task instruction for language-conditioned policies
        self._task_instruction: str = ""

    def start(
        self,
        model_path: str,
        embodiment_tag: str,
        camera_topic_map: list,
        joint_topic_map: list,
        task_instruction: str,
    ):
        """Setup inference: call /{prefix}/infer + start buffer management.

        Args:
            model_path: Path to the model checkpoint.
            embodiment_tag: Embodiment tag for the model.
            camera_topic_map: ["name:topic", ...] pairs.
            joint_topic_map: ["modality_key:topic", ...] pairs.
            task_instruction: Language instruction for the policy.
        """
        self._task_instruction = task_instruction

        self._client = ZenohServiceClient(
            node=self._node,
            service_prefix=self._service_prefix,
        )
        self._client.connect()

        # Call /{prefix}/infer service (setup only — model load + subscriber start)
        response = self._client.start_inference(
            model_path=model_path,
            embodiment_tag=embodiment_tag,
            camera_topic_map=camera_topic_map,
            joint_topic_map=joint_topic_map,
            task_instruction=task_instruction,
        )
        if not response.success:
            raise RuntimeError(
                f"Inference setup failed ({self._service_prefix}): "
                f"{response.message}"
            )

        # Build action_joint_map from action_keys returned by the executor
        action_keys = response.data.get("action_keys", [])
        self._build_action_joint_map(action_keys)

        self._running = True
        logger.info(
            f"InferenceManager started ({self._service_prefix}), "
            f"action_keys={action_keys}, requesting first chunk..."
        )

        # Request first chunk immediately
        self._request_chunk_async()

    def pop_action(self) -> Optional[dict]:
        """Pop one action from buffer and convert to joint messages.

        Called by 10Hz timer in physical_ai_server.
        Returns dict of {group_name: JointTrajectory msg} or None if buffer empty.
        """
        with self._buffer_lock:
            if not self._action_buffer:
                # Buffer empty — request new chunk if not already requesting
                if not self._requesting:
                    self._request_chunk_async()
                return None
            action = self._action_buffer.popleft()
            remaining = len(self._action_buffer)

        # Request new chunk if buffer running low
        if remaining < self.BUFFER_REFILL_THRESHOLD and not self._requesting:
            self._request_chunk_async()

        return self._action_to_joint_msgs(action)

    def _request_chunk_async(self):
        """Start background thread to fetch next action chunk."""
        if not self._running:
            return
        self._requesting = True
        self._inference_thread = threading.Thread(
            target=self._fetch_chunk, daemon=True
        )
        self._inference_thread.start()

    def _fetch_chunk(self):
        """Blocking service call to get action chunk, then enqueue.

        Retries up to MAX_RETRIES times with a delay if observations
        are not yet available (e.g., during startup).
        """
        import time
        MAX_RETRIES = 10
        RETRY_DELAY = 1.0  # seconds

        try:
            if self._client is None:
                return

            for attempt in range(MAX_RETRIES):
                if not self._running:
                    return

                response = self._client.get_action_chunk(
                    task_instruction=self._task_instruction
                )
                if response.success:
                    chunk_data = response.data.get("action_chunk", [])
                    chunk_size = response.data.get("chunk_size", 0)
                    action_dim = response.data.get("action_dim", 0)

                    if chunk_size > 0 and action_dim > 0 and len(chunk_data) > 0:
                        chunk = np.array(chunk_data).reshape(chunk_size, action_dim)
                        self._align_and_enqueue(chunk)
                        logger.info(
                            f"Chunk received: T={chunk_size}, D={action_dim}, "
                            f"buffer={len(self._action_buffer)}"
                        )
                        return  # Success
                    else:
                        logger.warning(f"Empty chunk response: {response.message}")
                        return
                else:
                    # Retry on transient failures (missing observations, etc.)
                    if attempt < MAX_RETRIES - 1:
                        logger.debug(
                            f"Chunk request failed (attempt {attempt + 1}): "
                            f"{response.message}, retrying in {RETRY_DELAY}s..."
                        )
                        time.sleep(RETRY_DELAY)
                    else:
                        logger.warning(
                            f"Chunk request failed after {MAX_RETRIES} attempts: "
                            f"{response.message}"
                        )
        except Exception as e:
            logger.error(f"Error fetching action chunk: {e}")
        finally:
            self._requesting = False

    def _align_and_enqueue(self, chunk: np.ndarray):
        """L2 distance based chunk alignment, then add to buffer.

        When transitioning between chunks, finds the closest timestep
        in the new chunk to the last executed action, and starts from
        the next timestep to avoid discontinuities.
        """
        with self._buffer_lock:
            if self._last_action is not None and len(chunk) > 1:
                distances = np.linalg.norm(chunk - self._last_action, axis=1)
                start_idx = int(np.argmin(distances)) + 1
                if start_idx < len(chunk):
                    chunk = chunk[start_idx:]

            for action in chunk:
                self._action_buffer.append(action)

            if len(chunk) > 0:
                self._last_action = chunk[-1].copy()

    def _build_action_joint_map(self, action_keys: list):
        """Build action_joint_map from model's action_keys and joint_order.

        Maps modality keys (e.g. "arm_left") to leader group keys in
        joint_order (e.g. "joint_order.leader_arm_left").
        """
        self._action_joint_map = {}
        for key in action_keys:
            leader_key = f"joint_order.leader_{key}"
            if leader_key in self._joint_order:
                self._action_joint_map[key] = leader_key
            else:
                logger.warning(
                    f"No leader group found for action key '{key}' "
                    f"(tried '{leader_key}')"
                )
        logger.info(f"Action joint map: {self._action_joint_map}")

    def _action_to_joint_msgs(self, action: np.ndarray) -> dict:
        """Convert flat action array to per-group JointTrajectory messages.

        Action is ordered by action_joint_map keys (same order as model output).
        e.g. [arm_l_j1..j7, grip_l, arm_r_j1..j7, grip_r] (16 dims)
        """
        joint_msg_datas = {}
        offset = 0

        for modality_key, leader_group in self._action_joint_map.items():
            joint_names = self._joint_order.get(leader_group, [])
            n_joints = len(joint_names)

            if n_joints == 0:
                continue

            values = action[offset:offset + n_joints]
            offset += n_joints

            msg = JointTrajectory()
            msg.joint_names = list(joint_names)
            point = JointTrajectoryPoint()
            point.positions = [float(v) for v in values]
            msg.points = [point]
            # Strip "joint_order." prefix to match communicator publisher keys
            publisher_key = leader_group.removeprefix("joint_order.")
            joint_msg_datas[publisher_key] = msg

        return joint_msg_datas

    def stop(self):
        """Stop inference and cleanup."""
        self._running = False

        if self._client:
            try:
                self._client.stop_inference()
            except Exception as e:
                logger.error(f"Error stopping inference: {e}")
            try:
                self._client.disconnect()
            except Exception as e:
                logger.debug(f"Error disconnecting client: {e}")
            self._client = None

        with self._buffer_lock:
            self._action_buffer.clear()

        self._last_action = None
        self._action_joint_map = {}
        logger.info(f"InferenceManager stopped ({self._service_prefix})")

