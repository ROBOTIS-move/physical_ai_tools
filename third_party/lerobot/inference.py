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
# Author: Dongyun Kim

"""
LeRobot Inference - Inference logic for LeRobot.

Module-level functions with two inference modes:
  1. Service response: get_action_chunk() returns dict -> physical_ai_server dispatches
  2. Direct publish: execute_action_directly() -> RobotClient publishes to robot

Both modes share the same load_policy() / cleanup_inference() lifecycle.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch

from zenoh_ros2_sdk import ROS2Subscriber

import logging
logger = logging.getLogger("lerobot_inference")

# Module-level inference state
_loaded_model: Optional[Any] = None
_inference_config: Optional[dict] = None
_ros2_subscribers: list = []
_latest_observations: dict = {
    "images": {},
    "joint_state": None,
    "timestamp": None,
}


def load_policy(server, request) -> dict:
    """Load LeRobot policy and setup subscribers. Returns dict for service response."""
    global _loaded_model, _inference_config, _latest_observations

    model_path = getattr(request, "model_path", "")
    if not model_path:
        return {"success": False, "message": "Missing required parameter: model_path"}

    try:
        logger.info(f"Loading model from: {model_path}")
        _loaded_model = _load_lerobot_policy(model_path)

        if _loaded_model is None:
            return {"success": False, "message": "Failed to load model"}

        # Parse request parameters
        camera_topics = getattr(request, "camera_topics", None)
        if not camera_topics:
            camera_topics = getattr(request, "image_topics", [])
        joint_topic = getattr(request, "joint_topic", None)
        if not joint_topic:
            joint_topic = getattr(request, "joint_state_topic", "")

        _inference_config = {
            "model_path": model_path,
            "camera_topics": camera_topics,
            "joint_topic": joint_topic,
        }

        _latest_observations = {
            "images": {},
            "joint_state": None,
            "timestamp": None,
        }

        if camera_topics or joint_topic:
            _setup_ros2_subscribers(server, camera_topics, joint_topic)

        return {"success": True, "message": "LeRobot inference started", "action_keys": []}

    except Exception as e:
        logger.error(f"Failed to start inference: {e}", exc_info=True)
        return {"success": False, "message": f"Failed to start inference: {e}"}


def get_action_chunk(server, request) -> dict:
    """Run inference and return action chunk as dict (service response mode)."""
    if _loaded_model is None:
        return {"success": False, "message": "Not in inference mode"}

    try:
        obs = _latest_observations

        if obs["timestamp"] is None or time.time() - obs["timestamp"] > 2.0:
            return {"success": False, "message": "No recent observations"}

        # Build observation tensor
        observation = {}

        for cam_name, image in obs["images"].items():
            image_tensor = _preprocess_image(image)
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
                    batch[key] = value.to(_loaded_model.device)

            action_tensor = _loaded_model.select_action(batch)

            if isinstance(action_tensor, torch.Tensor):
                action_array = action_tensor.cpu().numpy()
            else:
                action_array = np.array(action_tensor)

        # action_array shape: (T, D) or (D,)
        if len(action_array.shape) == 1:
            action_array = action_array[np.newaxis, :]  # (1, D)

        T, D = action_array.shape
        logger.info(f"Action chunk generated: T={T}, D={D}")

        return {
            "success": True,
            "action_chunk": action_array.flatten().astype(np.float64).tolist(),
            "chunk_size": T,
            "action_dim": D,
        }

    except Exception as e:
        logger.error(f"Inference failed: {e}", exc_info=True)
        return {"success": False, "message": f"Inference failed: {e}"}


def cleanup_inference() -> None:
    """Cleanup inference resources."""
    global _loaded_model, _inference_config

    for sub in _ros2_subscribers:
        try:
            sub.close()
        except Exception:
            pass
    _ros2_subscribers.clear()

    if _loaded_model is not None:
        del _loaded_model
        _loaded_model = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    _inference_config = None


# ------------------------------------------------------------------ #
# Internal helpers
# ------------------------------------------------------------------ #

def _load_lerobot_policy(model_path: str):
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


def _setup_ros2_subscribers(server, camera_topics: list, joint_topic: str) -> None:
    """Setup ROS2 topic subscribers for sensor data."""
    global _ros2_subscribers

    common_kwargs = {
        "router_ip": server._router_ip,
        "router_port": server._router_port,
    }
    if server._domain_id is not None:
        common_kwargs["domain_id"] = server._domain_id
    common_kwargs["node_name"] = server._node_name
    common_kwargs["namespace"] = server._namespace

    for cam_config in camera_topics:
        topic = cam_config.get("topic") if isinstance(cam_config, dict) else cam_config
        name = cam_config.get("name", topic.split("/")[-2]) if isinstance(cam_config, dict) else topic.split("/")[-2]

        if not topic:
            continue

        def make_image_callback(cam_name):
            def callback(msg):
                _on_image_received(cam_name, msg)
            return callback

        sub = ROS2Subscriber(
            topic=topic,
            msg_type="sensor_msgs/msg/CompressedImage",
            callback=make_image_callback(name),
            **common_kwargs,
        )
        _ros2_subscribers.append(sub)
        logger.info(f"Camera subscribed: {name} -> {topic}")

    if joint_topic:
        sub = ROS2Subscriber(
            topic=joint_topic,
            msg_type="sensor_msgs/msg/JointState",
            callback=_on_joint_state_received,
            **common_kwargs,
        )
        _ros2_subscribers.append(sub)
        logger.info(f"Joint subscribed: {joint_topic}")

    logger.info(f"Setup {len(_ros2_subscribers)} ROS2 subscribers")


def _on_image_received(camera_name: str, msg) -> None:
    """Callback for camera image received."""
    try:
        import cv2
        image_data = np.frombuffer(bytes(msg.data), dtype=np.uint8)
        image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)

        if image is not None:
            _latest_observations["images"][camera_name] = image
            _latest_observations["timestamp"] = time.time()
    except Exception as e:
        logger.debug(f"Error decoding image: {e}")


def _on_joint_state_received(msg) -> None:
    """Callback for joint state received."""
    try:
        joint_data = {
            "names": list(msg.name),
            "positions": list(msg.position),
            "velocities": list(msg.velocity) if msg.velocity else [],
            "efforts": list(msg.effort) if msg.effort else [],
        }
        _latest_observations["joint_state"] = joint_data
        _latest_observations["timestamp"] = time.time()
    except Exception as e:
        logger.debug(f"Error processing joint state: {e}")


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
