#!/usr/bin/env python3
"""
LeRobot Executor - Zenoh-based executor for LeRobot training and inference.

This module provides a clean interface between Physical AI Server (ROS2) and
LeRobot training/inference pipelines using zenoh_ros2_sdk.

Architecture:
    Physical AI Manager (React UI)
        |
        v (WebSocket 9090)
    Physical AI Server (ROS2 + rmw_zenoh_cpp)
        |
        v (Zenoh Protocol 7447)
    LeRobot Executor (this module)

Module structure (composition pattern):
    executor.py  - Shared infrastructure (this file)
    training.py  - TrainingHandler (training logic)
    inference.py - InferenceHandler (inference logic)

Services:
    - /lerobot/train: Start training with parameters
    - /lerobot/infer: Start inference with parameters
    - /lerobot/stop: Stop current training/inference
    - /lerobot/status: Get current status
    - /lerobot/policy_list: List available policies
    - /lerobot/checkpoint_list: List available checkpoints
    - /lerobot/model_list: List loaded models

Topics (Published):
    - /lerobot/progress: Training progress updates
    - /lerobot/action: Inference action outputs
"""

from __future__ import annotations

import json
import logging
import math
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import torch

# Add zenoh_ros2_sdk to path
ZENOH_SDK_PATH = os.environ.get("ZENOH_SDK_PATH", "/zenoh_sdk")
if os.path.exists(ZENOH_SDK_PATH):
    sys.path.insert(0, ZENOH_SDK_PATH)

from zenoh_ros2_sdk import (  # noqa: E402
    ROS2Publisher,
    ROS2ServiceServer,
    get_logger,
)

logger = get_logger("lerobot_executor")
logger.setLevel(logging.DEBUG)

# Enable DEBUG for all zenoh_ros2_sdk loggers to see keyexpr and connection details
logging.getLogger("zenoh_ros2_sdk").setLevel(logging.DEBUG)

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    force=True,
)


class ExecutorState(Enum):
    """Executor state enumeration."""

    IDLE = "idle"
    TRAINING = "training"
    INFERENCE = "inference"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass
class TrainingProgress:
    """Training progress data."""

    step: int = 0
    total_steps: int = 0
    epoch: float = 0.0
    loss: float = 0.0
    learning_rate: float = 0.0
    gradient_norm: float = 0.0
    samples_per_second: float = 0.0
    elapsed_seconds: float = 0.0
    eta_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step": self.step,
            "total_steps": self.total_steps,
            "epoch": self.epoch,
            "loss": self.loss,
            "learning_rate": self.learning_rate,
            "gradient_norm": self.gradient_norm,
            "samples_per_second": self.samples_per_second,
            "elapsed_seconds": self.elapsed_seconds,
            "eta_seconds": self.eta_seconds,
        }


@dataclass
class InferenceConfig:
    """Inference configuration."""

    model_path: str = ""
    inference_freq: float = 30.0  # Hz
    camera_topics: list = field(default_factory=list)
    joint_topic: str = ""


@dataclass
class ExecutorConfig:
    """Executor configuration."""

    router_ip: str = "127.0.0.1"
    router_port: int = 7447
    domain_id: int = 30
    node_name: str = "lerobot_executor"
    namespace: str = "/"

    # Topic/Service names
    train_service: str = "/lerobot/train"
    infer_service: str = "/lerobot/infer"
    stop_service: str = "/lerobot/stop"
    status_service: str = "/lerobot/status"
    policy_list_service: str = "/lerobot/policy_list"
    checkpoint_list_service: str = "/lerobot/checkpoint_list"
    model_list_service: str = "/lerobot/model_list"
    progress_topic: str = "/lerobot/progress"
    action_topic: str = "/lerobot/action"

    # Progress publish interval
    progress_interval_sec: float = 1.0


