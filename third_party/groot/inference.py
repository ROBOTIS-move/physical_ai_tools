"""
GR00T Inference Handler - Inference logic for GR00T N1.6.

Separated from executor.py for clean code organization.
Inference-specific methods: handle_infer, load_policy, get_modality_config,
setup_ros2_subscribers, handle_get_action_chunk.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Optional

import numpy as np
import torch

from zenoh_ros2_sdk import (
    ROS2Subscriber,
    get_logger,
)

if TYPE_CHECKING:
    from executor import Gr00tExecutor

logger = get_logger("groot_inference")


class InferenceHandler:
    """Handles GR00T inference requests.

    Takes a reference to the parent executor to access shared state
    (state machine, config, services).
    """

    def __init__(self, executor: Gr00tExecutor):
        self._executor = executor

        # Inference-specific state
        self._loaded_policy: Optional[Any] = None
        self._inference_running = False
        self._inference_config = None
        self._ros2_subscribers: list = []
        self._latest_observations: dict = {
            "video": {},
            "state": {},
            "language": {},
            "timestamp": None,
        }
        self._action_keys: list = []

    @staticmethod
    def _parse_topic_map(topic_map_list: list) -> dict:
        """Parse 'name:topic' string list into {name: topic} dict."""
        result = {}
        for entry in topic_map_list:
            if ":" in entry:
                name, topic = entry.split(":", 1)
                result[name.strip()] = topic.strip()
        return result

    def handle_infer(self, request: Any) -> Any:
        """Handle inference start request."""
        from executor import ExecutorState, InferenceConfig

        executor = self._executor
        logger.info(f"Received infer request: model_path={request.model_path}")

        if executor.state in (ExecutorState.TRAINING, ExecutorState.INFERENCE):
            return executor._create_response(
                executor._infer_service,
                success=False,
                message=f"Already {executor.state.value}. Stop current task first.",
            )

        model_path = getattr(request, "model_path", "")
        if not model_path:
            return executor._create_response(
                executor._infer_service,
                success=False,
                message="Missing required parameter: model_path",
            )

        try:
            # 1. Load model
            embodiment_tag = getattr(request, "embodiment_tag", "new_embodiment")
            if not embodiment_tag:
                embodiment_tag = "new_embodiment"

            logger.info(f"Loading GR00T policy from: {model_path}")
            self._loaded_policy = self._load_policy(model_path, embodiment_tag)

            if self._loaded_policy is None:
                return executor._create_response(
                    executor._infer_service,
                    success=False,
                    message="Failed to load GR00T policy",
                )

            # 2. Read modality config from loaded model
            modality_config = self._get_modality_config(embodiment_tag)
            video_keys = (
                modality_config["video"].modality_keys
                if "video" in modality_config
                else []
            )
            state_keys = (
                modality_config["state"].modality_keys
                if "state" in modality_config
                else []
            )
            action_keys = (
                modality_config["action"].modality_keys
                if "action" in modality_config
                else []
            )

            logger.info(
                f"Modality config - video: {video_keys}, state: {state_keys}, action: {action_keys}"
            )

            # 3. Parse topic maps from request and filter by modality keys
            camera_topic_map = self._parse_topic_map(
                getattr(request, "camera_topic_map", [])
            )
            joint_topic_map = self._parse_topic_map(
                getattr(request, "joint_topic_map", [])
            )

            active_cameras = {
                k: v for k, v in camera_topic_map.items() if k in video_keys
            }
            active_joints = {
                k: v for k, v in joint_topic_map.items() if k in state_keys
            }

            logger.info(f"Active cameras: {list(active_cameras.keys())}")
            logger.info(f"Active joints: {list(active_joints.keys())}")

            # 4. Store config
            task_instruction = getattr(request, "task_instruction", "")
            self._inference_config = InferenceConfig(
                model_path=model_path,
                embodiment_tag=embodiment_tag,
                camera_topic_map=active_cameras,
                joint_topic_map=active_joints,
                task_instruction=task_instruction,
            )

            # 5. Initialize observation dict with modality keys
            self._latest_observations = {
                "video": {key: None for key in active_cameras},
                "state": {key: None for key in active_joints},
                "language": {},
                "timestamp": None,
            }

            # 6. Subscribe to active topics only
            if active_cameras or active_joints:
                self._setup_ros2_subscribers(active_cameras, active_joints)

            # 7. Store action keys and transition state
            self._action_keys = action_keys
            self._inference_running = True
            executor.state = ExecutorState.INFERENCE

            return executor._create_response(
                executor._infer_service,
                success=True,
                message="GR00T inference started",
                action_keys=list(self._action_keys),
            )

        except Exception as e:
            logger.error(f"Failed to start inference: {e}", exc_info=True)
            return executor._create_response(
                executor._infer_service,
                success=False,
                message=f"Failed to start inference: {e}",
            )

    def _load_policy(self, model_path: str, embodiment_tag: str) -> Optional[Any]:
        """Load a GR00T policy from checkpoint."""
        try:
            from gr00t.data.embodiment_tags import EmbodimentTag
            from gr00t.policy.gr00t_policy import Gr00tPolicy

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

    def _get_modality_config(self, embodiment_tag: str) -> dict:
        """Get modality config for the loaded embodiment."""
        try:
            from gr00t.data.embodiment_tags import EmbodimentTag

            try:
                emb_tag = EmbodimentTag(embodiment_tag)
            except ValueError:
                emb_tag = EmbodimentTag.NEW_EMBODIMENT

            if self._loaded_policy is not None:
                try:
                    all_configs = self._loaded_policy.processor.get_modality_configs()
                    if emb_tag.value in all_configs:
                        config = all_configs[emb_tag.value]
                        logger.info(
                            f"Retrieved modality config from loaded policy for {emb_tag.value}"
                        )
                        return config
                except Exception as e:
                    logger.debug(f"Could not read from policy processor: {e}")

            try:
                from gr00t.configs.data.embodiment_configs import MODALITY_CONFIGS

                if emb_tag.value in MODALITY_CONFIGS:
                    config = MODALITY_CONFIGS[emb_tag.value]
                    logger.info(
                        f"Retrieved modality config from registry for {emb_tag.value}"
                    )
                    return config
            except Exception as e:
                logger.debug(f"Could not read from registry: {e}")

            logger.warning(
                f"No modality config found for {emb_tag.value}. Using empty config."
            )
            return {}

        except Exception as e:
            logger.warning(f"Failed to get modality config: {e}. Using empty config.")
            return {}

    def _setup_ros2_subscribers(
        self, active_cameras: dict, active_joints: dict
    ) -> None:
        """Setup ROS2 subscribers based on modality key -> topic mapping."""
        try:
            config = self._executor.config
            common_kwargs = {
                "node_name": config.node_name,
                "namespace": config.namespace,
                "domain_id": config.domain_id,
                "router_ip": config.router_ip,
                "router_port": config.router_port,
            }

            for modality_key, topic_path in active_cameras.items():

                def make_image_callback(key):
                    def callback(msg):
                        self._on_image_received(key, msg)
                    return callback

                sub = ROS2Subscriber(
                    topic=topic_path,
                    msg_type="sensor_msgs/msg/CompressedImage",
                    callback=make_image_callback(modality_key),
                    **common_kwargs,
                )
                self._ros2_subscribers.append(sub)
                logger.info(f"Camera subscribed: {modality_key} -> {topic_path}")

            for modality_key, topic_path in active_joints.items():

                def make_joint_callback(key):
                    def callback(msg):
                        self._on_joint_state_received(key, msg)
                    return callback

                sub = ROS2Subscriber(
                    topic=topic_path,
                    msg_type="sensor_msgs/msg/JointState",
                    callback=make_joint_callback(modality_key),
                    **common_kwargs,
                )
                self._ros2_subscribers.append(sub)
                logger.info(f"Joint subscribed: {modality_key} -> {topic_path}")

            logger.info(f"Setup {len(self._ros2_subscribers)} ROS2 subscribers")

        except Exception as e:
            logger.error(f"Failed to setup ROS2 subscribers: {e}", exc_info=True)

    def _on_image_received(self, modality_key: str, msg: Any) -> None:
        """Store camera image by modality key."""
        try:
            import cv2

            image_data = np.frombuffer(bytes(msg.data), dtype=np.uint8)
            image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)

            if image is not None:
                target_size = (224, 224)
                if image.shape[:2] != target_size:
                    image = cv2.resize(image, (target_size[1], target_size[0]))
                image = image[np.newaxis, np.newaxis, ...]  # (1,1,H,W,C)
                self._latest_observations["video"][modality_key] = image
                self._latest_observations["timestamp"] = time.time()
        except Exception as e:
            logger.debug(f"Error decoding image for {modality_key}: {e}")

    def _on_joint_state_received(self, modality_key: str, msg: Any) -> None:
        """Store joint state by modality key as (1,1,D) array."""
        try:
            positions = np.array(msg.position, dtype=np.float32)
            self._latest_observations["state"][modality_key] = (
                positions[np.newaxis, np.newaxis, :]
            )
            self._latest_observations["timestamp"] = time.time()
        except Exception as e:
            logger.debug(f"Error processing joint state for {modality_key}: {e}")

    def handle_get_action_chunk(self, request: Any) -> Any:
        """Handle get_action_chunk service — runs inference and returns full chunk."""
        from executor import ExecutorState

        executor = self._executor
        if executor.state != ExecutorState.INFERENCE or self._loaded_policy is None:
            return executor._create_response(
                executor._get_action_chunk_service,
                success=False,
                message="Not in inference mode",
            )

        try:
            obs = self._latest_observations

            if obs["timestamp"] is None or time.time() - obs["timestamp"] > 2.0:
                return executor._create_response(
                    executor._get_action_chunk_service,
                    success=False,
                    message="No recent observations",
                )

            for key in obs["video"]:
                if obs["video"][key] is None:
                    return executor._create_response(
                        executor._get_action_chunk_service,
                        success=False,
                        message=f"Missing video observation: {key}",
                    )
            for key in obs["state"]:
                if obs["state"][key] is None:
                    return executor._create_response(
                        executor._get_action_chunk_service,
                        success=False,
                        message=f"Missing state observation: {key}",
                    )

            task = getattr(request, "task_instruction", "") or (
                self._inference_config.task_instruction
                if self._inference_config
                else ""
            )
            if task:
                obs["language"]["annotation.human.task_description"] = [[task]]

            observation = {
                "video": obs["video"],
                "state": obs["state"],
                "language": obs["language"],
            }

            logger.debug("Running inference...")
            action, info = self._loaded_policy.get_action(observation)

            chunks = []
            for key in self._action_keys:
                if key in action and isinstance(action[key], np.ndarray):
                    chunks.append(action[key][0])  # Remove batch dim

            if chunks:
                chunk = np.concatenate(chunks, axis=1)  # (T, D_total)
                t_size, d_size = chunk.shape
                logger.info(f"Action chunk generated: T={t_size}, D={d_size}")
                return executor._create_response(
                    executor._get_action_chunk_service,
                    success=True,
                    message="",
                    action_chunk=np.asarray(chunk.flatten(), dtype=np.float64),
                    chunk_size=t_size,
                    action_dim=d_size,
                )

            return executor._create_response(
                executor._get_action_chunk_service,
                success=False,
                message="No action output from policy",
            )

        except Exception as e:
            logger.error(f"Inference failed: {e}", exc_info=True)
            return executor._create_response(
                executor._get_action_chunk_service,
                success=False,
                message=f"Inference failed: {e}",
            )

    def cleanup(self) -> None:
        """Cleanup inference resources."""
        self._inference_running = False

        for sub in self._ros2_subscribers:
            try:
                sub.close()
            except Exception:
                pass
        self._ros2_subscribers = []

        if self._loaded_policy is not None:
            del self._loaded_policy
            self._loaded_policy = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        self._action_keys = []
