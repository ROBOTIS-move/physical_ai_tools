"""
RobotServiceServer - Service framework for training/inference executors.

Provides decorator-based handler registration, automatic state management,
and progress reporting over Zenoh.
"""
import os
import sys
import json
import time
import threading
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable

import numpy as np

# Add zenoh_ros2_sdk to path if not already available
_SDK_PATH = os.environ.get("ZENOH_SDK_PATH", "")
if _SDK_PATH and _SDK_PATH not in sys.path:
    sys.path.insert(0, _SDK_PATH)

from zenoh_ros2_sdk import ROS2ServiceServer, ROS2Publisher

logger = logging.getLogger("robot_service_server")

# Service message definitions (physical_ai_interfaces)
# These are embedded here to avoid dependency on physical_ai_interfaces package

TRAIN_MODEL_REQUEST_DEF = """\
string model_path
string dataset_path
string output_dir
string extra_params_json
"""

TRAIN_MODEL_RESPONSE_DEF = """\
bool success
string message
string job_id
"""

START_INFERENCE_REQUEST_DEF = """\
string model_path
string embodiment_tag
string task_instruction
string extra_params_json
"""

START_INFERENCE_RESPONSE_DEF = """\
bool success
string message
string[] action_keys
"""

GET_ACTION_CHUNK_REQUEST_DEF = """\
string task_instruction
"""

GET_ACTION_CHUNK_RESPONSE_DEF = """\
bool success
string message
float64[] action_chunk
int32 chunk_size
int32 action_dim
"""

STOP_TRAINING_REQUEST_DEF = """\
string reason
"""

STOP_TRAINING_RESPONSE_DEF = """\
bool success
string message
"""

TRAINING_STATUS_REQUEST_DEF = """\
string query
"""

TRAINING_STATUS_RESPONSE_DEF = """\
string status
string message
int32 current_step
int32 total_steps
float64 loss
float64 learning_rate
"""

CHECKPOINT_LIST_REQUEST_DEF = """\
string model_path
"""

CHECKPOINT_LIST_RESPONSE_DEF = """\
bool success
string message
string checkpoints_json
"""

TRAINING_PROGRESS_DEF = """\
int32 step
int32 total_steps
float64 loss
float64 learning_rate
float64 gradient_norm
float64 epoch
string status
string message
"""


@dataclass
class TrainingProgress:
    step: int = 0
    total_steps: int = 0
    loss: float = 0.0
    learning_rate: float = 0.0
    gradient_norm: float = 0.0
    epoch: float = 0.0
    status: str = ""
    message: str = ""


class _RequestProxy:
    """Proxy object for service request with dict-like attribute access."""
    def __init__(self, raw_msg, extra_params: Optional[dict] = None):
        self._raw = raw_msg
        self.extra_params = extra_params or {}

    def __getattr__(self, name):
        if name.startswith("_") or name == "extra_params":
            return super().__getattribute__(name)
        return getattr(self._raw, name, "")


