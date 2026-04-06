// Copyright 2025 ROBOTIS CO., LTD.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// Author: Kiwoong Park

/**
 * Default paths configuration for file browser modals
 */

// Environment-based path configuration
const BASE_WORKSPACE_PATH =
  process.env.REACT_APP_BASE_WORKSPACE_PATH || '/root/ros2_ws/src/physical_ai_tools';

const LEROBOT_OUTPUTS_PATH =
  process.env.REACT_APP_LEROBOT_OUTPUTS_PATH || `${BASE_WORKSPACE_PATH}/lerobot/outputs`;

const DOT_CACHE_PATH = '/root/.cache';

export const DEFAULT_PATHS = {
  // Base paths
  BASE_WORKSPACE: BASE_WORKSPACE_PATH,
  LEROBOT_OUTPUTS: LEROBOT_OUTPUTS_PATH,

  // File browser defaults
  POLICY_MODEL_PATH: `${LEROBOT_OUTPUTS_PATH}/train/`,
  DATASET_PATH: `${DOT_CACHE_PATH}/huggingface/lerobot/`,
  ROSBAG2_PATH: '/workspace/rosbag2/',
  BT_TREES_PATH: `${BASE_WORKSPACE_PATH}/physical_ai_bt/trees/`,
  // Default destination for HuggingFace model downloads on the robot.
  HF_MODEL_DOWNLOAD_PATH:
    '/root/ros2_ws/src/physical_ai_tools/third_party/groot/workspace/checkpoints',
};

// Built-in HuggingFace endpoints shown as quick-pick options. Users can also
// add ad-hoc URLs via the "Custom…" entry in the dropdown; whichever ones they
// register tokens for are persisted on the server side in
// /root/.cache/huggingface/physical_ai_endpoints.json.
export const HF_ENDPOINT_PRESETS = [
  { url: 'https://huggingface.co', label: 'Hugging Face' },
  { url: 'http://192.168.60.152:1000', label: 'Internal hub' },
];

/**
 * Target file names for different types of file selection
 */
export const TARGET_FILES = {
  POLICY_MODEL: 'model.safetensors',
  TRAIN_CONFIG: 'train_config.json',
};

export const TARGET_FOLDERS = {
  DATASET_METADATA: 'meta',
  DATASET_VIDEO: 'videos',
  DATASET_DATA: 'data',
};
