"""
LeRobot Inference Handler - Inference logic for LeRobot.

Separated from executor.py for clean code organization.
Inference-specific methods: handle_infer, load_policy, setup_ros2_subscribers,
inference_loop, predict_from_observations, publish_action.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import numpy as np
import torch

from zenoh_ros2_sdk import (
    ROS2Subscriber,
    get_logger,
)

if TYPE_CHECKING:
    from executor import LeRobotExecutor

logger = get_logger("lerobot_inference")


class InferenceHandler:
    """Handles LeRobot inference requests.

    Takes a reference to the parent executor to access shared state
    (state machine, config, services).
    """

    def __init__(self, executor: LeRobotExecutor):
        self._executor = executor

        # Inference-specific state
        self._loaded_model: Optional[Any] = None
        self._inference_running = False
        self._inference_config = None
        self._inference_thread: Optional[threading.Thread] = None
        self._ros2_subscribers: list = []
        self._latest_observations: dict = {
            "images": {},
            "joint_state": None,
            "timestamp": None,
        }

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
            logger.info(f"Loading model from: {model_path}")
            self._loaded_model = self._load_policy(model_path)

            if self._loaded_model is None:
                return executor._create_response(
                    executor._infer_service,
                    success=False,
                    message="Failed to load model",
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
            executor.state = ExecutorState.INFERENCE

            self._inference_thread = threading.Thread(
                target=self._inference_loop,
                args=(inference_freq,),
                daemon=True,
            )
            self._inference_thread.start()

            return executor._create_response(
                executor._infer_service,
                success=True,
                message="Inference started",
            )

        except Exception as e:
            logger.error(f"Failed to start inference: {e}", exc_info=True)
            return executor._create_response(
                executor._infer_service,
                success=False,
                message=f"Failed to start inference: {e}",
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
            config = self._executor.config
            common_kwargs = {
                "node_name": config.node_name,
                "namespace": config.namespace,
                "domain_id": config.domain_id,
                "router_ip": config.router_ip,
                "router_port": config.router_port,
            }

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
                    **common_kwargs,
                )
                self._ros2_subscribers.append(sub)

            # Subscribe to joint state topic
            if joint_topic:
                logger.info(f"Subscribing to joint state topic: {joint_topic}")
                sub = ROS2Subscriber(
                    topic=joint_topic,
                    msg_type="sensor_msgs/msg/JointState",
                    callback=self._on_joint_state_received,
                    **common_kwargs,
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
        from executor import ExecutorState

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
        logger.info(
            f"Inference loop stopped. Total actions published: {action_count}"
        )
        self._executor.state = ExecutorState.IDLE

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
                    action_values[:-1]
                    if len(action_values) > 1
                    else action_values
                ),
                "gripper": (
                    action_values[-1] if len(action_values) > 1 else 0.0
                ),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            return action

        except Exception as e:
            logger.debug(f"Error in real inference: {e}")
            return None

    @staticmethod
    def _preprocess_image(image: np.ndarray) -> torch.Tensor:
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
        executor = self._executor
        if executor._action_publisher is None:
            return

        try:
            joint_positions = action.get("joint_positions", [])
            if isinstance(joint_positions, list):
                joint_positions = np.array(joint_positions, dtype=np.float64)

            executor._action_publisher.publish(
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

    def cleanup(self) -> None:
        """Cleanup inference resources."""
        self._inference_running = False

        if self._inference_thread and self._inference_thread.is_alive():
            self._inference_thread.join(timeout=5.0)

        self._cleanup_ros2_subscribers()

        if self._loaded_model is not None:
            del self._loaded_model
            self._loaded_model = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
