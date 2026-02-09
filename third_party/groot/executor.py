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
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import torch

# Add zenoh_ros2_sdk to path
ZENOH_SDK_PATH = os.environ.get("ZENOH_SDK_PATH", "/zenoh_sdk")
if os.path.exists(ZENOH_SDK_PATH):
    sys.path.insert(0, ZENOH_SDK_PATH)

from zenoh_ros2_sdk import (  # noqa: E402
    ROS2Publisher,
    ROS2ServiceServer,
    ROS2Subscriber,
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
    inference_freq: float = 30.0  # Hz
    camera_topics: list = field(default_factory=list)
    joint_topic: str = ""


@dataclass
class ExecutorConfig:
    """Executor configuration."""

    router_ip: str = "127.0.0.1"
    router_port: int = 7447
    domain_id: int = 0
    node_name: str = "groot_executor"
    namespace: str = "/"

    # Topic/Service names
    train_service: str = "/groot/train"
    infer_service: str = "/groot/infer"
    stop_service: str = "/groot/stop"
    status_service: str = "/groot/status"
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

    This class provides:
    - ROS2 service servers for train/infer/stop/status commands
    - ROS2 publisher for progress updates and action outputs
    - Thread-safe state management
    - Graceful shutdown handling
    """

    def __init__(self, config: Optional[ExecutorConfig] = None):
        """Initialize the executor."""
        self.config = config or ExecutorConfig()
        self._state = ExecutorState.IDLE
        self._state_lock = threading.Lock()
        self._progress = TrainingProgress()
        self._training_thread: Optional[threading.Thread] = None
        self._inference_thread: Optional[threading.Thread] = None
        self._stop_requested = threading.Event()
        self._start_time: Optional[float] = None
        self._current_job_id: Optional[str] = None
        self._running = False

        # Store original logging method for restoration
        self._original_log_info: Optional[Callable] = None

        # Inference state
        self._loaded_policy: Optional[Any] = None
        self._inference_running = False
        self._inference_config: Optional[InferenceConfig] = None
        self._ros2_subscribers: list = []
        self._latest_observations: dict = {
            "video": {},
            "state": {},
            "language": {},
            "timestamp": None,
        }

        # Services and publishers (initialized in start())
        self._train_service: Optional[ROS2ServiceServer] = None
        self._infer_service: Optional[ROS2ServiceServer] = None
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
            ("train", self._train_service, self._handle_train),
            ("infer", self._infer_service, self._handle_infer),
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

        # Embodiment list service
        self._embodiment_list_service = ROS2ServiceServer(
            service_name=self.config.embodiment_list_service,
            srv_type="physical_ai_interfaces/srv/PolicyList",
            mode="queue",
            **common_kwargs,
        )
        logger.info(
            f"Embodiment list service ready: {self.config.embodiment_list_service}"
        )

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
    # Training Handlers
    # ========================================================================

    def _handle_train(self, request: Any) -> Any:
        """Handle train (finetune) request."""
        logger.info(
            f"Received train request: dataset={request.dataset_path}, "
            f"embodiment={getattr(request, 'embodiment_tag', 'new_embodiment')}"
        )

        if self.state in (ExecutorState.TRAINING, ExecutorState.INFERENCE):
            return self._create_response(
                self._train_service,
                success=False,
                message=f"Already {self.state.value}. Stop current task first.",
                job_id="",
            )

        job_id = f"groot_train_{int(time.time())}"
        self._current_job_id = job_id

        self._stop_requested.clear()
        self._training_thread = threading.Thread(
            target=self._run_training,
            args=(request,),
            daemon=True,
        )
        self._training_thread.start()

        return self._create_response(
            self._train_service,
            success=True,
            message="GR00T finetuning started",
            job_id=job_id,
        )

    def _run_training(self, request: Any) -> None:
        """Run GR00T finetuning in background thread."""
        try:
            self.state = ExecutorState.TRAINING
            self._start_time = time.time()
            max_steps = getattr(request, "steps", 10000) or 10000
            self._progress = TrainingProgress(total_steps=max_steps)

            logger.info("Starting GR00T N1.6 finetuning...")

            self._execute_training(request)

            if self._stop_requested.is_set():
                logger.info("Finetuning stopped by user")
            else:
                logger.info("Finetuning completed successfully")

            self.state = ExecutorState.IDLE

            # Publish final progress with IDLE state
            if self._progress_publisher:
                self._publish_progress()
                logger.info(
                    f"Final progress published: step={self._progress.step}, state=idle"
                )

        except Exception as e:
            logger.error(f"Finetuning failed: {e}", exc_info=True)
            self.state = ExecutorState.ERROR

            # Publish error state
            if self._progress_publisher:
                self._publish_progress()
                logger.info(
                    f"Error state published: step={self._progress.step}, state=error"
                )

        finally:
            self._current_job_id = None

    def _build_finetune_config(self, request: Any):
        """Build GR00T FinetuneConfig from request."""
        from gr00t.data.embodiment_tags import EmbodimentTag

        # Get embodiment tag
        embodiment_tag_str = getattr(request, "policy_type", "new_embodiment")
        if not embodiment_tag_str:
            embodiment_tag_str = "new_embodiment"

        # Try to convert to EmbodimentTag enum
        try:
            embodiment_tag = EmbodimentTag(embodiment_tag_str)
        except ValueError:
            logger.warning(
                f"Unknown embodiment tag '{embodiment_tag_str}', using NEW_EMBODIMENT"
            )
            embodiment_tag = EmbodimentTag.NEW_EMBODIMENT

        # Dataset path (required)
        dataset_path = getattr(request, "dataset_path", "")
        if not dataset_path:
            raise ValueError("dataset_path is required")

        # Base model path
        base_model = "nvidia/GR00T-N1.6-3B"

        # Output directory
        workspace_dir = os.environ.get("GROOT_WORKSPACE", "/workspace")
        checkpoints_dir = f"{workspace_dir}/checkpoints"

        if hasattr(request, "output_dir") and request.output_dir:
            output_dir = request.output_dir
            if not output_dir.startswith("/"):
                output_dir = f"{checkpoints_dir}/{output_dir}"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = f"{checkpoints_dir}/groot_{timestamp}"

        # Training parameters
        max_steps = getattr(request, "steps", 10000) or 10000
        batch_size = getattr(request, "batch_size", 64) or 64
        learning_rate = getattr(request, "learning_rate", 1e-4) or 1e-4
        save_steps = getattr(request, "save_freq", 500) or 500
        use_wandb = bool(getattr(request, "wandb_project", ""))

        self._progress.total_steps = max_steps

        # Build FinetuneConfig dataclass
        from gr00t.configs.finetune_config import FinetuneConfig

        finetune_config = FinetuneConfig(
            base_model_path=base_model,
            dataset_path=dataset_path,
            embodiment_tag=embodiment_tag,
            output_dir=output_dir,
            max_steps=max_steps,
            global_batch_size=batch_size,
            learning_rate=learning_rate,
            save_steps=save_steps,
            use_wandb=use_wandb,
        )

        return finetune_config

    def _execute_training(self, request: Any) -> None:
        """Execute GR00T finetuning using Isaac-GR00T API directly."""
        from gr00t.configs.base_config import get_default_config
        from gr00t.experiment.experiment import run

        # Setup logging interceptor to capture progress
        self._setup_logging_interceptor()

        try:
            # Build finetune config
            ft_config = self._build_finetune_config(request)
            embodiment_tag = ft_config.embodiment_tag.value

            logger.info(f"Starting GR00T finetuning with config:")
            logger.info(f"  Dataset: {ft_config.dataset_path}")
            logger.info(f"  Embodiment: {embodiment_tag}")
            logger.info(f"  Output: {ft_config.output_dir}")
            logger.info(f"  Max steps: {ft_config.max_steps}")
            logger.info(f"  Batch size: {ft_config.global_batch_size}")
            logger.info(f"  Learning rate: {ft_config.learning_rate}")

            # Build config from FinetuneConfig (same as launch_finetune.py)
            config = get_default_config().load_dict(
                {
                    "data": {
                        "download_cache": False,
                        "datasets": [
                            {
                                "dataset_paths": [ft_config.dataset_path],
                                "mix_ratio": 1.0,
                                "embodiment_tag": embodiment_tag,
                            }
                        ],
                    }
                }
            )
            config.load_config_path = None

            # Apply finetune config settings
            config.model.tune_llm = ft_config.tune_llm
            config.model.tune_visual = ft_config.tune_visual
            config.model.tune_projector = ft_config.tune_projector
            config.model.tune_diffusion_model = ft_config.tune_diffusion_model
            config.model.state_dropout_prob = ft_config.state_dropout_prob
            config.model.random_rotation_angle = ft_config.random_rotation_angle
            config.model.color_jitter_params = ft_config.color_jitter_params

            config.model.load_bf16 = False
            config.model.reproject_vision = False
            config.model.eagle_collator = True
            config.model.model_name = "nvidia/Eagle-Block2A-2B-v2"
            config.model.backbone_trainable_params_fp32 = True
            config.model.use_relative_action = True

            config.training.start_from_checkpoint = ft_config.base_model_path
            config.training.optim = "adamw_torch"
            config.training.global_batch_size = ft_config.global_batch_size
            config.training.dataloader_num_workers = ft_config.dataloader_num_workers
            config.training.learning_rate = ft_config.learning_rate
            config.training.gradient_accumulation_steps = (
                ft_config.gradient_accumulation_steps
            )
            config.training.output_dir = ft_config.output_dir
            config.training.save_steps = ft_config.save_steps
            config.training.save_total_limit = ft_config.save_total_limit
            config.training.num_gpus = ft_config.num_gpus
            config.training.use_wandb = ft_config.use_wandb
            config.training.max_steps = ft_config.max_steps
            config.training.weight_decay = ft_config.weight_decay
            config.training.warmup_ratio = ft_config.warmup_ratio
            config.training.wandb_project = "finetune-gr00t-n1d6"

            config.data.shard_size = ft_config.shard_size
            config.data.episode_sampling_rate = ft_config.episode_sampling_rate
            config.data.num_shards_per_epoch = ft_config.num_shards_per_epoch

            # Run training (blocking call)
            run(config)

        finally:
            self._restore_logging()

    def _setup_logging_interceptor(self) -> None:
        """Setup logging interceptor to capture training progress."""
        import re

        self._original_log_info = logging.Logger.info
        executor_ref = self

        # Patterns for HuggingFace Trainer output
        patterns = {
            "step": re.compile(r"'global_step':\s*(\d+)"),
            "loss": re.compile(r"'loss':\s*([\d.]+)"),
            "lr": re.compile(r"'learning_rate':\s*([\d.e+-]+)"),
            "grad_norm": re.compile(r"'grad_norm':\s*([\d.]+)"),
        }

        # Alternative patterns for different log formats
        alt_patterns = {
            "step": re.compile(r"step\s*[=:]\s*(\d+)", re.IGNORECASE),
            "loss": re.compile(r"loss\s*[=:]\s*([\d.]+)", re.IGNORECASE),
            "lr": re.compile(r"lr\s*[=:]\s*([\d.e+-]+)", re.IGNORECASE),
        }

        def interceptor(self_logger, msg, *args, **kwargs):
            executor_ref._original_log_info(self_logger, msg, *args, **kwargs)

            try:
                log_msg = str(msg) % args if args else str(msg)

                # Check for stop request
                if executor_ref._stop_requested.is_set():
                    return

                # Try primary patterns first
                for key, pattern in patterns.items():
                    match = pattern.search(log_msg)
                    if match:
                        value = match.group(1)
                        if key == "step":
                            executor_ref._progress.step = int(value)
                        elif key == "loss":
                            executor_ref._progress.loss = float(value)
                        elif key == "lr":
                            executor_ref._progress.learning_rate = float(value)
                        elif key == "grad_norm":
                            executor_ref._progress.gradient_norm = float(value)

                # Try alternative patterns
                for key, pattern in alt_patterns.items():
                    match = pattern.search(log_msg)
                    if match:
                        value = match.group(1)
                        if key == "step":
                            executor_ref._progress.step = int(value)
                        elif key == "loss":
                            executor_ref._progress.loss = float(value)
                        elif key == "lr":
                            executor_ref._progress.learning_rate = float(value)

                # Update timing
                if executor_ref._start_time:
                    elapsed = time.time() - executor_ref._start_time
                    executor_ref._progress.elapsed_seconds = elapsed
                    if executor_ref._progress.step > 0:
                        steps_remaining = (
                            executor_ref._progress.total_steps
                            - executor_ref._progress.step
                        )
                        time_per_step = elapsed / executor_ref._progress.step
                        executor_ref._progress.eta_seconds = (
                            steps_remaining * time_per_step
                        )

            except Exception:
                pass

        logging.Logger.info = interceptor

    def _restore_logging(self) -> None:
        """Restore original logging."""
        if self._original_log_info is not None:
            logging.Logger.info = self._original_log_info
            self._original_log_info = None

    # ========================================================================
    # Inference Handlers
    # ========================================================================

    def _handle_infer(self, request: Any) -> Any:
        """Handle inference start request."""
        logger.info(f"Received infer request: model_path={request.model_path}")

        if self.state in (ExecutorState.TRAINING, ExecutorState.INFERENCE):
            return self._create_response(
                self._infer_service,
                success=False,
                message=f"Already {self.state.value}. Stop current task first.",
            )

        model_path = getattr(request, "model_path", "")
        if not model_path:
            return self._create_response(
                self._infer_service,
                success=False,
                message="Missing required parameter: model_path",
            )

        try:
            logger.info(f"Loading GR00T policy from: {model_path}")

            # Get embodiment tag
            embodiment_tag = getattr(request, "embodiment_tag", "new_embodiment")
            if not embodiment_tag:
                embodiment_tag = "new_embodiment"

            self._loaded_policy = self._load_policy(model_path, embodiment_tag)

            if self._loaded_policy is None:
                return self._create_response(
                    self._infer_service,
                    success=False,
                    message="Failed to load GR00T policy",
                )

            inference_freq = getattr(request, "inference_freq", 30.0)
            camera_topics = getattr(request, "camera_topics", None)
            if not camera_topics:
                camera_topics = getattr(request, "image_topics", [])
            joint_topic = getattr(request, "joint_topic", None)
            if not joint_topic:
                joint_topic = getattr(request, "joint_state_topic", "")

            self._inference_config = InferenceConfig(
                model_path=model_path,
                embodiment_tag=embodiment_tag,
                inference_freq=inference_freq,
                camera_topics=camera_topics,
                joint_topic=joint_topic,
            )

            self._latest_observations = {
                "video": {},
                "state": {},
                "language": {"task": [["Pick up the object"]]},  # Default task
                "timestamp": None,
            }

            if camera_topics or joint_topic:
                self._setup_ros2_subscribers(camera_topics, joint_topic)

            self._inference_running = True
            self.state = ExecutorState.INFERENCE

            self._inference_thread = threading.Thread(
                target=self._inference_loop,
                args=(inference_freq,),
                daemon=True,
            )
            self._inference_thread.start()

            return self._create_response(
                self._infer_service, success=True, message="GR00T inference started"
            )

        except Exception as e:
            logger.error(f"Failed to start inference: {e}", exc_info=True)
            return self._create_response(
                self._infer_service,
                success=False,
                message=f"Failed to start inference: {e}",
            )

    def _load_policy(self, model_path: str, embodiment_tag: str) -> Optional[Any]:
        """Load a GR00T policy from checkpoint."""
        try:
            from gr00t.data.embodiment_tags import EmbodimentTag
            from gr00t.policy.gr00t_policy import Gr00tPolicy

            # Get embodiment tag enum
            try:
                emb_tag = EmbodimentTag(embodiment_tag)
            except ValueError:
                logger.warning(
                    f"Unknown embodiment tag '{embodiment_tag}', using NEW_EMBODIMENT"
                )
                emb_tag = EmbodimentTag.NEW_EMBODIMENT

            logger.info(f"Loading GR00T policy from {model_path}")
            logger.info(f"Embodiment: {emb_tag.value}")

            device = "cuda" if torch.cuda.is_available() else "cpu"

            policy = Gr00tPolicy(
                embodiment_tag=emb_tag,
                model_path=model_path,
                device=device,
            )

            logger.info(f"GR00T policy loaded successfully on {device}")
            return policy

        except Exception as e:
            logger.error(f"Failed to load GR00T policy: {e}", exc_info=True)
            return None

    def _setup_ros2_subscribers(
        self, camera_topics: list, joint_topic: str
    ) -> None:
        """Setup ROS2 topic subscribers for sensor data."""
        try:
            # Subscribe to camera topics
            for cam_config in camera_topics:
                topic = (
                    cam_config.get("topic")
                    if isinstance(cam_config, dict)
                    else cam_config
                )
                name = (
                    cam_config.get("name", topic.split("/")[-2])
                    if isinstance(cam_config, dict)
                    else topic.split("/")[-2]
                )

                if not topic:
                    continue

                logger.info(f"Subscribing to camera topic: {topic} (name: {name})")

                def make_image_callback(cam_name):
                    def callback(msg):
                        self._on_image_received(cam_name, msg)

                    return callback

                sub = ROS2Subscriber(
                    topic=topic,
                    msg_type="sensor_msgs/msg/CompressedImage",
                    callback=make_image_callback(name),
                )
                self._ros2_subscribers.append(sub)

            # Subscribe to joint state topic
            if joint_topic:
                logger.info(f"Subscribing to joint state topic: {joint_topic}")
                sub = ROS2Subscriber(
                    topic=joint_topic,
                    msg_type="sensor_msgs/msg/JointState",
                    callback=self._on_joint_state_received,
                )
                self._ros2_subscribers.append(sub)

            logger.info(f"Setup {len(self._ros2_subscribers)} ROS2 subscribers")

        except Exception as e:
            logger.error(f"Failed to setup ROS2 subscribers: {e}", exc_info=True)

    def _on_image_received(self, camera_name: str, msg: Any) -> None:
        """Callback for camera image received."""
        try:
            import cv2

            image_data = np.frombuffer(bytes(msg.data), dtype=np.uint8)
            image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)

            if image is not None:
                # GR00T expects (B, T, H, W, C) format with uint8
                # Convert to (1, 1, H, W, C) for single frame
                image = image[np.newaxis, np.newaxis, ...]
                self._latest_observations["video"][camera_name] = image
                self._latest_observations["timestamp"] = time.time()
        except Exception as e:
            logger.debug(f"Error decoding image: {e}")

    def _on_joint_state_received(self, msg: Any) -> None:
        """Callback for joint state received."""
        try:
            # GR00T expects (B, T, D) format with float32
            positions = np.array(msg.position, dtype=np.float32)
            # Reshape to (1, 1, D)
            positions = positions[np.newaxis, np.newaxis, :]
            self._latest_observations["state"]["joint_positions"] = positions
            self._latest_observations["timestamp"] = time.time()
        except Exception as e:
            logger.debug(f"Error processing joint state: {e}")

    def _inference_loop(self, freq_hz: float) -> None:
        """Real-time inference loop."""
        logger.info(f"Starting GR00T inference loop at {freq_hz} Hz")

        interval = 1.0 / freq_hz
        action_count = 0
        use_real_observations = len(self._ros2_subscribers) > 0

        logger.info(
            f"Using {'real ROS2 observations' if use_real_observations else 'dummy observations'}"
        )

        while self._inference_running:
            loop_start = time.time()

            try:
                if self._loaded_policy is not None:
                    if use_real_observations:
                        action = self._predict_from_observations()
                    else:
                        action = self._predict_dummy_action()

                    if action is not None:
                        action_count += 1
                        self._publish_action(action, action_count)

            except Exception as e:
                logger.error(f"Inference loop error: {e}")

            elapsed = time.time() - loop_start
            sleep_time = max(0, interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

        self._cleanup_ros2_subscribers()
        logger.info(f"Inference loop stopped. Total actions published: {action_count}")
        self.state = ExecutorState.IDLE

    def _predict_from_observations(self) -> Optional[dict[str, Any]]:
        """Predict action from real observation data."""
        try:
            obs = self._latest_observations

            if obs["timestamp"] is None:
                return None

            if time.time() - obs["timestamp"] > 1.0:
                logger.debug("Observations too old, skipping inference")
                return None

            # Build observation dict for GR00T policy
            observation = {
                "video": obs["video"],
                "state": obs["state"],
                "language": obs["language"],
            }

            # Get action from policy
            action, info = self._loaded_policy.get_action(observation)

            # Convert action dict to standard format
            result = {
                "joint_positions": [],
                "gripper": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Extract action values (format depends on modality config)
            for key, value in action.items():
                if isinstance(value, np.ndarray):
                    # Action shape is (B, T, D) - take first batch, first timestep
                    action_values = value[0, 0].tolist()
                    result["joint_positions"] = action_values[:-1]
                    result["gripper"] = float(action_values[-1])
                    break

            return result

        except Exception as e:
            logger.debug(f"Error in real inference: {e}")
            return None

    def _predict_dummy_action(self) -> Optional[dict[str, Any]]:
        """Generate dummy action for testing."""
        try:
            action = {
                "joint_positions": np.random.randn(6).tolist(),
                "gripper": float(np.random.rand()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            return action
        except Exception as e:
            logger.error(f"Error generating action: {e}")
            return None

    def _publish_action(self, action: dict[str, Any], seq: int) -> None:
        """Publish predicted action."""
        if self._action_publisher is None:
            return

        try:
            joint_positions = action.get("joint_positions", [])
            if isinstance(joint_positions, list):
                joint_positions = np.array(joint_positions, dtype=np.float64)

            self._action_publisher.publish(
                joint_positions=joint_positions,
                gripper=float(action.get("gripper", 0.0)),
                timestamp=float(time.time()),
            )
        except Exception as e:
            logger.error(f"Failed to publish action: {e}")

    def _cleanup_ros2_subscribers(self) -> None:
        """Cleanup ROS2 subscribers."""
        for sub in self._ros2_subscribers:
            try:
                sub.close()
            except Exception:
                pass
        self._ros2_subscribers = []

    # ========================================================================
    # Stop Handler
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

        # Stop inference
        if self._inference_running:
            self._inference_running = False
            if self._inference_thread and self._inference_thread.is_alive():
                self._inference_thread.join(timeout=5.0)

            if self._loaded_policy is not None:
                del self._loaded_policy
                self._loaded_policy = None
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        if self._training_thread and self._training_thread.is_alive():
            self._training_thread.join(timeout=10.0)

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

        # Scan for GR00T checkpoints
        if checkpoints_dir.exists():
            for run_dir in checkpoints_dir.iterdir():
                if not run_dir.is_dir():
                    continue

                # Check for model files
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

                # Check for checkpoint subdirectories
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
                    # Only publish if step or loss changed
                    current_step = self._progress.step
                    current_loss = self._progress.loss

                    step_changed = current_step != self._last_published_step

                    # Handle NaN comparison properly
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
        self._inference_running = False

        if self._training_thread and self._training_thread.is_alive():
            self._training_thread.join(timeout=5.0)

        if self._inference_thread and self._inference_thread.is_alive():
            self._inference_thread.join(timeout=5.0)

        self._cleanup_ros2_subscribers()

        # Close services
        for service in [
            self._train_service,
            self._infer_service,
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
        domain_id=int(os.environ.get("ROS_DOMAIN_ID", "0")),
    )

    executor = Gr00tExecutor(config)
    executor.run_forever()


if __name__ == "__main__":
    main()
