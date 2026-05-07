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
Launch file for HDF5 topic publisher.

Usage:
    ros2 launch test_utils hdf5_publisher.launch.py \\
        hdf5_path:=/workspace/datasets/evButtonPush_hdf5/v02

    ros2 launch test_utils hdf5_publisher.launch.py \\
        hdf5_path:=/workspace/datasets/evButtonPush_hdf5/v02/demo_000.hdf5 \\
        robot_type:=omy_f3m_3cam \\
        episode_idx:=3 \\
        image_width:=224 image_height:=224 \\
        fps:=30.0 loop:=true
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('hdf5_path', default_value='',
                              description='Path to .hdf5 file or directory of demo_*.hdf5 files'),
        DeclareLaunchArgument('robot_type', default_value='omy_f3m_3cam',
                              description='Robot type for topic name config'),
        DeclareLaunchArgument('episode_idx', default_value='0',
                              description='Episode index to replay (-1 = random)'),
        DeclareLaunchArgument('fps', default_value='60.0',
                              description='Playback rate in Hz'),
        DeclareLaunchArgument('image_width', default_value='224',
                              description='Resize target width'),
        DeclareLaunchArgument('image_height', default_value='224',
                              description='Resize target height'),
        DeclareLaunchArgument('loop', default_value='true',
                              description='Loop after last frame'),

        Node(
            package='test_utils',
            executable='hdf5_topic_publisher.py',
            name='hdf5_topic_publisher',
            output='screen',
            parameters=[{
                'hdf5_path':    LaunchConfiguration('hdf5_path'),
                'robot_type':   LaunchConfiguration('robot_type'),
                'episode_idx':  LaunchConfiguration('episode_idx'),
                'fps':          LaunchConfiguration('fps'),
                'image_width':  LaunchConfiguration('image_width'),
                'image_height': LaunchConfiguration('image_height'),
                'loop':         LaunchConfiguration('loop'),
            }],
        ),
    ])
