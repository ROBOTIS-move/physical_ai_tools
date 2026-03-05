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
    "joint_states": {},
    "timestamp": None,
}
_action_keys: list = []


def load_policy(server, request) -> dict:
    """Load LeRobot policy and setup subscribers. Returns dict for service response."""
    global _loaded_model, _inference_config, _latest_observations, _action_keys

    model_path = getattr(request, "model_path", "")
    if not model_path:
        return {"success": False, "message": "Missing required parameter: model_path"}

    try:
        logger.info(f"Loading model from: {model_path}")
        _loaded_model = _load_lerobot_policy(model_path)

        if _loaded_model is None:
            return {"success": False, "message": "Failed to load model"}

        # Parse topic maps from request ("name:topic" format, same as gr00t)
        camera_topic_map = _parse_topic_map(getattr(request, "camera_topic_map", []))
        joint_topic_map = _parse_topic_map(getattr(request, "joint_topic_map", []))

        logger.info(f"Camera topic map: {camera_topic_map}")
        logger.info(f"Joint topic map: {joint_topic_map}")

        # Extract action_keys: use joint_topic_map keys as action keys
        # (LeRobot outputs a single concatenated action vector ordered by these groups)
        action_keys = list(joint_topic_map.keys())

        _inference_config = {
            "model_path": model_path,
            "camera_topic_map": camera_topic_map,
            "joint_topic_map": joint_topic_map,
            "joint_modality_keys": action_keys,
        }

        _latest_observations = {
            "images": {},
            "joint_states": {},
            "timestamp": None,
        }

        _action_keys = action_keys

        if camera_topic_map or joint_topic_map:
            _setup_ros2_subscribers(server, camera_topic_map, joint_topic_map)

        return {"success": True, "message": "LeRobot inference started", "action_keys": action_keys}

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

        # Concatenate joint states from all groups in joint_topic_map order
        joint_modality_keys = _inference_config.get("joint_modality_keys", []) if _inference_config else []
        state_parts = []
        for modality_key in joint_modality_keys:
            joint_data = obs["joint_states"].get(modality_key)
            if joint_data is None:
                return {"success": False, "message": f"Missing joint state: {modality_key}"}
            state_parts.append(joint_data["positions"])

        if state_parts:
            all_positions = []
            for part in state_parts:
                all_positions.extend(part)
            observation["observation.state"] = torch.tensor(
                all_positions, dtype=torch.float32
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
    global _loaded_model, _inference_config, _action_keys

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
    _action_keys = []


# ------------------------------------------------------------------ #
# Internal helpers
# ------------------------------------------------------------------ #

def _parse_topic_map(topic_map_list: list) -> dict:
    """Parse 'name:topic' string list into {name: topic} dict."""
    result = {}
    for entry in topic_map_list:
        if ":" in entry:
            name, topic = entry.split(":", 1)
            result[name.strip()] = topic.strip()
    return result


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


def _setup_ros2_subscribers(server, active_cameras: dict, active_joints: dict) -> None:
    """Setup ROS2 subscribers based on modality key -> topic mapping."""
    global _ros2_subscribers

    common_kwargs = {
        "router_ip": server._router_ip,
        "router_port": server._router_port,
    }
    if server._domain_id is not None:
        common_kwargs["domain_id"] = server._domain_id
    common_kwargs["node_name"] = server._node_name
    common_kwargs["namespace"] = server._namespace

    for cam_name, topic_path in active_cameras.items():
        def make_image_callback(name):
            def callback(msg):
                _on_image_received(name, msg)
            return callback

        sub = ROS2Subscriber(
            topic=topic_path,
            msg_type="sensor_msgs/msg/CompressedImage",
            callback=make_image_callback(cam_name),
            **common_kwargs,
        )
        _ros2_subscribers.append(sub)
        logger.info(f"Camera subscribed: {cam_name} -> {topic_path}")

    for modality_key, topic_path in active_joints.items():
        def make_joint_callback(key):
            def callback(msg):
                _on_joint_state_received(key, msg)
            return callback

        sub = ROS2Subscriber(
            topic=topic_path,
            msg_type="sensor_msgs/msg/JointState",
            callback=make_joint_callback(modality_key),
            **common_kwargs,
        )
        _ros2_subscribers.append(sub)
        logger.info(f"Joint subscribed: {modality_key} -> {topic_path}")

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


def _on_joint_state_received(modality_key: str, msg) -> None:
    """Callback for joint state received, stored by modality key."""
    try:
        joint_data = {
            "names": list(msg.name),
            "positions": list(msg.position),
            "velocities": list(msg.velocity) if msg.velocity else [],
            "efforts": list(msg.effort) if msg.effort else [],
        }
        _latest_observations["joint_states"][modality_key] = joint_data
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