# Available LeRobot policies with full metadata
AVAILABLE_POLICIES = [
    {
        "name": "act",
        "display_name": "ACT (Action Chunking Transformer)",
        "description": "Transformer-based policy with action chunking",
        "category": "imitation_learning",
        "supports_vision": True,
        "supports_proprio": True,
    },
    {
        "name": "diffusion",
        "display_name": "Diffusion Policy",
        "description": "Diffusion-based policy for continuous action prediction",
        "category": "imitation_learning",
        "supports_vision": True,
        "supports_proprio": True,
    },
    {
        "name": "vqbet",
        "display_name": "VQ-BeT (Vector Quantized Behavior Transformer)",
        "description": "Discrete action policy using vector quantization",
        "category": "imitation_learning",
        "supports_vision": True,
        "supports_proprio": True,
    },
    {
        "name": "tdmpc",
        "display_name": "TD-MPC",
        "description": "Model-based RL with temporal difference learning",
        "category": "reinforcement_learning",
        "supports_vision": True,
        "supports_proprio": True,
    },
    {
        "name": "pi0",
        "display_name": "Pi0 (Physical Intelligence)",
        "description": "Vision-Language-Action model from Physical Intelligence",
        "category": "vla",
        "supports_vision": True,
        "supports_proprio": True,
        "supports_language": True,
    },
    {
        "name": "pi0_fast",
        "display_name": "Pi0 Fast",
        "description": "Optimized faster version of Pi0",
        "category": "vla",
        "supports_vision": True,
        "supports_proprio": True,
        "supports_language": True,
    },
    {
        "name": "pi05",
        "display_name": "Pi0.5",
        "description": "Updated version of Pi0 with improvements",
        "category": "vla",
        "supports_vision": True,
        "supports_proprio": True,
        "supports_language": True,
    },
    {
        "name": "smolvla",
        "display_name": "SmolVLA",
        "description": "Small Vision-Language-Action model for efficient deployment",
        "category": "vla",
        "supports_vision": True,
        "supports_proprio": True,
        "supports_language": True,
    },
    {
        "name": "groot",
        "display_name": "GR00T N1.5",
        "description": "NVIDIA GR00T foundation model for robotics",
        "category": "vla",
        "supports_vision": True,
        "supports_proprio": True,
        "supports_language": True,
    },
    {
        "name": "sac",
        "display_name": "SAC (Soft Actor-Critic)",
        "description": "Off-policy RL algorithm for continuous control",
        "category": "reinforcement_learning",
        "supports_vision": False,
        "supports_proprio": True,
    },
]


