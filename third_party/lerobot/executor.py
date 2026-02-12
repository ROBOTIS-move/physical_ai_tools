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
    domain_id: int = 0
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

        # Inference state
        self._loaded_model: Optional[Any] = None
        self._inference_running = False
        self._inference_config: Optional[InferenceConfig] = None
        self._ros2_subscribers: list = []
        self._latest_observations: dict = {
            "images": {},
            "joint_state": None,
            "timestamp": None,
        }

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
        self._last_published_loss: float = float('nan')

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
            ("train", self._train_service, self._handle_train),
            ("infer", self._infer_service, self._handle_infer),
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
            'success': False,
            'message': '',
            'job_id': '',
            'state': 'unknown',
            'step': 0,
            'total_steps': 0,
            'loss': 0.0,
            'learning_rate': 0.0,
            'gradient_norm': 0.0,
            'elapsed_seconds': 0.0,
            'eta_seconds': 0.0,
            'policies_json': '[]',
            'checkpoints_json': '[]',
            'models_json': '[]',
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
        """Handle train request."""
        logger.info(
            f"Received train request: policy={request.policy_type}, "
            f"dataset={request.dataset_path}"
        )

        if self.state in (ExecutorState.TRAINING, ExecutorState.INFERENCE):
            return self._create_response(
                self._train_service,
                success=False,
                message=f"Already {self.state.value}. Stop current task first.",
                job_id=""
            )

        job_id = f"train_{int(time.time())}"
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
            message="Training started",
            job_id=job_id
        )

    def _run_training(self, request: Any) -> None:
        """Run training in background thread."""
        try:
            self.state = ExecutorState.TRAINING
            self._start_time = time.time()
            self._progress = TrainingProgress(total_steps=request.steps or 100000)

            logger.info("Starting LeRobot training...")

            args = self._build_training_args(request)
            logger.info(f"Training args: {args}")

            self._execute_training(args)

            if self._stop_requested.is_set():
                logger.info("Training stopped by user")
            else:
                logger.info("Training completed successfully")

            # Change state to IDLE first, then publish so the IDLE state is sent
            self.state = ExecutorState.IDLE

            # Publish final progress with IDLE state
            if self._progress_publisher:
                self._publish_progress()
                logger.info(f"Final progress published: step={self._progress.step}, state=idle")

        except Exception as e:
            logger.error(f"Training failed: {e}", exc_info=True)
            self.state = ExecutorState.ERROR

            # Publish error state
            if self._progress_publisher:
                self._publish_progress()
                logger.info(f"Error state published: step={self._progress.step}, state=error")

        finally:
            self._current_job_id = None

    def _build_training_args(self, request: Any) -> list[str]:
        """Build training arguments from request."""
        args = []

        policy_type = getattr(request, "policy_type", "act")
        args.append(f"--policy.type={policy_type}")

        dataset_path = getattr(request, "dataset_path", "")
        if dataset_path:
            args.append(f"--dataset.repo_id={dataset_path}")

        args.append("--policy.device=cuda")

        workspace_dir = os.environ.get("LEROBOT_WORKSPACE", "/workspace")
        checkpoints_dir = f"{workspace_dir}/checkpoints"

        if hasattr(request, "output_dir") and request.output_dir:
            output_dir = request.output_dir
            if not output_dir.startswith("/"):
                output_dir = f"{checkpoints_dir}/{output_dir}"
            args.append(f"--output_dir={output_dir}")
        else:
            args.append(f"--output_dir={checkpoints_dir}")

        if hasattr(request, "steps") and request.steps > 0:
            args.append(f"--steps={request.steps}")
            self._progress.total_steps = request.steps

        if hasattr(request, "batch_size") and request.batch_size > 0:
            args.append(f"--batch_size={request.batch_size}")

        if hasattr(request, "learning_rate") and request.learning_rate > 0:
            args.append(f"--optimizer.lr={request.learning_rate}")

        if hasattr(request, "eval_freq") and request.eval_freq > 0:
            args.append(f"--eval_freq={request.eval_freq}")

        if hasattr(request, "log_freq") and request.log_freq > 0:
            args.append(f"--log_freq={request.log_freq}")

        if hasattr(request, "save_freq") and request.save_freq > 0:
            args.append(f"--save_freq={request.save_freq}")
        else:
            args.append("--save_freq=500")

        if hasattr(request, "wandb_project") and request.wandb_project:
            args.append(f"--wandb.project={request.wandb_project}")

        push_to_hub = getattr(request, "push_to_hub", False)
        if not push_to_hub:
            args.append("--policy.push_to_hub=false")

        # Relax video-timestamp tolerance for datasets with frame alignment issues
        # Default 0.0001s is too strict; 0.04s allows up to ~1 frame drift at 30fps
        tolerance_s = getattr(request, "tolerance_s", 0.0)
        if tolerance_s > 0:
            args.append(f"--tolerance_s={tolerance_s}")
        else:
            args.append("--tolerance_s=0.04")

        return args

    def _execute_training(self, args: list[str]) -> None:
        """Execute LeRobot training with progress monitoring."""
        import draccus

        from lerobot.configs.train import TrainPipelineConfig
        from lerobot.scripts.lerobot_train import train as lerobot_train

        self._setup_logging_interceptor()

        try:
            cfg = draccus.parse(TrainPipelineConfig, None, args=args)
            lerobot_train(cfg)
        finally:
            self._restore_logging()

    def _setup_logging_interceptor(self) -> None:
        """Setup logging interceptor to capture training progress."""
        import re

        self._original_log_info = logging.Logger.info
        executor_ref = self

        patterns = {
            "step": re.compile(r"step:([\d.]+)([KMB]?)"),  # Handle K/M/B suffix
            "loss": re.compile(r"loss:([\d.]+)"),
            "grad": re.compile(r"grdn:([\d.]+)"),
            "lr": re.compile(r"lr:([\d.e+-]+)"),
            "epoch": re.compile(r"epch:([\d.]+)"),
        }

        def parse_number_with_suffix(value_str, suffix):
            """Parse numbers with K/M/B suffix (e.g., '1K' -> 1000)"""
            value = float(value_str)
            if suffix == 'K':
                value *= 1000
            elif suffix == 'M':
                value *= 1000000
            elif suffix == 'B':
                value *= 1000000000
            return int(value)

        def interceptor(self_logger, msg, *args, **kwargs):
            executor_ref._original_log_info(self_logger, msg, *args, **kwargs)

            try:
                log_msg = str(msg) % args if args else str(msg)

                if "step:" in log_msg:
                    for key, pattern in patterns.items():
                        match = pattern.search(log_msg)
                        if match:
                            value = match.group(1)
                            if key == "step":
                                suffix_str = match.group(2) if len(match.groups()) > 1 else ""
                                parsed_step = parse_number_with_suffix(value, suffix_str)
                                executor_ref._progress.step = parsed_step
                            elif key == "loss":
                                executor_ref._progress.loss = float(value)
                            elif key == "grad":
                                executor_ref._progress.gradient_norm = float(value)
                            elif key == "lr":
                                executor_ref._progress.learning_rate = float(value)
                            elif key == "epoch":
                                executor_ref._progress.epoch = float(value)

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
        if hasattr(self, "_original_log_info"):
            logging.Logger.info = self._original_log_info

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
                message=f"Already {self.state.value}. Stop current task first."
            )

        model_path = getattr(request, "model_path", "")
        if not model_path:
            return self._create_response(
                self._infer_service,
                success=False,
                message="Missing required parameter: model_path"
            )

        try:
            logger.info(f"Loading model from: {model_path}")
            self._loaded_model = self._load_policy(model_path)

            if self._loaded_model is None:
                return self._create_response(
                    self._infer_service,
                    success=False,
                    message="Failed to load model"
                )

            inference_freq = getattr(request, "inference_freq", 30.0)
            # Support both field naming conventions
            camera_topics = getattr(request, "camera_topics", None)
            if not camera_topics:
                camera_topics = getattr(request, "image_topics", [])
            joint_topic = getattr(request, "joint_topic", None)
            if not joint_topic:
                joint_topic = getattr(request, "joint_state_topic", "")

            self._inference_config = InferenceConfig(
                model_path=model_path,
                inference_freq=inference_freq,
                camera_topics=camera_topics,
                joint_topic=joint_topic,
            )

            self._latest_observations = {
                "images": {},
                "joint_state": None,
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
                self._infer_service,
                success=True,
                message="Inference started"
            )

        except Exception as e:
            logger.error(f"Failed to start inference: {e}", exc_info=True)
            return self._create_response(
                self._infer_service,
                success=False,
                message=f"Failed to start inference: {e}"
            )

    def _load_policy(self, model_path: str) -> Optional[Any]:
        """Load a LeRobot policy from checkpoint."""
        try:
            from lerobot.policies.factory import get_policy_class

            config_path = Path(model_path) / "config.json"
            if config_path.exists():
                with open(config_path) as f:
                    config = json.load(f)
                policy_type = config.get("type", "act")
            else:
                policy_type = "act"

            logger.info(f"Loading {policy_type} policy from {model_path}")

            PolicyClass = get_policy_class(policy_type)
            policy = PolicyClass.from_pretrained(model_path)

            device = "cuda" if torch.cuda.is_available() else "cpu"
            policy = policy.to(device)
            policy.eval()

            logger.info(f"Model loaded successfully on {device}")
            return policy

        except Exception as e:
            logger.error(f"Failed to load policy: {e}", exc_info=True)
            return None

    def _setup_ros2_subscribers(
        self, camera_topics: list, joint_topic: str
    ) -> None:
        """Setup ROS2 topic subscribers for sensor data."""
        try:
            # Subscribe to camera topics
            for cam_config in camera_topics:
                topic = cam_config.get("topic") if isinstance(cam_config, dict) else cam_config
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
                self._latest_observations["images"][camera_name] = image
                self._latest_observations["timestamp"] = time.time()
        except Exception as e:
            logger.debug(f"Error decoding image: {e}")

    def _on_joint_state_received(self, msg: Any) -> None:
        """Callback for joint state received."""
        try:
            joint_data = {
                "names": list(msg.name),
                "positions": list(msg.position),
                "velocities": list(msg.velocity) if msg.velocity else [],
                "efforts": list(msg.effort) if msg.effort else [],
            }
            self._latest_observations["joint_state"] = joint_data
            self._latest_observations["timestamp"] = time.time()
        except Exception as e:
            logger.debug(f"Error processing joint state: {e}")

    def _inference_loop(self, freq_hz: float) -> None:
        """Real-time inference loop."""
        logger.info(f"Starting inference loop at {freq_hz} Hz")

        interval = 1.0 / freq_hz
        action_count = 0
        use_real_observations = len(self._ros2_subscribers) > 0

        logger.info(
            f"Using {'real ROS2 observations' if use_real_observations else 'dummy observations'}"
        )

        while self._inference_running:
            loop_start = time.time()

            try:
                if self._loaded_model is not None:
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

            observation = {}

            for cam_name, image in obs["images"].items():
                image_tensor = self._preprocess_image(image)
                observation[f"observation.images.{cam_name}"] = image_tensor

            if obs["joint_state"] is not None:
                joint_state = obs["joint_state"]
                observation["observation.state"] = torch.tensor(
                    joint_state["positions"], dtype=torch.float32
                ).unsqueeze(0)

            with torch.no_grad():
                batch = {}
                for key, value in observation.items():
                    if isinstance(value, torch.Tensor):
                        batch[key] = value.to(self._loaded_model.device)

                action_tensor = self._loaded_model.select_action(batch)

                if isinstance(action_tensor, torch.Tensor):
                    action_values = action_tensor.cpu().numpy().flatten().tolist()
                else:
                    action_values = list(action_tensor)

            action = {
                "joint_positions": (
                    action_values[:-1] if len(action_values) > 1 else action_values
                ),
                "gripper": action_values[-1] if len(action_values) > 1 else 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            return action

        except Exception as e:
            logger.debug(f"Error in real inference: {e}")
            return None

    def _preprocess_image(self, image: np.ndarray) -> torch.Tensor:
        """Preprocess image for model input."""
        import cv2

        target_size = (224, 224)
        image = cv2.resize(image, target_size)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = image.astype(np.float32) / 255.0
        image = np.transpose(image, (2, 0, 1))
        tensor = torch.from_numpy(image).unsqueeze(0)
        return tensor

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
            # ActionOutput message has: joint_positions, gripper, timestamp
            # rosbags requires numpy arrays for array fields
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
                self._stop_service,
                success=False,
                message="No task is running"
            )

        self._stop_requested.set()
        self.state = ExecutorState.STOPPING

        if self._inference_running:
            self._inference_running = False
            if self._inference_thread and self._inference_thread.is_alive():
                self._inference_thread.join(timeout=5.0)

            if self._loaded_model is not None:
                del self._loaded_model
                self._loaded_model = None
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

        if self._training_thread and self._training_thread.is_alive():
            self._training_thread.join(timeout=10.0)

        self.state = ExecutorState.IDLE

        return self._create_response(
            self._stop_service,
            success=True,
            message="Stop requested"
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
            message=""
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
            policies_json=json.dumps(policies)
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
                                        "workspace" if outputs_dir == checkpoints_dir
                                        else "legacy"
                                    ),
                                }
                            )

        return self._create_response(
            self._checkpoint_list_service,
            success=True,
            message="",
            checkpoints_json=json.dumps(checkpoints)
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
            models_json=json.dumps(models)
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
                        if isinstance(current_loss, float) else False
                    )
                    last_is_nan = (
                        math.isnan(self._last_published_loss)
                        if isinstance(self._last_published_loss, float) else False
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
        domain_id=int(os.environ.get("ROS_DOMAIN_ID", "0")),
    )

    executor = LeRobotExecutor(config)
    executor.run_forever()


if __name__ == "__main__":
    main()
