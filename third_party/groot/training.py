"""
GR00T Training Handler - Finetuning logic for GR00T N1.6.

Separated from executor.py for clean code organization.
Training-specific methods: handle_train, run_training, build_finetune_config,
execute_training, logging interceptor.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Optional

from zenoh_ros2_sdk import get_logger

if TYPE_CHECKING:
    from executor import Gr00tExecutor

logger = get_logger("groot_training")


class TrainingHandler:
    """Handles GR00T finetuning requests.

    Takes a reference to the parent executor to access shared state
    (state machine, progress, services).
    """

    def __init__(self, executor: Gr00tExecutor):
        self._executor = executor
        self._original_log_info: Optional[Callable] = None

    def handle_train(self, request: Any) -> Any:
        """Handle train (finetune) request."""
        from executor import ExecutorState

        executor = self._executor
        logger.info(
            f"Received train request: dataset={request.dataset_path}, "
            f"embodiment={getattr(request, 'embodiment_tag', 'new_embodiment')}"
        )

        if executor.state in (ExecutorState.TRAINING, ExecutorState.INFERENCE):
            return executor._create_response(
                executor._train_service,
                success=False,
                message=f"Already {executor.state.value}. Stop current task first.",
                job_id="",
            )

        job_id = f"groot_train_{int(time.time())}"
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
            message="GR00T finetuning started",
            job_id=job_id,
        )

    def _run_training(self, request: Any) -> None:
        """Run GR00T finetuning in background thread."""
        from executor import ExecutorState, TrainingProgress

        executor = self._executor
        try:
            executor.state = ExecutorState.TRAINING
            executor._start_time = time.time()
            max_steps = getattr(request, "steps", 10000) or 10000
            executor._progress = TrainingProgress(total_steps=max_steps)

            logger.info("Starting GR00T N1.6 finetuning...")
            self._execute_training(request)

            if executor._stop_requested.is_set():
                logger.info("Finetuning stopped by user")
            else:
                logger.info("Finetuning completed successfully")

            executor.state = ExecutorState.IDLE

            if executor._progress_publisher:
                executor._publish_progress()

        except Exception as e:
            logger.error(f"Finetuning failed: {e}", exc_info=True)
            executor.state = ExecutorState.ERROR

            if executor._progress_publisher:
                executor._publish_progress()

        finally:
            executor._current_job_id = None

    def _build_finetune_config(self, request: Any):
        """Build GR00T FinetuneConfig from request."""
        from gr00t.data.embodiment_tags import EmbodimentTag

        embodiment_tag_str = getattr(request, "policy_type", "new_embodiment")
        if not embodiment_tag_str:
            embodiment_tag_str = "new_embodiment"

        try:
            embodiment_tag = EmbodimentTag(embodiment_tag_str)
        except ValueError:
            logger.warning(
                f"Unknown embodiment tag '{embodiment_tag_str}', using NEW_EMBODIMENT"
            )
            embodiment_tag = EmbodimentTag.NEW_EMBODIMENT

        dataset_path = getattr(request, "dataset_path", "")
        if not dataset_path:
            raise ValueError("dataset_path is required")

        base_model = "nvidia/GR00T-N1.6-3B"

        workspace_dir = os.environ.get("GROOT_WORKSPACE", "/workspace")
        checkpoints_dir = f"{workspace_dir}/checkpoints"

        if hasattr(request, "output_dir") and request.output_dir:
            output_dir = request.output_dir
            if not output_dir.startswith("/"):
                output_dir = f"{checkpoints_dir}/{output_dir}"
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = f"{checkpoints_dir}/groot_{timestamp}"

        max_steps = getattr(request, "steps", 10000) or 10000
        batch_size = getattr(request, "batch_size", 64) or 64
        learning_rate = getattr(request, "learning_rate", 1e-4) or 1e-4
        save_steps = getattr(request, "save_freq", 500) or 500
        use_wandb = bool(getattr(request, "wandb_project", ""))

        self._executor._progress.total_steps = max_steps

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

        self._setup_logging_interceptor()

        try:
            ft_config = self._build_finetune_config(request)
            embodiment_tag = ft_config.embodiment_tag.value

            logger.info(f"Starting GR00T finetuning with config:")
            logger.info(f"  Dataset: {ft_config.dataset_path}")
            logger.info(f"  Embodiment: {embodiment_tag}")
            logger.info(f"  Output: {ft_config.output_dir}")
            logger.info(f"  Max steps: {ft_config.max_steps}")
            logger.info(f"  Batch size: {ft_config.global_batch_size}")
            logger.info(f"  Learning rate: {ft_config.learning_rate}")

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

            run(config)

        finally:
            self._restore_logging()

    def _setup_logging_interceptor(self) -> None:
        """Setup logging interceptor to capture training progress."""
        self._original_log_info = logging.Logger.info
        executor = self._executor

        patterns = {
            "step": re.compile(r"'global_step':\s*(\d+)"),
            "loss": re.compile(r"'loss':\s*([\d.]+)"),
            "lr": re.compile(r"'learning_rate':\s*([\d.e+-]+)"),
            "grad_norm": re.compile(r"'grad_norm':\s*([\d.]+)"),
        }

        alt_patterns = {
            "step": re.compile(r"step\s*[=:]\s*(\d+)", re.IGNORECASE),
            "loss": re.compile(r"loss\s*[=:]\s*([\d.]+)", re.IGNORECASE),
            "lr": re.compile(r"lr\s*[=:]\s*([\d.e+-]+)", re.IGNORECASE),
        }

        original = self._original_log_info

        def interceptor(self_logger, msg, *args, **kwargs):
            original(self_logger, msg, *args, **kwargs)

            try:
                log_msg = str(msg) % args if args else str(msg)

                if executor._stop_requested.is_set():
                    return

                for key, pattern in patterns.items():
                    match = pattern.search(log_msg)
                    if match:
                        value = match.group(1)
                        if key == "step":
                            executor._progress.step = int(value)
                        elif key == "loss":
                            executor._progress.loss = float(value)
                        elif key == "lr":
                            executor._progress.learning_rate = float(value)
                        elif key == "grad_norm":
                            executor._progress.gradient_norm = float(value)

                for key, pattern in alt_patterns.items():
                    match = pattern.search(log_msg)
                    if match:
                        value = match.group(1)
                        if key == "step":
                            executor._progress.step = int(value)
                        elif key == "loss":
                            executor._progress.loss = float(value)
                        elif key == "lr":
                            executor._progress.learning_rate = float(value)

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
