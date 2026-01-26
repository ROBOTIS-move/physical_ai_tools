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
Mock Topic Publisher Node for testing rosbag2 recording pipeline.

This node publishes mock data for camera and joint topics defined in
physical_ai_server config files, allowing testing without a real robot.

Usage:
    ros2 run test_utils mock_topic_publisher.py --ros-args -p robot_type:=ffw_bg2_rev4
"""

import math
import time
from typing import Dict, List

import cv2
from cv_bridge import CvBridge
from geometry_msgs.msg import TransformStamped, Twist
from nav_msgs.msg import Odometry
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, CompressedImage, JointState
from tf2_ros import StaticTransformBroadcaster, TransformBroadcaster
import yaml


class MockTopicPublisher(Node):
    """Publishes mock sensor data for testing rosbag recording."""

    # Default publish rates
    CAMERA_RATE_HZ = 15.0  # Cameras run at 15fps
    JOINT_RATE_HZ = 100.0
    TF_RATE_HZ = 100.0

    # Image settings per camera type
    # head cameras: 720p (1280x720)
    # wrist cameras: VGA (640x480)
    HEAD_CAMERA_WIDTH = 1280
    HEAD_CAMERA_HEIGHT = 720
    WRIST_CAMERA_WIDTH = 640
    WRIST_CAMERA_HEIGHT = 480

    def __init__(self):
        super().__init__('mock_topic_publisher')

        # Declare parameters
        self.declare_parameter('robot_type', 'ffw_bg2_rev4')
        self.declare_parameter('config_path', '')
        self.declare_parameter('camera_rate', self.CAMERA_RATE_HZ)
        self.declare_parameter('joint_rate', self.JOINT_RATE_HZ)

        self.robot_type = self.get_parameter('robot_type').value
        self.config_path = self.get_parameter('config_path').value
        self.camera_rate = self.get_parameter('camera_rate').value
        self.joint_rate = self.get_parameter('joint_rate').value

        self.get_logger().info(f'Starting mock publisher for robot type: {self.robot_type}')

        # Initialize components
        self.bridge = CvBridge()
        self.tf_broadcaster = TransformBroadcaster(self)
        self.static_tf_broadcaster = StaticTransformBroadcaster(self)

        # Storage for publishers
        self.camera_publishers: Dict[str, rclpy.publisher.Publisher] = {}
        self.camera_info_publishers: Dict[str, rclpy.publisher.Publisher] = {}
        self.joint_publishers: Dict[str, rclpy.publisher.Publisher] = {}
        self.odom_publisher = None
        self.cmd_vel_publisher = None

        # Joint configuration
        self.joint_configs: Dict[str, List[str]] = {}

        # Time tracking for animations
        self.start_time = time.time()

        # Create callback groups for parallel processing
        from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
        self.camera_callback_group = MutuallyExclusiveCallbackGroup()
        self.joint_callback_group = MutuallyExclusiveCallbackGroup()
        self.tf_callback_group = MutuallyExclusiveCallbackGroup()

        # Load config and setup publishers
        self._load_config()
        self._setup_publishers()
        self._setup_timers()

        # Publish static transforms once
        self._publish_static_transforms()

        self.get_logger().info('Mock topic publisher initialized successfully')

    def _load_config(self):
        """Load robot configuration from YAML file."""
        if self.config_path:
            config_file = self.config_path
        else:
            # Default path based on package structure
            import os
            from ament_index_python.packages import get_package_share_directory
            try:
                pkg_dir = get_package_share_directory('physical_ai_server')
                config_file = os.path.join(
                    pkg_dir, 'config', f'{self.robot_type}_config.yaml')
            except Exception:
                # Fallback to source path
                config_file = (
                    f'/root/main_ws/physical_ai_tools/physical_ai_server/'
                    f'config/{self.robot_type}_config.yaml')

        self.get_logger().info(f'Loading config from: {config_file}')

        try:
            with open(config_file, 'r') as f:
                full_config = yaml.safe_load(f)

            # Navigate to robot-specific config
            params = full_config.get('physical_ai_server', {}).get('ros__parameters', {})
            self.config = params.get(self.robot_type, {})

            if not self.config:
                self.get_logger().error(f'No config found for robot type: {self.robot_type}')
                self.config = self._get_default_config()

            # Extract joint order for each joint group
            joint_order = self.config.get('joint_order', {})
            for group_name, joints in joint_order.items():
                self.joint_configs[group_name] = joints

            cam_count = len(self.config.get('camera_topic_list', []))
            joint_count = len(self.config.get('joint_topic_list', []))
            self.get_logger().info(
                f'Loaded config with {cam_count} cameras, {joint_count} joint topics')

        except FileNotFoundError:
            self.get_logger().warn(f'Config file not found: {config_file}, using defaults')
            self.config = self._get_default_config()

    def _get_default_config(self) -> dict:
        """Return default configuration for testing."""
        return {
            'camera_topic_list': [
                'cam_test:/camera/test/image_raw/compressed'
            ],
            'joint_topic_list': [
                'test_joints:/test/joint_states'
            ],
            'rosbag_extra_topic_list': [
                '/tf',
                '/tf_static'
            ],
            'joint_order': {
                'test_joints': ['joint1', 'joint2', 'joint3', 'joint4', 'joint5', 'joint6']
            }
        }

    def _setup_publishers(self):
        """Create publishers for all configured topics."""
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)

        # Camera publishers (CompressedImage)
        camera_topics = self.config.get('camera_topic_list', [])
        for topic_entry in camera_topics:
            # Format: "name:topic_path"
            parts = topic_entry.split(':')
            if len(parts) >= 2:
                name = parts[0]
                topic = ':'.join(parts[1:])  # Handle topic paths with colons
            else:
                name = topic_entry
                topic = topic_entry

            self.camera_publishers[name] = self.create_publisher(
                CompressedImage, topic, qos)
            self.get_logger().info(f'Created camera publisher: {topic}')

            # Also create camera_info publisher
            # Config uses: /robot/camera/cam_xxx/image_raw/compressed/camera_info
            camera_info_topic = topic + '/camera_info'
            self.camera_info_publishers[name] = self.create_publisher(
                CameraInfo, camera_info_topic, qos)
            self.get_logger().info(f'Created camera_info publisher: {camera_info_topic}')

        # Joint state publishers (skip odom and cmd_vel - they have different msg types)
        joint_topics = self.config.get('joint_topic_list', [])
        for topic_entry in joint_topics:
            parts = topic_entry.split(':')
            if len(parts) >= 2:
                name = parts[0]
                topic = ':'.join(parts[1:])
            else:
                name = topic_entry
                topic = topic_entry

            # Skip odom and cmd_vel - they will be created separately
            if 'odom' in topic.lower():
                self.odom_publisher = self.create_publisher(Odometry, topic, qos)
                self.get_logger().info(f'Created odom publisher: {topic}')
                continue
            elif 'cmd_vel' in topic.lower():
                self.cmd_vel_publisher = self.create_publisher(Twist, topic, qos)
                self.get_logger().info(f'Created cmd_vel publisher: {topic}')
                continue

            self.joint_publishers[name] = self.create_publisher(
                JointState, topic, qos)
            self.get_logger().info(f'Created joint publisher: {topic}')

    def _setup_timers(self):
        """Set up periodic timers for publishing with separate callback groups."""
        # Camera timer - runs independently in its own callback group
        if self.camera_publishers:
            self.camera_timer = self.create_timer(
                1.0 / self.camera_rate,
                self._publish_camera_data,
                callback_group=self.camera_callback_group)

        # Joint state timer - runs independently at high rate (100Hz)
        if self.joint_publishers:
            self.joint_timer = self.create_timer(
                1.0 / self.joint_rate,
                self._publish_joint_states,
                callback_group=self.joint_callback_group)

        # TF timer - runs independently
        self.tf_timer = self.create_timer(
            1.0 / self.TF_RATE_HZ,
            self._publish_tf,
            callback_group=self.tf_callback_group)

    def _get_camera_resolution(self, camera_name: str) -> tuple:
        """Get camera resolution based on camera type (head vs wrist)."""
        if 'head' in camera_name.lower():
            return (self.HEAD_CAMERA_WIDTH, self.HEAD_CAMERA_HEIGHT)
        else:
            # wrist cameras and others use VGA
            return (self.WRIST_CAMERA_WIDTH, self.WRIST_CAMERA_HEIGHT)

    def _publish_camera_data(self):
        """Publish mock camera images."""
        current_time = self.get_clock().now().to_msg()
        elapsed = time.time() - self.start_time

        for name, publisher in self.camera_publishers.items():
            # Get resolution for this camera
            width, height = self._get_camera_resolution(name)

            # Create a test pattern image with moving elements
            image = self._create_test_image(name, elapsed, width, height)

            # Compress as JPEG
            _, encoded = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 80])

            # Create CompressedImage message
            msg = CompressedImage()
            msg.header.stamp = current_time
            msg.header.frame_id = f'{name}_optical_frame'
            msg.format = 'jpeg'
            msg.data = encoded.tobytes()

            publisher.publish(msg)

            # Also publish camera info
            if name in self.camera_info_publishers:
                info_msg = self._create_camera_info(name, current_time, width, height)
                self.camera_info_publishers[name].publish(info_msg)

    def _create_test_image(self, camera_name: str, elapsed: float,
                           width: int, height: int) -> np.ndarray:
        """Create a test pattern image with camera name and timestamp."""
        # Create base image with gradient (using vectorized operations for speed)
        image = np.zeros((height, width, 3), dtype=np.uint8)

        # Create gradient using meshgrid (faster than nested loops)
        x_coords = np.arange(width)
        y_coords = np.arange(height)
        xx, yy = np.meshgrid(x_coords, y_coords)

        image[:, :, 0] = (128 + 127 * np.sin(elapsed + xx * 0.01)).astype(np.uint8)
        image[:, :, 1] = (128 + 127 * np.sin(elapsed * 1.5 + yy * 0.01)).astype(np.uint8)
        image[:, :, 2] = (128 + 127 * np.cos(elapsed * 0.5)).astype(np.uint8)

        # Add moving circle
        cx = int(width / 2 + 100 * math.sin(elapsed * 2))
        cy = int(height / 2 + 100 * math.cos(elapsed * 2))
        cv2.circle(image, (cx, cy), 30, (255, 255, 255), -1)

        # Add camera name text
        cv2.putText(image, camera_name, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

        # Add resolution info
        cv2.putText(image, f'{width}x{height}', (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 1)

        # Add timestamp
        cv2.putText(image, f't={elapsed:.2f}s', (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)

        # Add frame counter
        frame_num = int(elapsed * self.camera_rate)
        cv2.putText(image, f'frame: {frame_num}', (10, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 1)

        return image

    def _create_camera_info(self, camera_name: str, stamp,
                            width: int, height: int) -> CameraInfo:
        """Create a mock CameraInfo message."""
        msg = CameraInfo()
        msg.header.stamp = stamp
        msg.header.frame_id = f'{camera_name}_optical_frame'
        msg.width = width
        msg.height = height
        msg.distortion_model = 'plumb_bob'

        # Mock intrinsic parameters (reasonable defaults based on resolution)
        fx = fy = 500.0 * (width / 640.0)  # Scale focal length with resolution
        cx, cy = width / 2.0, height / 2.0
        msg.k = [fx, 0.0, cx, 0.0, fy, cy, 0.0, 0.0, 1.0]
        msg.d = [0.0, 0.0, 0.0, 0.0, 0.0]
        msg.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        msg.p = [fx, 0.0, cx, 0.0, 0.0, fy, cy, 0.0, 0.0, 0.0, 1.0, 0.0]

        return msg

    def _publish_joint_states(self):
        """Publish mock joint states with sinusoidal motion."""
        current_time = self.get_clock().now().to_msg()
        elapsed = time.time() - self.start_time

        for name, publisher in self.joint_publishers.items():
            # Get joint names for this group
            # Try to match with joint_configs
            joint_names = None
            for config_name, joints in self.joint_configs.items():
                if config_name in name or name in config_name:
                    joint_names = joints
                    break

            if joint_names is None:
                # Default joint names
                joint_names = [f'{name}_joint{i}' for i in range(1, 7)]

            msg = JointState()
            msg.header.stamp = current_time
            msg.header.frame_id = ''
            msg.name = joint_names

            # Generate sinusoidal positions for each joint
            positions = []
            velocities = []
            efforts = []

            for i, joint_name in enumerate(joint_names):
                # Different frequency and phase for each joint
                freq = 0.5 + i * 0.1
                phase = i * math.pi / 4
                amplitude = 0.5 if 'gripper' not in joint_name else 0.04

                pos = amplitude * math.sin(elapsed * freq + phase)
                vel = amplitude * freq * math.cos(elapsed * freq + phase)

                positions.append(pos)
                velocities.append(vel)
                efforts.append(0.0)

            msg.position = positions
            msg.velocity = velocities
            msg.effort = efforts

            publisher.publish(msg)

        # Publish odom if available
        if self.odom_publisher:
            odom_msg = Odometry()
            odom_msg.header.stamp = current_time
            odom_msg.header.frame_id = 'odom'
            odom_msg.child_frame_id = 'base_link'
            # Simulate circular motion
            odom_msg.pose.pose.position.x = 0.5 * math.sin(elapsed * 0.2)
            odom_msg.pose.pose.position.y = 0.5 * math.cos(elapsed * 0.2)
            odom_msg.pose.pose.position.z = 0.0
            odom_msg.pose.pose.orientation.w = 1.0
            odom_msg.twist.twist.linear.x = 0.1 * math.cos(elapsed * 0.2)
            odom_msg.twist.twist.linear.y = -0.1 * math.sin(elapsed * 0.2)
            self.odom_publisher.publish(odom_msg)

        # Publish cmd_vel if available
        if self.cmd_vel_publisher:
            cmd_msg = Twist()
            cmd_msg.linear.x = 0.1 * math.sin(elapsed * 0.5)
            cmd_msg.linear.y = 0.0
            cmd_msg.angular.z = 0.2 * math.cos(elapsed * 0.3)
            self.cmd_vel_publisher.publish(cmd_msg)

    def _publish_tf(self):
        """Publish dynamic TF transforms."""
        current_time = self.get_clock().now().to_msg()

        transforms = []

        # Base to world transform
        t = TransformStamped()
        t.header.stamp = current_time
        t.header.frame_id = 'world'
        t.child_frame_id = 'base_link'
        t.transform.translation.x = 0.0
        t.transform.translation.y = 0.0
        t.transform.translation.z = 0.0
        t.transform.rotation.x = 0.0
        t.transform.rotation.y = 0.0
        t.transform.rotation.z = 0.0
        t.transform.rotation.w = 1.0
        transforms.append(t)

        # Camera frames
        for name in self.camera_publishers.keys():
            t = TransformStamped()
            t.header.stamp = current_time
            t.header.frame_id = 'base_link'
            t.child_frame_id = f'{name}_link'
            t.transform.translation.x = 0.5
            t.transform.translation.y = 0.0
            t.transform.translation.z = 0.5
            t.transform.rotation.x = 0.0
            t.transform.rotation.y = 0.0
            t.transform.rotation.z = 0.0
            t.transform.rotation.w = 1.0
            transforms.append(t)

            # Optical frame
            t2 = TransformStamped()
            t2.header.stamp = current_time
            t2.header.frame_id = f'{name}_link'
            t2.child_frame_id = f'{name}_optical_frame'
            t2.transform.translation.x = 0.0
            t2.transform.translation.y = 0.0
            t2.transform.translation.z = 0.0
            # Rotate to optical frame convention
            t2.transform.rotation.x = -0.5
            t2.transform.rotation.y = 0.5
            t2.transform.rotation.z = -0.5
            t2.transform.rotation.w = 0.5
            transforms.append(t2)

        if transforms:
            self.tf_broadcaster.sendTransform(transforms)

    def _publish_static_transforms(self):
        """Publish static TF transforms."""
        transforms = []

        # Static world frame
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = 'map'
        t.child_frame_id = 'world'
        t.transform.translation.x = 0.0
        t.transform.translation.y = 0.0
        t.transform.translation.z = 0.0
        t.transform.rotation.x = 0.0
        t.transform.rotation.y = 0.0
        t.transform.rotation.z = 0.0
        t.transform.rotation.w = 1.0
        transforms.append(t)

        if transforms:
            self.static_tf_broadcaster.sendTransform(transforms)


def main(args=None):
    rclpy.init(args=args)

    node = MockTopicPublisher()

    # Use MultiThreadedExecutor to prevent camera callbacks from blocking joint callbacks
    # This ensures joint topics publish at their intended rate (100Hz) independently
    from rclpy.executors import MultiThreadedExecutor
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
