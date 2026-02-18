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
GR00T Inference - Inference logic for GR00T N1.6.

Module-level functions with two inference modes:
  1. Service response: get_action_chunk() returns dict -> physical_ai_server dispatches
  2. Direct publish: execute_action_directly() -> RobotClient publishes to robot

Both modes share the same load_policy() / cleanup_inference() lifecycle.
"""
from __future__ import annotations

import time
from typing import Any, Optional

import numpy as np
import torch

from zenoh_ros2_sdk import ROS2Subscriber

import logging
logger = logging.getLogger("groot_inference")

# Module-level inference state
_loaded_policy: Optional[Any] = None
_inference_config: Optional[dict] = None
_ros2_subscribers: list = []
_latest_observations: dict = {
    "video": {},
    "state": {},
    "language": {},
    "timestamp": None,
}
_action_keys: list = []


def load_policy(server, request) -> dict:
    """Load GR00T policy and setup subscribers. Returns dict for service response."""
    global _loaded_policy, _inference_config, _latest_observations, _action_keys

    model_path = getattr(request, "model_path", "")
    if not model_path:
        return {"success": False, "message": "Missing required parameter: model_path"}

    try:
        # 1. Load model
        embodiment_tag = getattr(request, "embodiment_tag", "new_embodiment")
        if not embodiment_tag:
            embodiment_tag = "new_embodiment"

        logger.info(f"Loading GR00T policy from: {model_path}")
        _loaded_policy = _load_groot_policy(model_path, embodiment_tag)

        if _loaded_policy is None:
            return {"success": False, "message": "Failed to load GR00T policy"}

        # 2. Read modality config directly from loaded policy (already resolved during loading)
        modality_config = getattr(_loaded_policy, "modality_configs", None)
        if modality_config is None:
            modality_config = _get_modality_config(_loaded_policy, embodiment_tag)
        video_keys = modality_config["video"].modality_keys if "video" in modality_config else []
        state_keys = modality_config["state"].modality_keys if "state" in modality_config else []
        action_keys = modality_config["action"].modality_keys if "action" in modality_config else []

        logger.info(f"Modality config - video: {video_keys}, state: {state_keys}, action: {action_keys}")

        # 3. Parse topic maps from request
        camera_topic_map = _parse_topic_map(getattr(request, "camera_topic_map", []))
        joint_topic_map = _parse_topic_map(getattr(request, "joint_topic_map", []))

        active_cameras = {k: v for k, v in camera_topic_map.items() if k in video_keys}
        active_joints = {k: v for k, v in joint_topic_map.items() if k in state_keys}

        logger.info(f"Active cameras: {list(active_cameras.keys())}")
        logger.info(f"Active joints: {list(active_joints.keys())}")

        # 4. Store config
        task_instruction = getattr(request, "task_instruction", "")
        _inference_config = {
            "model_path": model_path,
            "embodiment_tag": embodiment_tag,
            "camera_topic_map": active_cameras,
            "joint_topic_map": active_joints,
            "task_instruction": task_instruction,
        }

        # 5. Initialize observation dict
        _latest_observations = {
            "video": {key: None for key in active_cameras},
            "state": {key: None for key in active_joints},
            "language": {},
            "timestamp": None,
        }

        # 6. Subscribe to active topics
        if active_cameras or active_joints:
            _setup_ros2_subscribers(server, active_cameras, active_joints)

        # 7. Store action keys
        _action_keys = action_keys

        return {"success": True, "message": "GR00T inference started", "action_keys": list(action_keys)}

    except Exception as e:
        logger.error(f"Failed to start inference: {e}", exc_info=True)
        return {"success": False, "message": f"Failed to start inference: {e}"}


def get_action_chunk(server, request) -> dict:
    """Run inference and return action chunk as dict (service response mode)."""
    if _loaded_policy is None:
        return {"success": False, "message": "Not in inference mode"}

    try:
        obs = _latest_observations

        if obs["timestamp"] is None or time.time() - obs["timestamp"] > 2.0:
            return {"success": False, "message": "No recent observations"}

        for key in obs["video"]:
            if obs["video"][key] is None:
                return {"success": False, "message": f"Missing video observation: {key}"}
        for key in obs["state"]:
            if obs["state"][key] is None:
                return {"success": False, "message": f"Missing state observation: {key}"}

        # Language instruction
        task = getattr(request, "task_instruction", "") or (
            _inference_config.get("task_instruction", "") if _inference_config else ""
        )
        if task:
            obs["language"]["annotation.human.task_description"] = [[task]]

        observation = {
            "video": obs["video"],
            "state": obs["state"],
            "language": obs["language"],
        }

        logger.debug("Running inference...")
        action, info = _loaded_policy.get_action(observation)

        chunks = []
        for key in _action_keys:
            if key in action and isinstance(action[key], np.ndarray):
                chunks.append(action[key][0])  # Remove batch dim

        if chunks:
            chunk = np.concatenate(chunks, axis=1)  # (T, D_total)
            T, D = chunk.shape
            logger.info(f"Action chunk generated: T={T}, D={D}")
            return {
                "success": True,
                "action_chunk": np.asarray(chunk.flatten(), dtype=np.float64).tolist(),
                "chunk_size": T,
                "action_dim": D,
            }

        return {"success": False, "message": "No action output from policy"}

    except Exception as e:
        logger.error(f"Inference failed: {e}", exc_info=True)
        return {"success": False, "message": f"Inference failed: {e}"}


def cleanup_inference() -> None:
    """Cleanup inference resources."""
    global _loaded_policy, _inference_config, _action_keys

    for sub in _ros2_subscribers:
        try:
            sub.close()
        except Exception:
            pass
    _ros2_subscribers.clear()

    if _loaded_policy is not None:
        del _loaded_policy
        _loaded_policy = None
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


def _load_groot_policy(model_path: str, embodiment_tag: str):
    """Load a GR00T policy from checkpoint.

    If the requested embodiment_tag is not available in the model's processor,
    falls back to the first available embodiment config.
    """
    try:
        from gr00t.data.embodiment_tags import EmbodimentTag
        from gr00t.policy.gr00t_policy import Gr00tPolicy

        try:
            emb_tag = EmbodimentTag(embodiment_tag)
        except ValueError:
            logger.warning(f"Unknown embodiment tag '{embodiment_tag}', using NEW_EMBODIMENT")
            emb_tag = EmbodimentTag.NEW_EMBODIMENT

        device = "cuda" if torch.cuda.is_available() else "cpu"

        # Try loading with the requested embodiment tag first
        try:
            policy = Gr00tPolicy(
                embodiment_tag=emb_tag,
                model_path=model_path,
                device=device,
            )
            logger.info(f"GR00T policy loaded successfully on {device} with embodiment '{emb_tag.value}'")
            return policy
        except KeyError:
            # Embodiment tag not in model's processor configs - find available ones
            from transformers import AutoProcessor
            import gr00t.model  # noqa: F401 - register custom models
            proc = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
            available = list(proc.get_modality_configs().keys())
            logger.warning(
                f"Embodiment '{emb_tag.value}' not in model configs. "
                f"Available: {available}"
            )
            if not available:
                raise ValueError("No embodiment configs found in model")

            # Fall back to first available embodiment
            fallback_tag_str = available[0]
            try:
                fallback_tag = EmbodimentTag(fallback_tag_str)
            except ValueError:
                fallback_tag = EmbodimentTag.NEW_EMBODIMENT

            logger.info(f"Falling back to embodiment '{fallback_tag_str}'")
            policy = Gr00tPolicy(
                embodiment_tag=fallback_tag,
                model_path=model_path,
                device=device,
            )
            logger.info(f"GR00T policy loaded on {device} with fallback embodiment '{fallback_tag.value}'")
            return policy

    except Exception as e:
        logger.error(f"Failed to load GR00T policy: {e}", exc_info=True)
        return None


def _get_modality_config(policy, embodiment_tag: str) -> dict:
    """Get modality config for the loaded embodiment."""
    try:
        from gr00t.data.embodiment_tags import EmbodimentTag

        try:
            emb_tag = EmbodimentTag(embodiment_tag)
        except ValueError:
            emb_tag = EmbodimentTag.NEW_EMBODIMENT

        # Try from loaded policy
        try:
            all_configs = policy.processor.get_modality_configs()
            if emb_tag.value in all_configs:
                return all_configs[emb_tag.value]
        except Exception as e:
            logger.debug(f"Could not read from policy processor: {e}")

        # Try from registry
        try:
            from gr00t.configs.data.embodiment_configs import MODALITY_CONFIGS
            if emb_tag.value in MODALITY_CONFIGS:
                return MODALITY_CONFIGS[emb_tag.value]
        except Exception as e:
            logger.debug(f"Could not read from registry: {e}")

        logger.warning(f"No modality config found for {emb_tag.value}. Using empty config.")
        return {}

    except Exception as e:
        logger.warning(f"Failed to get modality config: {e}. Using empty config.")
        return {}


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

    for modality_key, topic_path in active_cameras.items():
        def make_image_callback(key):
            def callback(msg):
                _on_image_received(key, msg)
            return callback

        sub = ROS2Subscriber(
            topic=topic_path,
            msg_type="sensor_msgs/msg/CompressedImage",
            callback=make_image_callback(modality_key),
            **common_kwargs,
        )
        _ros2_subscribers.append(sub)
        logger.info(f"Camera subscribed: {modality_key} -> {topic_path}")

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


def _on_image_received(modality_key: str, msg) -> None:
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
            _latest_observations["video"][modality_key] = image
            _latest_observations["timestamp"] = time.time()
    except Exception as e:
        logger.debug(f"Error decoding image for {modality_key}: {e}")


def _on_joint_state_received(modality_key: str, msg) -> None:
    """Store joint state by modality key as (1,1,D) array."""
    try:
        positions = np.array(msg.position, dtype=np.float32)
        _latest_observations["state"][modality_key] = positions[np.newaxis, np.newaxis, :]
        _latest_observations["timestamp"] = time.time()
    except Exception as e:
        logger.debug(f"Error processing joint state for {modality_key}: {e}")
