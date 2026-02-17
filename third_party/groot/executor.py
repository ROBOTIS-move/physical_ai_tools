#!/usr/bin/env python3
"""
GR00T N1.6 Executor - Zenoh-based executor for GR00T finetuning and inference.

This module provides a clean interface between Physical AI Server (ROS2) and
GR00T training/inference pipelines using zenoh_ros2_sdk.

Architecture:
    Physical AI Manager (React UI)
        |
        v (WebSocket 9090)
    Physical AI Server (ROS2 + rmw_zenoh_cpp)
        |
        v (Zenoh Protocol 7447)
    GR00T Executor (this module)

Services:
    - /groot/train: Start finetuning with parameters
    - /groot/infer: Start inference with parameters
    - /groot/stop: Stop current finetuning/inference
    - /groot/status: Get current status
    - /groot/embodiment_list: List supported embodiments
    - /groot/checkpoint_list: List available checkpoints

Topics (Published):
    - /groot/progress: Training progress updates
    - /groot/action: Inference action outputs

Code Organization:
    - executor.py: Shared infrastructure, service setup, lifecycle
    - training.py: TrainingHandler - finetuning logic
    - inference.py: InferenceHandler - inference logic
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

import numpy as np

# Add zenoh_ros2_sdk to path
ZENOH_SDK_PATH = os.environ.get("ZENOH_SDK_PATH", "/zenoh_sdk")
if os.path.exists(ZENOH_SDK_PATH):
    sys.path.insert(0, ZENOH_SDK_PATH)

from zenoh_ros2_sdk import (  # noqa: E402
    ROS2Publisher,
    ROS2ServiceServer,
    get_logger,
)

logger = get_logger("groot_executor")

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
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
    embodiment_tag: str = "new_embodiment"
    camera_topic_map: dict = field(default_factory=dict)
    joint_topic_map: dict = field(default_factory=dict)
    task_instruction: str = ""


@dataclass
class ExecutorConfig:
    """Executor configuration."""

    router_ip: str = "127.0.0.1"
    router_port: int = 7447
    domain_id: int = 30
    node_name: str = "groot_executor"
    namespace: str = "/"

    # Topic/Service names
    train_service: str = "/groot/train"
    infer_service: str = "/groot/infer"
    stop_service: str = "/groot/stop"
    status_service: str = "/groot/status"
    get_action_chunk_service: str = "/groot/get_action_chunk"
    embodiment_list_service: str = "/groot/embodiment_list"
    checkpoint_list_service: str = "/groot/checkpoint_list"
    progress_topic: str = "/groot/progress"
    action_topic: str = "/groot/action"

    # Progress publish interval
    progress_interval_sec: float = 1.0


# Available GR00T embodiments with full metadata
AVAILABLE_EMBODIMENTS = [
    {
        "name": "gr1",
        "display_name": "Fourier GR1",
        "description": "Fourier Intelligence GR1 humanoid robot",
        "category": "humanoid",
        "dof": 32,
    },
    {
        "name": "so100",
        "display_name": "SO-100",
        "description": "SO-100 robot arm",
        "category": "manipulator",
        "dof": 7,
    },
    {
        "name": "unitree_g1",
        "display_name": "Unitree G1",
        "description": "Unitree G1 humanoid robot",
        "category": "humanoid",
        "dof": 29,
    },
    {
        "name": "new_embodiment",
        "display_name": "Custom Embodiment",
        "description": "Custom robot embodiment (requires modality.json)",
        "category": "custom",
        "dof": 0,
    },
]


class Gr00tExecutor:
    """
    GR00T N1.6 Executor - Manages finetuning and inference via Zenoh.

    Shared infrastructure: state management, service setup, lifecycle.
    Training logic is in training.py (TrainingHandler).
    Inference logic is in inference.py (InferenceHandler).
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
        self._get_action_chunk_service: Optional[ROS2ServiceServer] = None
        self._stop_service: Optional[ROS2ServiceServer] = None
        self._status_service: Optional[ROS2ServiceServer] = None
        self._embodiment_list_service: Optional[ROS2ServiceServer] = None
        self._checkpoint_list_service: Optional[ROS2ServiceServer] = None
        self._progress_publisher: Optional[ROS2Publisher] = None
        self._action_publisher: Optional[ROS2Publisher] = None
        self._progress_thread: Optional[threading.Thread] = None

        # Track last published progress to avoid duplicate publishes
        self._last_published_step: int = -1
        self._last_published_loss: float = float("nan")

        # Initialize handlers (separated modules)
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
        logger.info("Starting GR00T N1.6 Executor...")
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
            (
                "get_action_chunk",
                self._get_action_chunk_service,
                self._inference_handler.handle_get_action_chunk,
            ),
            ("stop", self._stop_service, self._handle_stop),
            ("status", self._status_service, self._handle_status),
            (
                "embodiment_list",
                self._embodiment_list_service,
                self._handle_embodiment_list,
            ),
            (
                "checkpoint_list",
                self._checkpoint_list_service,
                self._handle_checkpoint_list,
            ),
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

        logger.info("GR00T N1.6 Executor started successfully")

    def _init_services(self) -> None:
        """Initialize ROS2 services and publishers."""
        common_kwargs = {
            "node_name": self.config.node_name,
            "namespace": self.config.namespace,
            "domain_id": self.config.domain_id,
            "router_ip": self.config.router_ip,
            "router_port": self.config.router_port,
        }

        self._train_service = ROS2ServiceServer(
            service_name=self.config.train_service,
            srv_type="physical_ai_interfaces/srv/TrainModel",
            mode="queue",
            **common_kwargs,
        )
        logger.info(f"Train service ready: {self.config.train_service}")

        self._infer_service = ROS2ServiceServer(
            service_name=self.config.infer_service,
            srv_type="physical_ai_interfaces/srv/StartInference",
            mode="queue",
            **common_kwargs,
        )
        logger.info(f"Infer service ready: {self.config.infer_service}")

        self._get_action_chunk_service = ROS2ServiceServer(
            service_name=self.config.get_action_chunk_service,
            srv_type="physical_ai_interfaces/srv/GetActionChunk",
            mode="queue",
            **common_kwargs,
        )
        logger.info(
            f"Get action chunk service ready: {self.config.get_action_chunk_service}"
        )

        self._stop_service = ROS2ServiceServer(
            service_name=self.config.stop_service,
            srv_type="physical_ai_interfaces/srv/StopTraining",
            mode="queue",
            **common_kwargs,
        )
        logger.info(f"Stop service ready: {self.config.stop_service}")

        self._status_service = ROS2ServiceServer(
            service_name=self.config.status_service,
            srv_type="physical_ai_interfaces/srv/TrainingStatus",
            mode="queue",
            **common_kwargs,
        )
        logger.info(f"Status service ready: {self.config.status_service}")

        self._embodiment_list_service = ROS2ServiceServer(
            service_name=self.config.embodiment_list_service,
            srv_type="physical_ai_interfaces/srv/PolicyList",
            mode="queue",
            **common_kwargs,
        )
        logger.info(
            f"Embodiment list service ready: {self.config.embodiment_list_service}"
        )

        self._checkpoint_list_service = ROS2ServiceServer(
            service_name=self.config.checkpoint_list_service,
            srv_type="physical_ai_interfaces/srv/CheckpointList",
            mode="queue",
            **common_kwargs,
        )
        logger.info(
            f"Checkpoint list service ready: {self.config.checkpoint_list_service}"
        )

        self._progress_publisher = ROS2Publisher(
            topic=self.config.progress_topic,
            msg_type="physical_ai_interfaces/msg/TrainingProgress",
            **common_kwargs,
        )
        logger.info(f"Progress publisher ready: {self.config.progress_topic}")

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
            "action_chunk": np.array([], dtype=np.float64),
            "chunk_size": 0,
            "action_dim": 0,
            "action_keys": [],
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
    # Stop Handler (shared - handles both training and inference)
    # ========================================================================

    def _handle_stop(self, request: Any) -> Any:
        """Handle stop request."""
        logger.info("Received stop request")

        if self.state == ExecutorState.IDLE:
            return self._create_response(
                self._stop_service, success=False, message="No task is running"
            )

        self._stop_requested.set()
        self.state = ExecutorState.STOPPING

        # Cleanup inference
        self._inference_handler.cleanup()

        # Wait for training thread
        if self._training_thread and self._training_thread.is_alive():
            self._training_thread.join(timeout=10.0)

        # Cleanup training
        self._training_handler.cleanup()

        self.state = ExecutorState.IDLE

        return self._create_response(
            self._stop_service, success=True, message="Stop requested"
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
    # Embodiment List Handler
    # ========================================================================

    def _handle_embodiment_list(self, request: Any) -> Any:
        """Handle embodiment list request."""
        category = getattr(request, "category", "")
        embodiments = AVAILABLE_EMBODIMENTS

        if category:
            embodiments = [e for e in embodiments if e.get("category") == category]

        return self._create_response(
            self._embodiment_list_service,
            success=True,
            message="",
            policies_json=json.dumps(embodiments),
        )

    # ========================================================================
    # Checkpoint List Handler
    # ========================================================================

    def _handle_checkpoint_list(self, request: Any) -> Any:
        """Handle checkpoint list request."""
        workspace_dir = os.environ.get("GROOT_WORKSPACE", "/workspace")
        checkpoints_dir = Path(workspace_dir) / "checkpoints"

        checkpoints = []

        if checkpoints_dir.exists():
            for run_dir in checkpoints_dir.iterdir():
                if not run_dir.is_dir():
                    continue

                config_file = run_dir / "config.json"
                if config_file.exists():
                    checkpoints.append(
                        {
                            "name": run_dir.name,
                            "path": str(run_dir),
                            "type": "groot_n1.6",
                        }
                    )
                    continue

                for ckpt_dir in run_dir.iterdir():
                    if not ckpt_dir.is_dir():
                        continue
                    if (ckpt_dir / "config.json").exists() or (
                        ckpt_dir / "model.safetensors"
                    ).exists():
                        checkpoints.append(
                            {
                                "name": f"{run_dir.name}/{ckpt_dir.name}",
                                "path": str(ckpt_dir),
                                "type": "groot_n1.6",
                            }
                        )

        return self._create_response(
            self._checkpoint_list_service,
            success=True,
            message="",
            checkpoints_json=json.dumps(checkpoints),
        )

    # ========================================================================
    # Progress Publishing
    # ========================================================================

    def _progress_publish_loop(self) -> None:
        """Publish progress only when there are changes."""
        while self._running:
            try:
                if self.state == ExecutorState.TRAINING and self._progress_publisher:
                    current_step = self._progress.step
                    current_loss = self._progress.loss

                    step_changed = current_step != self._last_published_step

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
        logger.info("Stopping GR00T N1.6 Executor...")
        self._running = False

        self._stop_requested.set()

        if self._training_thread and self._training_thread.is_alive():
            self._training_thread.join(timeout=5.0)

        self._inference_handler.cleanup()
        self._training_handler.cleanup()

        # Close services
        for service in [
            self._train_service,
            self._infer_service,
            self._get_action_chunk_service,
            self._stop_service,
            self._status_service,
            self._embodiment_list_service,
            self._checkpoint_list_service,
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

        logger.info("GR00T N1.6 Executor stopped")

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

    executor = Gr00tExecutor(config)
    executor.run_forever()
