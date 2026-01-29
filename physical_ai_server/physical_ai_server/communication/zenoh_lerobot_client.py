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
ZenohLeRobotClient - Zenoh SDK Client for LeRobot Docker communication.

Uses zenoh_ros2_sdk to communicate with LeRobot Docker container.
This ensures protocol compatibility with lerobot's zenoh_ros2_sdk server.

Architecture Design:
- physical_ai_server uses ROS2 + rmw_zenoh for INTERNAL ROS2 communication
- physical_ai_server uses zenoh_ros2_sdk for EXTERNAL communication with lerobot
- lerobot container uses zenoh_ros2_sdk only (no ROS2 installed)
- Both sides use the same zenoh_ros2_sdk protocol = COMPATIBLE
"""

from dataclasses import dataclass
import logging
import os
from typing import Any, Callable, Dict, Optional

from rclpy.node import Node

from zenoh_ros2_sdk import (
    ROS2ServiceClient,
    ROS2Subscriber,
)

logger = logging.getLogger(__name__)


# Service type definitions for zenoh_ros2_sdk
# These match the ROS2 service definitions in physical_ai_interfaces
SERVICE_DEFINITIONS = {
    'TrainModel': {
        'type': 'physical_ai_interfaces/srv/TrainModel',
        'request': '''string policy_type
string dataset_path
string output_dir
int32 steps
int32 batch_size
float32 learning_rate
int32 eval_freq
int32 log_freq
int32 save_freq
string wandb_project
bool push_to_hub''',
        'response': '''bool success
string message
string job_id'''
    },
    'StartInference': {
        'type': 'physical_ai_interfaces/srv/StartInference',
        'request': '''string model_path''',
        'response': '''bool success
string message'''
    },
    'StopTraining': {
        'type': 'physical_ai_interfaces/srv/StopTraining',
        'request': '''''',
        'response': '''bool success
string message'''
    },
    'TrainingStatus': {
        'type': 'physical_ai_interfaces/srv/TrainingStatus',
        'request': '''''',
        'response': '''bool success
string message
string state
int32 step
int32 total_steps
float32 loss
float32 learning_rate'''
    },
    'PolicyList': {
        'type': 'physical_ai_interfaces/srv/PolicyList',
        'request': '''string category''',
        'response': '''bool success
string message
string[] policies'''
    },
    'CheckpointList': {
        'type': 'physical_ai_interfaces/srv/CheckpointList',
        'request': '''''',
        'response': '''bool success
string message
string[] checkpoints'''
    },
    'ModelList': {
        'type': 'physical_ai_interfaces/srv/ModelList',
        'request': '''''',
        'response': '''bool success
string message
string[] models'''
    },
}

# Message type definitions
MESSAGE_DEFINITIONS = {
    'TrainingProgress': {
        'type': 'physical_ai_interfaces/msg/TrainingProgress',
        'definition': '''int32 step
int32 total_steps
float64 epoch
float64 loss
float64 learning_rate
float64 gradient_norm
float64 samples_per_second
float64 elapsed_seconds
float64 eta_seconds
string state'''
    },
}


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
        return data


class ZenohLeRobotClient:
    """
    Client for communicating with LeRobot Docker container via zenoh_ros2_sdk.

    Uses zenoh_ros2_sdk service clients which are protocol-compatible with
    the zenoh_ros2_sdk service servers in the lerobot container.

    Note: The 'node' parameter is accepted for API compatibility with the
    rest of the physical_ai_server code, but is not used for actual
    communication (zenoh_ros2_sdk doesn't need ROS2 nodes).
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
        router_ip: str = None,
        router_port: int = 7447,
        domain_id: int = None,
    ):
        """
        Initialize the LeRobot client.

        Parameters
        ----------
        node : Node, optional
            ROS2 node (accepted for API compatibility, not used directly).
        timeout_sec : float
            Timeout for service calls in seconds.
        router_ip : str, optional
            Zenoh router IP. Defaults to 127.0.0.1.
        router_port : int
            Zenoh router port. Defaults to 7447.
        domain_id : int, optional
            ROS domain ID. Defaults to ROS_DOMAIN_ID or 30.
        """
        self._node = node  # For API compatibility
        self.timeout_sec = timeout_sec
        self.router_ip = router_ip or os.getenv('ZENOH_ROUTER_IP', '127.0.0.1')
        self.router_port = router_port
        self.domain_id = domain_id or int(os.getenv('ROS_DOMAIN_ID', '30'))

        self._connected = False

        self._status_callback: Optional[Callable] = None
        self._action_callback: Optional[Callable] = None
        self._training_log_callback: Optional[Callable] = None

        # Service clients (zenoh_ros2_sdk)
        self._train_client: Optional[ROS2ServiceClient] = None
        self._infer_client: Optional[ROS2ServiceClient] = None
        self._stop_client: Optional[ROS2ServiceClient] = None
        self._status_client: Optional[ROS2ServiceClient] = None
        self._policy_list_client: Optional[ROS2ServiceClient] = None
        self._checkpoint_list_client: Optional[ROS2ServiceClient] = None
        self._model_list_client: Optional[ROS2ServiceClient] = None

        # Subscribers
        self._progress_sub: Optional[ROS2Subscriber] = None

    def connect(self, node: Node = None) -> bool:
        """
        Connect to LeRobot services via zenoh_ros2_sdk.

        Parameters
        ----------
        node : Node, optional
            ROS2 node (accepted for API compatibility, not used).
        """
        if node is not None:
            self._node = node

        if self._connected:
            return True

        try:
            self._init_service_clients()
            self._connected = True
            logger.info(
                f'Connected to LeRobot services via zenoh_ros2_sdk '
                f'(router={self.router_ip}:{self.router_port}, '
                f'domain_id={self.domain_id})'
            )
            return True
        except Exception as e:
            logger.error(f'Connection failed: {e}')
            return False

    def _create_service_client(
        self, service_name: str, service_key: str
    ) -> ROS2ServiceClient:
        """Create a zenoh_ros2_sdk service client."""
        svc_def = SERVICE_DEFINITIONS[service_key]
        return ROS2ServiceClient(
            service_name=service_name,
            srv_type=svc_def['type'],
            request_definition=svc_def['request'],
            response_definition=svc_def['response'],
            domain_id=self.domain_id,
            router_ip=self.router_ip,
            router_port=self.router_port,
            timeout=self.timeout_sec,
        )

    def _init_service_clients(self):
        """Initialize zenoh_ros2_sdk service clients."""
        self._train_client = self._create_service_client(
            self.SERVICE_TRAIN, 'TrainModel'
        )
        self._infer_client = self._create_service_client(
            self.SERVICE_INFER, 'StartInference'
        )
        self._stop_client = self._create_service_client(
            self.SERVICE_STOP, 'StopTraining'
        )
        self._status_client = self._create_service_client(
            self.SERVICE_STATUS, 'TrainingStatus'
        )
        self._policy_list_client = self._create_service_client(
            self.SERVICE_POLICY_LIST, 'PolicyList'
        )
        self._checkpoint_list_client = self._create_service_client(
            self.SERVICE_CHECKPOINT_LIST, 'CheckpointList'
        )
        self._model_list_client = self._create_service_client(
            self.SERVICE_MODEL_LIST, 'ModelList'
        )

    def disconnect(self):
        """Disconnect from LeRobot services."""
        if self._progress_sub is not None:
            self._progress_sub.close()
            self._progress_sub = None

        # Close service clients
        clients = [
            self._train_client,
            self._infer_client,
            self._stop_client,
            self._status_client,
            self._policy_list_client,
            self._checkpoint_list_client,
            self._model_list_client,
        ]
        for client in clients:
            if client is not None:
                try:
                    client.close()
                except Exception as e:
                    logger.debug(f'Error closing client: {e}')

        self._train_client = None
        self._infer_client = None
        self._stop_client = None
        self._status_client = None
        self._policy_list_client = None
        self._checkpoint_list_client = None
        self._model_list_client = None

        self._connected = False

    def _call_service(
        self, client: ROS2ServiceClient, service_name: str, **kwargs
    ) -> LeRobotResponse:
        """Call a zenoh_ros2_sdk service and return LeRobotResponse."""
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
            logger.debug(f'Calling service {service_name} with args: {kwargs}')
            response = client.call(**kwargs)

            if response is not None:
                return LeRobotResponse.from_service_response(response)
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
        return self._call_service(
            self._train_client,
            self.SERVICE_TRAIN,
            policy_type=policy_type,
            dataset_path=dataset_path,
            output_dir=output_dir or '',
            steps=num_epochs or 0,
            batch_size=batch_size or 0,
            learning_rate=learning_rate or 0.0,
            eval_freq=eval_freq or 0,
            log_freq=log_freq or 0,
            save_freq=save_freq or 0,
            wandb_project=wandb_project or '',
            push_to_hub=False,
        )

    def stop_training(self) -> LeRobotResponse:
        """Stop training on LeRobot container."""
        return self._call_service(
            self._stop_client,
            self.SERVICE_STOP,
        )

    def resume_training(self, checkpoint_path: str) -> LeRobotResponse:
        """Resume training from checkpoint."""
        return self._call_service(
            self._train_client,
            self.SERVICE_TRAIN,
            policy_type='',
            dataset_path='',
            output_dir=checkpoint_path,
            steps=0,
            batch_size=0,
            learning_rate=0.0,
            eval_freq=0,
            log_freq=0,
            save_freq=0,
            wandb_project='',
            push_to_hub=False,
        )

    def get_training_status(self) -> LeRobotResponse:
        """Get training status from LeRobot container."""
        return self._call_service(
            self._status_client,
            self.SERVICE_STATUS,
        )

    def start_inference(
        self,
        model_path: str,
        env_name: str = None,
        num_episodes: int = None
    ) -> LeRobotResponse:
        """Start inference on LeRobot container."""
        return self._call_service(
            self._infer_client,
            self.SERVICE_INFER,
            model_path=model_path,
        )

    def stop_inference(self) -> LeRobotResponse:
        """Stop inference on LeRobot container."""
        return self._call_service(
            self._stop_client,
            self.SERVICE_STOP,
        )

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
        return self._call_service(
            self._model_list_client,
            self.SERVICE_MODEL_LIST,
        )

    def subscribe_status(self, callback: Callable[[Dict], None]) -> bool:
        """Subscribe to training progress updates."""
        self._status_callback = callback

        try:
            msg_def = MESSAGE_DEFINITIONS['TrainingProgress']

            def on_progress(msg):
                data = {
                    'status': getattr(msg, 'state', 'unknown'),
                    'step': getattr(msg, 'step', 0),
                    'total_steps': getattr(msg, 'total_steps', 0),
                    'epoch': getattr(msg, 'epoch', 0.0),
                    'loss': getattr(msg, 'loss', 0.0),
                    'learning_rate': getattr(msg, 'learning_rate', 0.0),
                    'gradient_norm': getattr(msg, 'gradient_norm', 0.0),
                    'samples_per_second': getattr(msg, 'samples_per_second', 0.0),
                    'elapsed_seconds': getattr(msg, 'elapsed_seconds', 0.0),
                    'eta_seconds': getattr(msg, 'eta_seconds', 0.0),
                }
                callback(data)

            self._progress_sub = ROS2Subscriber(
                topic=self.TOPIC_PROGRESS,
                msg_type=msg_def['type'],
                msg_definition=msg_def['definition'],
                callback=on_progress,
                domain_id=self.domain_id,
                router_ip=self.router_ip,
                router_port=self.router_port,
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
        return self._call_service(
            self._checkpoint_list_client,
            self.SERVICE_CHECKPOINT_LIST,
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
        return self._call_service(
            self._policy_list_client,
            self.SERVICE_POLICY_LIST,
            category=category or '',
        )
