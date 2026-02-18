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

# physical_ai_tools custom message/service definitions
# Separated from zenoh_ros2_sdk to keep it a generic ROS2 library
#
# These definitions are embedded as strings for use with zenoh_ros2_sdk's
# request_definition/response_definition/msg_definition parameters.
# This avoids dependency on physical_ai_interfaces ROS2 package.
#
# IMPORTANT: These MUST match the .srv/.msg files in physical_ai_interfaces/
# exactly (field names, types, order) for CDR serialization and type hash
# compatibility with physical_ai_server (which uses native ROS2 + rmw_zenoh).

# ============================================================
# Service Definitions (srv)
# ============================================================

# --- TrainModel (physical_ai_interfaces/srv/TrainModel.srv) ---
TRAIN_MODEL_REQUEST_DEF = """\
string policy_type
string dataset_path
string output_dir
int32 steps
int32 batch_size
float32 learning_rate
int32 eval_freq
int32 log_freq
int32 save_freq
string wandb_project
bool push_to_hub
"""

TRAIN_MODEL_RESPONSE_DEF = """\
bool success
string message
string job_id
"""

# --- StartInference (physical_ai_interfaces/srv/StartInference.srv) ---
START_INFERENCE_REQUEST_DEF = """\
string model_path
string embodiment_tag
string[] camera_topic_map
string[] joint_topic_map
string task_instruction
"""

START_INFERENCE_RESPONSE_DEF = """\
bool success
string message
string[] action_keys
"""

# --- GetActionChunk (physical_ai_interfaces/srv/GetActionChunk.srv) ---
GET_ACTION_CHUNK_REQUEST_DEF = """\
string task_instruction
"""

GET_ACTION_CHUNK_RESPONSE_DEF = """\
bool success
string message
float64[] action_chunk
int32 chunk_size
int32 action_dim
"""

# --- StopTraining (physical_ai_interfaces/srv/StopTraining.srv) ---
# Request has no fields (empty request). Comment-only string keeps
# register_message_type from trying auto-load (physical_ai_interfaces
# is not in the message registry).
STOP_TRAINING_REQUEST_DEF = "# empty"

STOP_TRAINING_RESPONSE_DEF = """\
bool success
string message
"""

# --- TrainingStatus (physical_ai_interfaces/srv/TrainingStatus.srv) ---
# Request has no fields (empty request)
TRAINING_STATUS_REQUEST_DEF = "# empty"

TRAINING_STATUS_RESPONSE_DEF = """\
string state
int32 step
int32 total_steps
float32 loss
float32 learning_rate
float32 gradient_norm
float32 elapsed_seconds
float32 eta_seconds
string job_id
string message
"""

# ============================================================
# Message Definitions (msg)
# ============================================================

# --- TrainingProgress (physical_ai_interfaces/msg/TrainingProgress.msg) ---
TRAINING_PROGRESS_DEF = """\
int32 step
int32 total_steps
float64 epoch
float64 loss
float64 learning_rate
float64 gradient_norm
float64 samples_per_second
float64 elapsed_seconds
float64 eta_seconds
string state
"""

ACTION_OUTPUT_DEF = """\
float64[] joint_positions
float64 gripper
float64 timestamp
"""
