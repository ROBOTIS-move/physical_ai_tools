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
ZenohLeRobotClient - ROS2 Service Client for LeRobot Docker communication.

Uses ROS2 standard Service Client with rmw_zenoh middleware.
rmw_zenoh automatically handles Zenoh protocol conversion, enabling
communication with LeRobot Docker container's zenoh_ros2_sdk server.

Architecture Design:
- physical_ai_server uses ROS2 + rmw_zenoh (standard ROS2 API)
- lerobot container uses zenoh_ros2_sdk (no ROS2 installed)
- rmw_zenoh converts ROS2 messages to Zenoh protocol = COMPATIBLE
"""

from dataclasses import dataclass
import logging
from typing import Any, Callable, Dict, Optional

from physical_ai_interfaces.msg import TrainingProgress
from physical_ai_interfaces.srv import (
    CheckpointList,
    ModelList,
    PolicyList,
    StartInference,
    StopTraining,
    TrainingStatus,
    TrainModel,
)
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

logger = logging.getLogger(__name__)


@dataclass
class LeRobotResponse:
    success: bool
    message: str
    data: Dict[str, Any]
    request_id: str

    @classmethod
    def from_service_response(
        cls, response: Any, request_id: str = ''
    ) -> 'LeRobotResponse':
        if response is None:
            return cls(
                success=False,
                message='No response from service (timeout or error)',
                data={},
                request_id=request_id
            )
        return cls(
            success=getattr(response, 'success', False),
            message=getattr(response, 'message', ''),
            data=cls._extract_data(response),
            request_id=request_id
        )

    @staticmethod
    def _extract_data(response: Any) -> Dict[str, Any]:
        data = {}
        if hasattr(response, 'job_id'):
            data['job_id'] = response.job_id
        if hasattr(response, 'state'):
            data['state'] = response.state
        if hasattr(response, 'step'):
            data['step'] = response.step
        if hasattr(response, 'total_steps'):
            data['total_steps'] = response.total_steps
        if hasattr(response, 'loss'):
            data['loss'] = response.loss
        if hasattr(response, 'learning_rate'):
            data['learning_rate'] = response.learning_rate
        if hasattr(response, 'policies'):
            data['policies'] = list(response.policies)
        if hasattr(response, 'checkpoints'):
            data['checkpoints'] = list(response.checkpoints)
        if hasattr(response, 'models'):
            data['models'] = list(response.models)
        if hasattr(response, 'action_chunk'):
            data['action_chunk'] = list(response.action_chunk)
        if hasattr(response, 'chunk_size'):
            data['chunk_size'] = response.chunk_size
        if hasattr(response, 'action_dim'):
            data['action_dim'] = response.action_dim
        if hasattr(response, 'action_keys'):
            data['action_keys'] = list(response.action_keys)
        return data


class ZenohLeRobotClient:
    """
    Client for communicating with LeRobot Docker container via ROS2 + rmw_zenoh.

    Uses ROS2 standard service clients. The rmw_zenoh middleware automatically
    converts ROS2 messages to Zenoh protocol, enabling communication with
    the zenoh_ros2_sdk service servers in the lerobot container.
    """

    SERVICE_TRAIN = '/lerobot/train'
    SERVICE_INFER = '/lerobot/infer'
    SERVICE_STOP = '/lerobot/stop'
    SERVICE_STATUS = '/lerobot/status'
    SERVICE_POLICY_LIST = '/lerobot/policy_list'
    SERVICE_CHECKPOINT_LIST = '/lerobot/checkpoint_list'
    SERVICE_MODEL_LIST = '/lerobot/model_list'

    TOPIC_PROGRESS = '/lerobot/progress'
    TOPIC_ACTION = '/lerobot/action'

    def __init__(
        self,
        node: Node = None,
        timeout_sec: float = 30.0,
        **kwargs  # Accept but ignore zenoh-specific params for compatibility
    ):
        """
        Initialize the LeRobot client.

        Parameters
        ----------
        node : Node
            ROS2 node for creating service clients.
        timeout_sec : float
            Timeout for service calls in seconds.
        """
        self._node = node
        self.timeout_sec = timeout_sec

        self._connected = False

        self._status_callback: Optional[Callable] = None
        self._action_callback: Optional[Callable] = None
        self._training_log_callback: Optional[Callable] = None

        # Callback group for service clients
        self._callback_group: Optional[MutuallyExclusiveCallbackGroup] = None

        # Service clients (ROS2 standard)
        self._train_client = None
        self._infer_client = None
        self._stop_client = None
        self._status_client = None
        self._policy_list_client = None
        self._checkpoint_list_client = None
        self._model_list_client = None

        # Subscribers
        self._progress_sub = None

    def connect(self, node: Node = None) -> bool:
        """
        Connect to LeRobot services via ROS2 service clients.

        Parameters
        ----------
        node : Node
            ROS2 node for creating service clients.
        """
        if node is not None:
            self._node = node

        if self._node is None:
            logger.error('No ROS2 node provided')
            return False

        if self._connected:
            return True

        try:
            self._callback_group = MutuallyExclusiveCallbackGroup()
            self._init_service_clients()
            self._connected = True
            logger.info(
                'Connected to LeRobot services via ROS2 rmw_zenoh'
            )
            return True
        except Exception as e:
            logger.error(f'Connection failed: {e}')
            return False

    def _init_service_clients(self):
        """Initialize ROS2 service clients."""
        self._train_client = self._node.create_client(
            TrainModel,
            self.SERVICE_TRAIN,
            callback_group=self._callback_group
        )
        self._infer_client = self._node.create_client(
            StartInference,
            self.SERVICE_INFER,
            callback_group=self._callback_group
        )
        self._stop_client = self._node.create_client(
            StopTraining,
            self.SERVICE_STOP,
            callback_group=self._callback_group
        )
        self._status_client = self._node.create_client(
            TrainingStatus,
            self.SERVICE_STATUS,
            callback_group=self._callback_group
        )
        self._policy_list_client = self._node.create_client(
            PolicyList,
            self.SERVICE_POLICY_LIST,
            callback_group=self._callback_group
        )
        self._checkpoint_list_client = self._node.create_client(
            CheckpointList,
            self.SERVICE_CHECKPOINT_LIST,
            callback_group=self._callback_group
        )
        self._model_list_client = self._node.create_client(
            ModelList,
            self.SERVICE_MODEL_LIST,
            callback_group=self._callback_group
        )

    def disconnect(self):
        """Disconnect from LeRobot services."""
        if self._progress_sub is not None:
            self._node.destroy_subscription(self._progress_sub)
            self._progress_sub = None

        # Destroy service clients
        clients = [
            ('_train_client', self._train_client),
            ('_infer_client', self._infer_client),
            ('_stop_client', self._stop_client),
            ('_status_client', self._status_client),
            ('_policy_list_client', self._policy_list_client),
            ('_checkpoint_list_client', self._checkpoint_list_client),
            ('_model_list_client', self._model_list_client),
        ]
        for name, client in clients:
            if client is not None:
                try:
                    self._node.destroy_client(client)
                except Exception as e:
                    logger.debug(f'Error destroying client {name}: {e}')

        self._train_client = None
        self._infer_client = None
        self._stop_client = None
        self._status_client = None
        self._policy_list_client = None
        self._checkpoint_list_client = None
        self._model_list_client = None

        self._connected = False

    def _call_service(
        self, client, request, service_name: str
    ) -> LeRobotResponse:
        """Call a ROS2 service and return LeRobotResponse."""
        if not self._connected:
            return LeRobotResponse(
                success=False,
                message='Not connected to LeRobot services',
                data={},
                request_id=''
            )

        if client is None:
            return LeRobotResponse(
                success=False,
                message=f'Service client not initialized: {service_name}',
                data={},
                request_id=''
            )

        try:
            # Check if service is available
            if not client.wait_for_service(timeout_sec=5.0):
                return LeRobotResponse(
                    success=False,
                    message=f'Service not available: {service_name}',
                    data={},
                    request_id=''
                )

            logger.debug(f'Calling service {service_name}')
            future = client.call_async(request)

            # Wait for response with timeout
            import rclpy
            rclpy.spin_until_future_complete(
                self._node, future, timeout_sec=self.timeout_sec
            )

            if future.done():
                response = future.result()
                if response is not None:
                    return LeRobotResponse.from_service_response(response)
                else:
                    return LeRobotResponse(
                        success=False,
                        message=f'Service call returned None: {service_name}',
                        data={},
                        request_id=''
                    )
            else:
                return LeRobotResponse(
                    success=False,
                    message=f'Service call timed out: {service_name}',
                    data={},
                    request_id=''
                )
        except Exception as e:
            logger.error(f'Service call to {service_name} failed: {e}')
            return LeRobotResponse(
                success=False,
                message=f'Service call failed: {str(e)}',
                data={},
                request_id=''
            )

    def start_training(
        self,
        policy_type: str,
        dataset_path: str,
        output_dir: str = None,
        num_epochs: int = None,
        batch_size: int = None,
        learning_rate: float = None,
        eval_freq: int = None,
        log_freq: int = None,
        save_freq: int = None,
        wandb_project: str = None
    ) -> LeRobotResponse:
        """Start training on LeRobot container."""
        request = TrainModel.Request()
        request.policy_type = policy_type
        request.dataset_path = dataset_path
        request.output_dir = output_dir or ''
        request.steps = num_epochs or 0
        request.batch_size = batch_size or 0
        request.learning_rate = learning_rate or 0.0
        request.eval_freq = eval_freq or 0
        request.log_freq = log_freq or 0
        request.save_freq = save_freq or 0
        request.wandb_project = wandb_project or ''
        request.push_to_hub = False

        return self._call_service(
            self._train_client, request, self.SERVICE_TRAIN
        )

    def stop_training(self) -> LeRobotResponse:
        """Stop training on LeRobot container."""
        request = StopTraining.Request()
        return self._call_service(
            self._stop_client, request, self.SERVICE_STOP
        )

    def resume_training(self, checkpoint_path: str) -> LeRobotResponse:
        """Resume training from checkpoint."""
        request = TrainModel.Request()
        request.policy_type = ''
        request.dataset_path = ''
        request.output_dir = checkpoint_path
        request.steps = 0
        request.batch_size = 0
        request.learning_rate = 0.0
        request.eval_freq = 0
        request.log_freq = 0
        request.save_freq = 0
        request.wandb_project = ''
        request.push_to_hub = False

        return self._call_service(
            self._train_client, request, self.SERVICE_TRAIN
        )

    def get_training_status(self) -> LeRobotResponse:
        """Get training status from LeRobot container."""
        request = TrainingStatus.Request()
        return self._call_service(
            self._status_client, request, self.SERVICE_STATUS
        )

    def start_inference(
        self,
        model_path: str,
        env_name: str = None,
        num_episodes: int = None
    ) -> LeRobotResponse:
        """Start inference on LeRobot container."""
        request = StartInference.Request()
        request.model_path = model_path

        return self._call_service(
            self._infer_client, request, self.SERVICE_INFER
        )

    def stop_inference(self) -> LeRobotResponse:
        """Stop inference on LeRobot container."""
        return self.stop_training()

    def get_inference_status(self) -> LeRobotResponse:
        """Get inference status from LeRobot container."""
        return self.get_training_status()

    def load_model(self, model_path: str) -> LeRobotResponse:
        """Load model for inference."""
        return self.start_inference(model_path)

    def unload_model(self) -> LeRobotResponse:
        """Unload model."""
        return self.stop_inference()

    def list_models(self) -> LeRobotResponse:
        """List available models."""
        request = ModelList.Request()
        return self._call_service(
            self._model_list_client, request, self.SERVICE_MODEL_LIST
        )

    def subscribe_status(self, callback: Callable[[Dict], None]) -> bool:
        """Subscribe to training progress updates."""
        self._status_callback = callback

        try:
            qos = QoSProfile(
                depth=10,
                reliability=ReliabilityPolicy.RELIABLE
            )

            def on_progress(msg: TrainingProgress):
                data = {
                    'status': msg.state,
                    'step': msg.step,
                    'total_steps': msg.total_steps,
                    'epoch': msg.epoch,
                    'loss': msg.loss,
                    'learning_rate': msg.learning_rate,
                    'gradient_norm': msg.gradient_norm,
                    'samples_per_second': msg.samples_per_second,
                    'elapsed_seconds': msg.elapsed_seconds,
                    'eta_seconds': msg.eta_seconds,
                }
                callback(data)

            self._progress_sub = self._node.create_subscription(
                TrainingProgress,
                self.TOPIC_PROGRESS,
                on_progress,
                qos
            )
            return True
        except Exception as e:
            logger.error(f'Failed to subscribe to progress: {e}')
            return False

    def subscribe_actions(self, callback: Callable[[Dict], None]) -> bool:
        """Subscribe to action outputs from inference."""
        self._action_callback = callback
        # TODO: Implement when ActionOutput message is defined
        return True

    def subscribe_training_log(self, callback: Callable[[Dict], None]) -> bool:
        """Subscribe to training log."""
        self._training_log_callback = callback
        return True

    def list_checkpoints(self) -> LeRobotResponse:
        """List available checkpoints."""
        request = CheckpointList.Request()
        return self._call_service(
            self._checkpoint_list_client, request, self.SERVICE_CHECKPOINT_LIST
        )

    def get_checkpoint_info(self, checkpoint_path: str) -> LeRobotResponse:
        """Get checkpoint info."""
        return LeRobotResponse(
            success=False,
            message='Not implemented',
            data={},
            request_id=''
        )

    def delete_checkpoint(self, checkpoint_path: str) -> LeRobotResponse:
        """Delete checkpoint."""
        return LeRobotResponse(
            success=False,
            message='Not implemented',
            data={},
            request_id=''
        )

    def get_policy_list(self, category: str = None) -> LeRobotResponse:
        """Get available policy types."""
        request = PolicyList.Request()
        request.category = category or ''
        return self._call_service(
            self._policy_list_client, request, self.SERVICE_POLICY_LIST
        )
