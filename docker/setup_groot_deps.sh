#!/bin/bash
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
# Setup script for GR00T N1 training dependencies.
# Run this inside the physical_ai_server container after recreation.
#
# Usage:
#   bash /root/ros2_ws/src/physical_ai_tools/docker/setup_groot_deps.sh

set -e

GROOT_DIR="/root/ros2_ws/src/physical_ai_tools/Isaac-GR00T"
LEROBOT_DIR="/root/ros2_ws/src/physical_ai_tools/lerobot"

echo "=============================="
echo " GR00T N1 Dependency Setup"
echo "=============================="

# Install Isaac-GR00T as editable package with train extras
echo "[1/4] Installing Isaac-GR00T..."
pip install -e "${GROOT_DIR}" --ignore-installed cryptography

# Install LeRobot as editable package
echo "[2/4] Installing LeRobot..."
pip install -e "${LEROBOT_DIR}"

# Install additional dependencies
echo "[3/4] Installing additional packages..."
pip install \
    peft==0.19.0 \
    deepspeed==0.17.6 \
    albumentations==2.0.8 \
    tyro==0.9.17

# Install flash-attn (requires CUDA, takes a few minutes)
echo "[4/4] Installing flash-attn (this may take a while)..."
pip install flash-attn==2.8.3 --no-build-isolation

echo ""
echo "=============================="
echo " Setup complete!"
echo "=============================="