class LeRobotExecutor:
    """
    LeRobot Executor - Manages training and inference via Zenoh.

    This class provides shared infrastructure:
    - ROS2 service servers for train/infer/stop/status commands
    - ROS2 publisher for progress updates and action outputs
    - Thread-safe state management
    - Graceful shutdown handling

    Training and inference logic are delegated to:
    - training.TrainingHandler
    - inference.InferenceHandler
    """

    def __init__(self, config: Optional[ExecutorConfig] = None):
        """Initialize the executor."""
        self.config = config or ExecutorConfig()
        self._state = ExecutorState.IDLE
        self._state_lock = threading.Lock()
        self._progress = TrainingProgress()
        self._training_thread: Optional[threading.Thread] = None
        self._stop_requested = threading.Event()
        self._start_time: Optional[float] = None
        self._current_job_id: Optional[str] = None
        self._running = False

        # Services and publishers (initialized in start())
        self._train_service: Optional[ROS2ServiceServer] = None
        self._infer_service: Optional[ROS2ServiceServer] = None
        self._stop_service: Optional[ROS2ServiceServer] = None
        self._status_service: Optional[ROS2ServiceServer] = None
        self._policy_list_service: Optional[ROS2ServiceServer] = None
        self._checkpoint_list_service: Optional[ROS2ServiceServer] = None
        self._model_list_service: Optional[ROS2ServiceServer] = None
        self._progress_publisher: Optional[ROS2Publisher] = None
        self._action_publisher: Optional[ROS2Publisher] = None
        self._progress_thread: Optional[threading.Thread] = None

        # Track last published progress to avoid duplicate publishes
        self._last_published_step: int = -1
        self._last_published_loss: float = float("nan")

        # Initialize handlers (composition pattern)
        from training import TrainingHandler
        from inference import InferenceHandler

        self._training_handler = TrainingHandler(self)
        self._inference_handler = InferenceHandler(self)

    @property
    def state(self) -> ExecutorState:
        """Get current state (thread-safe)."""
        with self._state_lock:
            return self._state

    @state.setter
    def state(self, value: ExecutorState) -> None:
        """Set current state (thread-safe)."""
        with self._state_lock:
            self._state = value

    def start(self) -> None:
        """Start the executor and its services."""
        logger.info("Starting LeRobot Executor...")
        logger.info(f"  Router: {self.config.router_ip}:{self.config.router_port}")
        logger.info(f"  Domain ID: {self.config.domain_id}")

        self._running = True

        # Initialize services using queue mode for better control
        self._init_services()

        # Start progress publisher thread
        self._progress_thread = threading.Thread(
            target=self._progress_publish_loop, daemon=True
        )
        self._progress_thread.start()

        # Start service handler threads
        self._service_threads = []
        services = [
            ("train", self._train_service, self._training_handler.handle_train),
            ("infer", self._infer_service, self._inference_handler.handle_infer),
            ("stop", self._stop_service, self._handle_stop),
            ("status", self._status_service, self._handle_status),
            ("policy_list", self._policy_list_service, self._handle_policy_list),
            (
                "checkpoint_list",
                self._checkpoint_list_service,
                self._handle_checkpoint_list,
            ),
            ("model_list", self._model_list_service, self._handle_model_list),
        ]

        for name, service, handler in services:
            if service:
                thread = threading.Thread(
                    target=self._service_loop,
                    args=(name, service, handler),
                    daemon=True,
                )
                thread.start()
                self._service_threads.append(thread)

        logger.info("LeRobot Executor started successfully")

    def _init_services(self) -> None:
        """Initialize ROS2 services and publishers."""
        common_kwargs = {
            "node_name": self.config.node_name,
            "namespace": self.config.namespace,
            "domain_id": self.config.domain_id,
            "router_ip": self.config.router_ip,
            "router_port": self.config.router_port,
        }

        # Train service
        self._train_service = ROS2ServiceServer(
            service_name=self.config.train_service,
            srv_type="physical_ai_interfaces/srv/TrainModel",
            mode="queue",
            **common_kwargs,
        )
        logger.info(f"Train service ready: {self.config.train_service}")

        # Infer service
        self._infer_service = ROS2ServiceServer(
            service_name=self.config.infer_service,
            srv_type="physical_ai_interfaces/srv/StartInference",
            mode="queue",
            **common_kwargs,
        )
        logger.info(f"Infer service ready: {self.config.infer_service}")

        # Stop service
        self._stop_service = ROS2ServiceServer(
            service_name=self.config.stop_service,
            srv_type="physical_ai_interfaces/srv/StopTraining",
            mode="queue",
            **common_kwargs,
        )
        logger.info(f"Stop service ready: {self.config.stop_service}")

        # Status service
        self._status_service = ROS2ServiceServer(
            service_name=self.config.status_service,
            srv_type="physical_ai_interfaces/srv/TrainingStatus",
            mode="queue",
            **common_kwargs,
        )
        logger.info(f"Status service ready: {self.config.status_service}")

        # Policy list service
        self._policy_list_service = ROS2ServiceServer(
            service_name=self.config.policy_list_service,
            srv_type="physical_ai_interfaces/srv/PolicyList",
            mode="queue",
            **common_kwargs,
        )
        logger.info(f"Policy list service ready: {self.config.policy_list_service}")

        # Checkpoint list service
        self._checkpoint_list_service = ROS2ServiceServer(
            service_name=self.config.checkpoint_list_service,
            srv_type="physical_ai_interfaces/srv/CheckpointList",
            mode="queue",
            **common_kwargs,
        )
        logger.info(
            f"Checkpoint list service ready: {self.config.checkpoint_list_service}"
        )

        # Model list service
        self._model_list_service = ROS2ServiceServer(
            service_name=self.config.model_list_service,
            srv_type="physical_ai_interfaces/srv/ModelList",
            mode="queue",
            **common_kwargs,
        )
        logger.info(f"Model list service ready: {self.config.model_list_service}")

        # Progress publisher
        self._progress_publisher = ROS2Publisher(
            topic=self.config.progress_topic,
            msg_type="physical_ai_interfaces/msg/TrainingProgress",
            **common_kwargs,
        )
        logger.info(f"Progress publisher ready: {self.config.progress_topic}")

        # Action publisher for inference outputs
        self._action_publisher = ROS2Publisher(
            topic=self.config.action_topic,
            msg_type="physical_ai_interfaces/msg/ActionOutput",
            **common_kwargs,
        )
        logger.info(f"Action publisher ready: {self.config.action_topic}")

    def _service_loop(
        self,
        name: str,
        service: ROS2ServiceServer,
        handler: Callable,
    ) -> None:
        """Service handler loop."""
        logger.info(f"Service loop started for: {name}")
        while self._running:
            try:
                key, request = service.take_request(timeout=1.0)
                try:
                    response = handler(request)
                    service.send_response(key, response)
                except Exception as e:
                    logger.error(f"Error handling {name} request: {e}", exc_info=True)
                    try:
                        error_response = self._create_error_response(service, str(e))
                        service.send_response(key, error_response)
                    except Exception:
                        pass
            except TimeoutError:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f"Error in {name} service loop: {e}")
                    time.sleep(0.1)

    def _create_response(self, service: ROS2ServiceServer, **kwargs) -> Any:
        """Create a response for a service with given field values."""
        response_class = service.response_msg_class
        fields = response_class.__dataclass_fields__.keys()
        defaults = {
            "success": False,
            "message": "",
            "job_id": "",
            "state": "unknown",
            "step": 0,
            "total_steps": 0,
            "loss": 0.0,
            "learning_rate": 0.0,
            "gradient_norm": 0.0,
            "elapsed_seconds": 0.0,
            "eta_seconds": 0.0,
            "policies_json": "[]",
            "checkpoints_json": "[]",
            "models_json": "[]",
        }
        init_kwargs = {}
        for field_name in fields:
            if field_name in kwargs:
                init_kwargs[field_name] = kwargs[field_name]
            elif field_name in defaults:
                init_kwargs[field_name] = defaults[field_name]
        return response_class(**init_kwargs)

    def _create_error_response(
        self, service: ROS2ServiceServer, error_msg: str
    ) -> Any:
        """Create an error response for a service."""
        return self._create_response(service, success=False, message=error_msg)

    # ========================================================================
    # Stop Handler
    # ========================================================================

    def _handle_stop(self, request: Any) -> Any:
        """Handle stop request."""
        logger.info("Received stop request")

        if self.state == ExecutorState.IDLE:
            return self._create_response(
                self._stop_service,
                success=False,
                message="No task is running",
            )

        self._stop_requested.set()
        self.state = ExecutorState.STOPPING

        # Cleanup inference handler
        self._inference_handler.cleanup()

        # Wait for training thread
        if self._training_thread and self._training_thread.is_alive():
            self._training_thread.join(timeout=10.0)

        self.state = ExecutorState.IDLE

        return self._create_response(
            self._stop_service,
            success=True,
            message="Stop requested",
        )

    # ========================================================================
    # Status Handler
    # ========================================================================

    def _handle_status(self, request: Any) -> Any:
        """Handle status request."""
        return self._create_response(
            self._status_service,
            state=self.state.value,
            step=self._progress.step,
            total_steps=self._progress.total_steps,
            loss=self._progress.loss,
            learning_rate=self._progress.learning_rate,
            gradient_norm=self._progress.gradient_norm,
            elapsed_seconds=self._progress.elapsed_seconds,
            eta_seconds=self._progress.eta_seconds,
            job_id=self._current_job_id or "",
            message="",
        )

    # ========================================================================
    # Policy List Handler
    # ========================================================================

    def _handle_policy_list(self, request: Any) -> Any:
        """Handle policy list request."""
        category = getattr(request, "category", "")
        policies = AVAILABLE_POLICIES

        if category:
            policies = [p for p in policies if p.get("category") == category]

        return self._create_response(
            self._policy_list_service,
            success=True,
            message="",
            policies_json=json.dumps(policies),
        )

    # ========================================================================
    # Checkpoint List Handler
    # ========================================================================

    def _handle_checkpoint_list(self, request: Any) -> Any:
        """Handle checkpoint list request."""
        workspace_dir = os.environ.get("LEROBOT_WORKSPACE", "/workspace")
        checkpoints_dir = Path(workspace_dir) / "checkpoints"

        legacy_dir = Path(
            os.environ.get("HF_LEROBOT_HOME", "/root/.cache/huggingface/lerobot")
        ) / "outputs" / "train"

        checkpoints = []

        for outputs_dir in [checkpoints_dir, legacy_dir]:
            if not outputs_dir.exists():
                continue

            for run_dir in outputs_dir.iterdir():
                if not run_dir.is_dir():
                    continue

                ckpt_subdir = run_dir / "checkpoints"
                if ckpt_subdir.exists():
                    for ckpt_dir in ckpt_subdir.iterdir():
                        if not ckpt_dir.is_dir():
                            continue

                        model_path = ckpt_dir / "pretrained_model"
                        if model_path.exists():
                            checkpoints.append(
                                {
                                    "name": f"{run_dir.name}/{ckpt_dir.name}",
                                    "path": str(model_path),
                                    "run_name": run_dir.name,
                                    "step": ckpt_dir.name,
                                    "location": (
                                        "workspace"
                                        if outputs_dir == checkpoints_dir
                                        else "legacy"
                                    ),
                                }
                            )

        return self._create_response(
            self._checkpoint_list_service,
            success=True,
            message="",
            checkpoints_json=json.dumps(checkpoints),
        )

    # ========================================================================
    # Model List Handler
    # ========================================================================

    def _handle_model_list(self, request: Any) -> Any:
        """Handle model list request."""
        cache_dir = Path(
            os.environ.get("HF_LEROBOT_HOME", "/root/.cache/huggingface/lerobot")
        )

        models = []
        if cache_dir.exists():
            for item in cache_dir.iterdir():
                if item.is_dir() and (item / "config.json").exists():
                    models.append({"name": item.name, "path": str(item)})

        return self._create_response(
            self._model_list_service,
            success=True,
            message="",
            models_json=json.dumps(models),
        )

    # ========================================================================
    # Progress Publishing
    # ========================================================================

    def _progress_publish_loop(self) -> None:
        """Publish progress only when there are changes."""
        while self._running:
            try:
                if (
                    self.state == ExecutorState.TRAINING
                    and self._progress_publisher
                ):
                    # Only publish if step or loss changed
                    current_step = self._progress.step
                    current_loss = self._progress.loss

                    step_changed = current_step != self._last_published_step

                    # Handle NaN comparison properly using math.isnan
                    current_is_nan = (
                        math.isnan(current_loss)
                        if isinstance(current_loss, float)
                        else False
                    )
                    last_is_nan = (
                        math.isnan(self._last_published_loss)
                        if isinstance(self._last_published_loss, float)
                        else False
                    )

                    if current_is_nan and last_is_nan:
                        loss_changed = False
                    elif current_is_nan or last_is_nan:
                        loss_changed = True
                    else:
                        loss_changed = current_loss != self._last_published_loss

                    if step_changed or loss_changed:
                        self._publish_progress()
                        self._last_published_step = current_step
                        self._last_published_loss = current_loss

                time.sleep(self.config.progress_interval_sec)
            except Exception as e:
                logger.error(f"Error publishing progress: {e}")

    def _publish_progress(self) -> None:
        """Publish current progress."""
        try:
            self._progress_publisher.publish(
                step=self._progress.step,
                total_steps=self._progress.total_steps,
                epoch=self._progress.epoch,
                loss=self._progress.loss,
                learning_rate=self._progress.learning_rate,
                gradient_norm=self._progress.gradient_norm,
                samples_per_second=self._progress.samples_per_second,
                elapsed_seconds=self._progress.elapsed_seconds,
                eta_seconds=self._progress.eta_seconds,
                state=self.state.value,
            )
            step = self._progress.step
            loss = self._progress.loss
            logger.info(f"Published progress: step={step}, loss={loss:.4f}")
        except Exception as e:
            logger.error(f"Failed to publish progress: {e}")

    # ========================================================================
    # Lifecycle
    # ========================================================================

    def stop(self) -> None:
        """Stop the executor."""
        logger.info("Stopping LeRobot Executor...")
        self._running = False

        self._stop_requested.set()

        # Cleanup handlers
        self._training_handler.cleanup()
        self._inference_handler.cleanup()

        if self._training_thread and self._training_thread.is_alive():
            self._training_thread.join(timeout=5.0)

        # Close services
        for service in [
            self._train_service,
            self._infer_service,
            self._stop_service,
            self._status_service,
            self._policy_list_service,
            self._checkpoint_list_service,
            self._model_list_service,
        ]:
            if service:
                try:
                    service.close()
                except Exception:
                    pass

        # Close publishers
        for publisher in [self._progress_publisher, self._action_publisher]:
            if publisher:
                try:
                    publisher.close()
                except Exception:
                    pass

        logger.info("LeRobot Executor stopped")

    def run_forever(self) -> None:
        """Run the executor until interrupted."""
        self.start()

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info("Executor running. Press Ctrl+C to stop.")

        while self._running:
            time.sleep(1.0)


def main():
    """Main entry point."""
    config = ExecutorConfig(
        router_ip=os.environ.get("ZENOH_ROUTER_IP", "127.0.0.1"),
        router_port=int(os.environ.get("ZENOH_ROUTER_PORT", "7447")),
        domain_id=int(os.environ.get("ROS_DOMAIN_ID", "30")),
    )

    executor = LeRobotExecutor(config)
    executor.run_forever()


if __name__ == "__main__":
    main()
