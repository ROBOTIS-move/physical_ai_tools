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
# Author: Kiwoong Park

"""
HDF5 Topic Publisher Node.

Replays a recorded HDF5 demo file by publishing camera images and joint states
to ROS2 topics at the original recording rate. Useful for testing the inference
pipeline without a physical robot.

HDF5 structure expected (evButtonPush v02 format):
  data/demo_0/
    obs/
      cam_wrist    (T, H, W, 3)
      cam_top      (T, H, W, 3)
      cam_belly    (T, H, W, 3)
      joint_pos    (T, D)        -- first 7 DOF used
    actions        (T, 7)

Usage:
    ros2 run test_utils hdf5_topic_publisher.py \\
        --ros-args -p hdf5_path:=/workspace/datasets/evButtonPush_hdf5/v02 \\
                   -p robot_type:=omy_f3m_3cam

    ros2 launch test_utils hdf5_publisher.launch.py \\
        hdf5_path:=/workspace/datasets/evButtonPush_hdf5/v02
"""

import glob
import os
import random
import time
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import h5py
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CompressedImage, JointState
import yaml


DEMO_KEY = 'data/demo_0'
CAMERA_KEYS = ['cam_wrist', 'cam_top', 'cam_belly']
JOINT_STATE_DOF = 7


class HDF5TopicPublisher(Node):
    """Replays HDF5 demo data as ROS2 topics."""

    def __init__(self):
        super().__init__('hdf5_topic_publisher')

        self.declare_parameter('hdf5_path', '')
        self.declare_parameter('robot_type', 'omy_f3m_3cam')
        self.declare_parameter('episode_idx', 0)   # -1 = random
        self.declare_parameter('fps', 60.0)
        self.declare_parameter('image_width', 224)
        self.declare_parameter('image_height', 224)
        self.declare_parameter('loop', True)

        self.hdf5_path = self.get_parameter('hdf5_path').value
        self.robot_type = self.get_parameter('robot_type').value
        self.episode_idx = self.get_parameter('episode_idx').value
        self.fps = self.get_parameter('fps').value
        self.image_width = self.get_parameter('image_width').value
        self.image_height = self.get_parameter('image_height').value
        self.loop = self.get_parameter('loop').value

        if not self.hdf5_path:
            self.get_logger().error('hdf5_path parameter is required')
            raise RuntimeError('hdf5_path not set')

        self._config: dict = {}
        self._camera_publishers: Dict[str, rclpy.publisher.Publisher] = {}
        self._joint_publishers: Dict[str, rclpy.publisher.Publisher] = {}

        # Loaded episode data
        self._frames: Dict[str, np.ndarray] = {}   # cam_key -> (T, H, W, 3)
        self._joint_pos: Optional[np.ndarray] = None  # (T, D)
        self._total_frames: int = 0
        self._frame_idx: int = 0

        self._load_config()
        self._setup_publishers()
        self._load_episode()

        period = 1.0 / self.fps
        self._timer = self.create_timer(period, self._publish_frame)

        self.get_logger().info(
            f'HDF5 publisher ready: {self._total_frames} frames @ {self.fps} fps, '
            f'image {self.image_width}x{self.image_height}, loop={self.loop}')

    # ------------------------------------------------------------------ #
    # Config                                                               #
    # ------------------------------------------------------------------ #

    def _load_config(self):
        from ament_index_python.packages import get_package_share_directory
        try:
            pkg_dir = get_package_share_directory('physical_ai_server')
            config_file = os.path.join(
                pkg_dir, 'config', f'{self.robot_type}_config.yaml')
        except Exception:
            config_file = (
                f'/root/ros2_ws/src/physical_ai_tools/physical_ai_server/'
                f'config/{self.robot_type}_config.yaml')

        try:
            with open(config_file, 'r') as f:
                full = yaml.safe_load(f)
            params = full.get('physical_ai_server', {}).get('ros__parameters', {})
            self._config = params.get(self.robot_type, {})
            self.get_logger().info(f'Loaded config from {config_file}')
        except FileNotFoundError:
            self.get_logger().error(f'Config not found: {config_file}')
            raise

    # ------------------------------------------------------------------ #
    # Publishers                                                           #
    # ------------------------------------------------------------------ #

    def _setup_publishers(self):
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)

        for entry in self._config.get('camera_topic_list', []):
            parts = entry.split(':')
            name, topic = (parts[0], ':'.join(parts[1:])) if len(parts) >= 2 else (entry, entry)
            self._camera_publishers[name] = self.create_publisher(CompressedImage, topic, qos)
            self.get_logger().info(f'Camera publisher: {topic}')

        for entry in self._config.get('joint_topic_list', []):
            parts = entry.split(':')
            name, topic = (parts[0], ':'.join(parts[1:])) if len(parts) >= 2 else (entry, entry)
            if 'odom' in topic.lower() or 'cmd_vel' in topic.lower():
                continue
            self._joint_publishers[name] = self.create_publisher(JointState, topic, qos)
            self.get_logger().info(f'Joint publisher: {topic}')

    # ------------------------------------------------------------------ #
    # Episode loading                                                      #
    # ------------------------------------------------------------------ #

    def _resolve_hdf5_file(self) -> str:
        p = Path(self.hdf5_path)
        if p.is_file():
            return str(p)
        files = sorted(glob.glob(str(p / 'demo_*.hdf5')))
        if not files:
            raise FileNotFoundError(f'No demo_*.hdf5 found in {p}')
        idx = self.episode_idx
        if idx < 0:
            idx = random.randint(0, len(files) - 1)
        idx = min(idx, len(files) - 1)
        self.get_logger().info(f'Using episode {idx}/{len(files)-1}: {files[idx]}')
        return files[idx]

    def _load_episode(self):
        path = self._resolve_hdf5_file()
        self.get_logger().info(f'Loading HDF5: {path}')

        with h5py.File(path, 'r') as f:
            self._joint_pos = f[f'{DEMO_KEY}/obs/joint_pos'][:, :JOINT_STATE_DOF].astype(np.float32)
            self._total_frames = self._joint_pos.shape[0]

            for cam in CAMERA_KEYS:
                key = f'{DEMO_KEY}/obs/{cam}'
                if key in f:
                    self._frames[cam] = f[key][:]  # (T, H, W, 3)
                else:
                    self.get_logger().warn(f'Camera key not found in HDF5: {key}')

        self._frame_idx = 0
        self.get_logger().info(
            f'Loaded {self._total_frames} frames, cameras: {list(self._frames.keys())}')

    # ------------------------------------------------------------------ #
    # Playback                                                             #
    # ------------------------------------------------------------------ #

    def _publish_frame(self):
        if self._total_frames == 0:
            return

        if self._frame_idx >= self._total_frames:
            if self.loop:
                self._frame_idx = 0
                self.get_logger().info('Looping back to frame 0')
            else:
                self.get_logger().info('Playback complete')
                self._timer.cancel()
                return

        t = self._frame_idx
        stamp = self.get_clock().now().to_msg()

        # Camera images
        for pub_name, publisher in self._camera_publishers.items():
            cam_key = pub_name  # e.g. 'cam_wrist'
            if cam_key not in self._frames:
                continue

            frame = self._frames[cam_key][t]  # (H, W, 3) uint8 RGB
            bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            resized = cv2.resize(bgr, (self.image_width, self.image_height),
                                 interpolation=cv2.INTER_AREA)
            _, encoded = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 85])

            msg = CompressedImage()
            msg.header.stamp = stamp
            msg.header.frame_id = f'{cam_key}_optical_frame'
            msg.format = 'jpeg'
            msg.data = encoded.tobytes()
            publisher.publish(msg)

        # Joint states
        joint_order = self._config.get('joint_order', {})
        for group_name, publisher in self._joint_publishers.items():
            names: List[str] = joint_order.get(group_name, [])
            if not names:
                names = [f'joint{i+1}' for i in range(JOINT_STATE_DOF)]

            positions = self._joint_pos[t].tolist()
            # Pad or trim to match declared joint count
            while len(positions) < len(names):
                positions.append(0.0)
            positions = positions[:len(names)]

            msg = JointState()
            msg.header.stamp = stamp
            msg.name = names
            msg.position = positions
            msg.velocity = [0.0] * len(names)
            msg.effort = [0.0] * len(names)
            publisher.publish(msg)

        self._frame_idx += 1

        if self._frame_idx % 100 == 0:
            self.get_logger().info(
                f'Frame {self._frame_idx}/{self._total_frames} '
                f'({100*self._frame_idx//self._total_frames}%)')


def main(args=None):
    rclpy.init(args=args)
    node = HDF5TopicPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