class RobotServiceServer:
    """Service framework for training/inference executors.

    Usage:
        server = RobotServiceServer(name="groot")

        @server.on_train
        def handle_train(request):
            ...
            return {"success": True}

        server.start()
    """

    def __init__(
        self,
        name: str,
        router_ip: str = "127.0.0.1",
        router_port: int = 7447,
    ):
        self._name = name
        self._router_ip = router_ip
        self._router_port = router_port
        self._state = "idle"
        self._progress = TrainingProgress()
        self._handlers: dict[str, Callable] = {}
        self._services: list = []
        self._progress_publisher: Optional[ROS2Publisher] = None
        self._progress_thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------ #
    # Decorator API
    # ------------------------------------------------------------------ #

    def on_train(self, func: Callable) -> Callable:
        self._handlers["train"] = func
        return func

    def on_load_policy(self, func: Callable) -> Callable:
        self._handlers["load_policy"] = func
        return func

    def on_get_action(self, func: Callable) -> Callable:
        self._handlers["get_action"] = func
        return func

    def on_stop(self, func: Callable) -> Callable:
        self._handlers["stop"] = func
        return func

    def on_checkpoint_list(self, func: Callable) -> Callable:
        self._handlers["checkpoint_list"] = func
        return func

    # ------------------------------------------------------------------ #
    # Progress reporting
    # ------------------------------------------------------------------ #

    def report_progress(self, **kwargs):
        """Update and publish training progress."""
        for k, v in kwargs.items():
            if hasattr(self._progress, k):
                setattr(self._progress, k, v)
        # Immediate publish
        self._publish_progress()

    def _publish_progress(self):
        if self._progress_publisher is None:
            return
        try:
            self._progress_publisher.publish(**asdict(self._progress))
        except Exception as e:
            logger.debug(f"Failed to publish progress: {e}")

    def _progress_loop(self):
        """Background loop to periodically publish progress."""
        while self._running:
            if self._state == "training":
                self._publish_progress()
            time.sleep(1.0)

    # ------------------------------------------------------------------ #
    # Service handlers (internal)
    # ------------------------------------------------------------------ #

    def _handle_train(self, request_msg):
        """Handle TrainModel service request."""
        handler = self._handlers.get("train")
        if not handler:
            return self._make_train_response(False, "No train handler registered")

        proxy = self._parse_train_request(request_msg)
        self._state = "training"
        self._progress = TrainingProgress(status="training")

        try:
            result = handler(proxy)
            success = result.get("success", True) if isinstance(result, dict) else True
            message = result.get("message", "") if isinstance(result, dict) else ""
            job_id = result.get("job_id", "") if isinstance(result, dict) else ""
            self._state = "idle"
            return self._make_train_response(success, message, job_id)
        except Exception as e:
            self._state = "error"
            logger.error(f"Train handler error: {e}", exc_info=True)
            return self._make_train_response(False, str(e))

    def _handle_load_policy(self, request_msg):
        """Handle StartInference service request."""
        handler = self._handlers.get("load_policy")
        if not handler:
            return self._make_inference_response(False, "No load_policy handler registered")

        proxy = self._parse_inference_request(request_msg)
        self._state = "inference"

        try:
            result = handler(proxy)
            success = result.get("success", True) if isinstance(result, dict) else True
            message = result.get("message", "") if isinstance(result, dict) else ""
            action_keys = result.get("action_keys", []) if isinstance(result, dict) else []
            return self._make_inference_response(success, message, action_keys)
        except Exception as e:
            self._state = "error"
            logger.error(f"Load policy handler error: {e}", exc_info=True)
            return self._make_inference_response(False, str(e))

    def _handle_get_action(self, request_msg):
        """Handle GetActionChunk service request."""
        handler = self._handlers.get("get_action")
        if not handler:
            return self._make_action_response(False, "No get_action handler registered")

        proxy = _RequestProxy(request_msg)

        try:
            result = handler(proxy)
            if isinstance(result, dict):
                chunk = result.get("action_chunk")
                chunk_size = result.get("chunk_size", 0)
                if isinstance(chunk, np.ndarray):
                    action_dim = chunk.shape[-1] if len(chunk.shape) > 1 else chunk.shape[0]
                    chunk_flat = chunk.flatten().tolist()
                    chunk_size = chunk.shape[0] if len(chunk.shape) > 1 else 1
                else:
                    chunk_flat = list(chunk) if chunk else []
                    action_dim = result.get("action_dim", 0)
                return self._make_action_response(True, "", chunk_flat, chunk_size, action_dim)
            return self._make_action_response(False, "Invalid handler return")
        except Exception as e:
            logger.error(f"Get action handler error: {e}", exc_info=True)
            return self._make_action_response(False, str(e))

    def _handle_stop(self, request_msg):
        """Handle StopTraining service request."""
        handler = self._handlers.get("stop")
        prev_state = self._state
        self._state = "idle"

        if handler:
            try:
                result = handler()
                success = result.get("success", True) if isinstance(result, dict) else True
                message = result.get("message", "") if isinstance(result, dict) else ""
                return self._make_stop_response(success, message)
            except Exception as e:
                logger.error(f"Stop handler error: {e}", exc_info=True)
                return self._make_stop_response(False, str(e))
        return self._make_stop_response(True, f"Stopped (was {prev_state})")

    def _handle_training_status(self, request_msg):
        """Handle TrainingStatus service request."""
        from zenoh_ros2_sdk.session import ZenohSession
        session = ZenohSession.get_instance(self._router_ip, self._router_port)
        ResponseClass = session.register_message_type(
            TRAINING_STATUS_RESPONSE_DEF,
            "physical_ai_interfaces/srv/TrainingStatus_Response",
        )
        return ResponseClass(
            status=self._state,
            message=self._progress.message,
            current_step=self._progress.step,
            total_steps=self._progress.total_steps,
            loss=self._progress.loss,
            learning_rate=self._progress.learning_rate,
        )

    def _handle_checkpoint_list(self, request_msg):
        """Handle CheckpointList service request."""
        handler = self._handlers.get("checkpoint_list")
        from zenoh_ros2_sdk.session import ZenohSession
        session = ZenohSession.get_instance(self._router_ip, self._router_port)
        ResponseClass = session.register_message_type(
            CHECKPOINT_LIST_RESPONSE_DEF,
            "physical_ai_interfaces/srv/CheckpointList_Response",
        )
        if handler:
            try:
                result = handler()
                checkpoints = result if isinstance(result, list) else []
                return ResponseClass(
                    success=True,
                    message="",
                    checkpoints_json=json.dumps(checkpoints),
                )
            except Exception as e:
                return ResponseClass(success=False, message=str(e), checkpoints_json="[]")
        return ResponseClass(success=True, message="No handler", checkpoints_json="[]")

    # ------------------------------------------------------------------ #
    # Request parsing helpers
    # ------------------------------------------------------------------ #

    def _parse_train_request(self, msg) -> _RequestProxy:
        extra = {}
        extra_json = getattr(msg, "extra_params_json", "")
        if extra_json:
            try:
                extra = json.loads(extra_json)
            except json.JSONDecodeError:
                logger.warning(f"Invalid extra_params_json: {extra_json}")
        return _RequestProxy(msg, extra_params=extra)

    def _parse_inference_request(self, msg) -> _RequestProxy:
        extra = {}
        extra_json = getattr(msg, "extra_params_json", "")
        if extra_json:
            try:
                extra = json.loads(extra_json)
            except json.JSONDecodeError:
                logger.warning(f"Invalid extra_params_json: {extra_json}")
        return _RequestProxy(msg, extra_params=extra)

    # ------------------------------------------------------------------ #
    # Response builders
    # ------------------------------------------------------------------ #

    def _make_train_response(self, success, message="", job_id=""):
        from zenoh_ros2_sdk.session import ZenohSession
        session = ZenohSession.get_instance(self._router_ip, self._router_port)
        ResponseClass = session.register_message_type(
            TRAIN_MODEL_RESPONSE_DEF,
            "physical_ai_interfaces/srv/TrainModel_Response",
        )
        return ResponseClass(success=success, message=message, job_id=job_id)

    def _make_inference_response(self, success, message="", action_keys=None):
        from zenoh_ros2_sdk.session import ZenohSession
        session = ZenohSession.get_instance(self._router_ip, self._router_port)
        ResponseClass = session.register_message_type(
            START_INFERENCE_RESPONSE_DEF,
            "physical_ai_interfaces/srv/StartInference_Response",
        )
        return ResponseClass(
            success=success,
            message=message,
            action_keys=action_keys or [],
        )

    def _make_action_response(self, success, message="", action_chunk=None,
                               chunk_size=0, action_dim=0):
        from zenoh_ros2_sdk.session import ZenohSession
        session = ZenohSession.get_instance(self._router_ip, self._router_port)
        ResponseClass = session.register_message_type(
            GET_ACTION_CHUNK_RESPONSE_DEF,
            "physical_ai_interfaces/srv/GetActionChunk_Response",
        )
        return ResponseClass(
            success=success,
            message=message,
            action_chunk=action_chunk or [],
            chunk_size=chunk_size,
            action_dim=action_dim,
        )

    def _make_stop_response(self, success, message=""):
        from zenoh_ros2_sdk.session import ZenohSession
        session = ZenohSession.get_instance(self._router_ip, self._router_port)
        ResponseClass = session.register_message_type(
            STOP_TRAINING_RESPONSE_DEF,
            "physical_ai_interfaces/srv/StopTraining_Response",
        )
        return ResponseClass(success=success, message=message)

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def start(self):
        """Register all services and start progress publisher."""
        prefix = f"/{self._name}"

        # Register services
        service_map = {
            f"{prefix}/train": ("physical_ai_interfaces/srv/TrainModel",
                                TRAIN_MODEL_REQUEST_DEF, TRAIN_MODEL_RESPONSE_DEF,
                                self._handle_train),
            f"{prefix}/infer": ("physical_ai_interfaces/srv/StartInference",
                                START_INFERENCE_REQUEST_DEF, START_INFERENCE_RESPONSE_DEF,
                                self._handle_load_policy),
            f"{prefix}/get_action_chunk": ("physical_ai_interfaces/srv/GetActionChunk",
                                            GET_ACTION_CHUNK_REQUEST_DEF, GET_ACTION_CHUNK_RESPONSE_DEF,
                                            self._handle_get_action),
            f"{prefix}/stop": ("physical_ai_interfaces/srv/StopTraining",
                               STOP_TRAINING_REQUEST_DEF, STOP_TRAINING_RESPONSE_DEF,
                               self._handle_stop),
            f"{prefix}/training_status": ("physical_ai_interfaces/srv/TrainingStatus",
                                          TRAINING_STATUS_REQUEST_DEF, TRAINING_STATUS_RESPONSE_DEF,
                                          self._handle_training_status),
            f"{prefix}/checkpoint_list": ("physical_ai_interfaces/srv/CheckpointList",
                                          CHECKPOINT_LIST_REQUEST_DEF, CHECKPOINT_LIST_RESPONSE_DEF,
                                          self._handle_checkpoint_list),
        }

        for svc_name, (srv_type, req_def, resp_def, handler) in service_map.items():
            try:
                svc = ROS2ServiceServer(
                    service_name=svc_name,
                    srv_type=srv_type,
                    callback=handler,
                    request_definition=req_def,
                    response_definition=resp_def,
                    router_ip=self._router_ip,
                    router_port=self._router_port,
                    mode="callback",
                )
                self._services.append(svc)
                logger.info(f"Service registered: {svc_name}")
            except Exception as e:
                logger.error(f"Failed to register service {svc_name}: {e}", exc_info=True)

        # Progress publisher
        try:
            self._progress_publisher = ROS2Publisher(
                topic=f"{prefix}/training_progress",
                msg_type="physical_ai_interfaces/msg/TrainingProgress",
                msg_definition=TRAINING_PROGRESS_DEF,
                router_ip=self._router_ip,
                router_port=self._router_port,
            )
        except Exception as e:
            logger.warning(f"Failed to create progress publisher: {e}")

        # Start progress background thread
        self._running = True
        self._progress_thread = threading.Thread(target=self._progress_loop, daemon=True)
        self._progress_thread.start()

        self._state = "idle"
        logger.info(f"RobotServiceServer '{self._name}' started with {len(self._services)} services")

    def stop(self):
        """Stop all services and cleanup."""
        self._running = False
        if self._progress_thread:
            self._progress_thread.join(timeout=2.0)

        for svc in self._services:
            try:
                svc.close()
            except Exception as e:
                logger.debug(f"Error closing service: {e}")
        self._services.clear()

        if self._progress_publisher:
            try:
                self._progress_publisher.close()
            except Exception:
                pass
            self._progress_publisher = None

        logger.info(f"RobotServiceServer '{self._name}' stopped")

    @property
    def state(self) -> str:
        return self._state

    def enable_log_interceptor(self, patterns=None):
        """Fallback: Enable log interceptor for progress parsing."""
        logger.info("Log interceptor enabled (fallback mode)")
        # TODO: Implement log interceptor if needed
        pass
