"""
LeRobot Training Handler - Training logic for LeRobot.

Separated from executor.py for clean code organization.
Training-specific methods: handle_train, run_training, build_training_args,
execute_training, logging interceptor.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Optional

from zenoh_ros2_sdk import get_logger

if TYPE_CHECKING:
    from executor import LeRobotExecutor

logger = get_logger("lerobot_training")


class TrainingHandler:
    """Handles LeRobot training requests.

    Takes a reference to the parent executor to access shared state
    (state machine, progress, services).
    """

    def __init__(self, executor: LeRobotExecutor):
        self._executor = executor
        self._original_log_info: Optional[Callable] = None

    def handle_train(self, request: Any) -> Any:
        """Handle train request."""
        from executor import ExecutorState

        executor = self._executor
        logger.info(
            f"Received train request: policy={request.policy_type}, "
            f"dataset={request.dataset_path}"
        )

        if executor.state in (ExecutorState.TRAINING, ExecutorState.INFERENCE):
            return executor._create_response(
                executor._train_service,
                success=False,
                message=f"Already {executor.state.value}. Stop current task first.",
                job_id="",
            )

        job_id = f"train_{int(time.time())}"
        executor._current_job_id = job_id

        executor._stop_requested.clear()
        executor._training_thread = threading.Thread(
            target=self._run_training,
            args=(request,),
            daemon=True,
        )
        executor._training_thread.start()

        return executor._create_response(
            executor._train_service,
            success=True,
            message="Training started",
            job_id=job_id,
        )

    def _run_training(self, request: Any) -> None:
        """Run training in background thread."""
        from executor import ExecutorState, TrainingProgress

        executor = self._executor
        try:
            executor.state = ExecutorState.TRAINING
            executor._start_time = time.time()
            executor._progress = TrainingProgress(
                total_steps=request.steps or 100000
            )

            logger.info("Starting LeRobot training...")

            args = self._build_training_args(request)
            logger.info(f"Training args: {args}")

            self._execute_training(args)

            if executor._stop_requested.is_set():
                logger.info("Training stopped by user")
            else:
                logger.info("Training completed successfully")

            # Change state to IDLE first, then publish so the IDLE state is sent
            executor.state = ExecutorState.IDLE

            # Publish final progress with IDLE state
            if executor._progress_publisher:
                executor._publish_progress()
                logger.info(
                    f"Final progress published: step={executor._progress.step}, state=idle"
                )

        except Exception as e:
            logger.error(f"Training failed: {e}", exc_info=True)
            executor.state = ExecutorState.ERROR

            # Publish error state
            if executor._progress_publisher:
                executor._publish_progress()
                logger.info(
                    f"Error state published: step={executor._progress.step}, state=error"
                )

        finally:
            executor._current_job_id = None

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
            self._executor._progress.total_steps = request.steps

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
        self._original_log_info = logging.Logger.info
        executor = self._executor

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
            if suffix == "K":
                value *= 1000
            elif suffix == "M":
                value *= 1000000
            elif suffix == "B":
                value *= 1000000000
            return int(value)

        original = self._original_log_info

        def interceptor(self_logger, msg, *args, **kwargs):
            original(self_logger, msg, *args, **kwargs)

            try:
                log_msg = str(msg) % args if args else str(msg)

                if "step:" in log_msg:
                    for key, pattern in patterns.items():
                        match = pattern.search(log_msg)
                        if match:
                            value = match.group(1)
                            if key == "step":
                                suffix_str = (
                                    match.group(2)
                                    if len(match.groups()) > 1
                                    else ""
                                )
                                parsed_step = parse_number_with_suffix(
                                    value, suffix_str
                                )
                                executor._progress.step = parsed_step
                            elif key == "loss":
                                executor._progress.loss = float(value)
                            elif key == "grad":
                                executor._progress.gradient_norm = float(value)
                            elif key == "lr":
                                executor._progress.learning_rate = float(value)
                            elif key == "epoch":
                                executor._progress.epoch = float(value)

                    if executor._start_time:
                        elapsed = time.time() - executor._start_time
                        executor._progress.elapsed_seconds = elapsed
                        if executor._progress.step > 0:
                            steps_remaining = (
                                executor._progress.total_steps
                                - executor._progress.step
                            )
                            time_per_step = elapsed / executor._progress.step
                            executor._progress.eta_seconds = (
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

    def cleanup(self) -> None:
        """Cleanup training resources."""
        self._restore_logging()
