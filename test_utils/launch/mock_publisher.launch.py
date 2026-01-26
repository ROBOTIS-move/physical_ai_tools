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
Launch file for mock topic publisher.

Usage:
    ros2 launch test_utils mock_publisher.launch.py
    ros2 launch test_utils mock_publisher.launch.py robot_type:=omy_f3m
    ros2 launch test_utils mock_publisher.launch.py robot_type:=ffw_bg2_rev4 camera_rate:=15.0
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    # Declare launch arguments
    robot_type_arg = DeclareLaunchArgument(
        'robot_type',
        default_value='ffw_bg2_rev4',
        description='Robot type to load config for'
    )

    camera_rate_arg = DeclareLaunchArgument(
        'camera_rate',
        default_value='15.0',
        description='Camera publish rate in Hz'
    )

    joint_rate_arg = DeclareLaunchArgument(
        'joint_rate',
        default_value='100.0',
        description='Joint state publish rate in Hz'
    )

    config_path_arg = DeclareLaunchArgument(
        'config_path',
        default_value='',
        description='Optional path to config file (overrides robot_type lookup)'
    )

    # Create the node
    mock_publisher_node = Node(
        package='test_utils',
        executable='mock_topic_publisher.py',
        name='mock_topic_publisher',
        output='screen',
        parameters=[{
            'robot_type': LaunchConfiguration('robot_type'),
            'camera_rate': LaunchConfiguration('camera_rate'),
            'joint_rate': LaunchConfiguration('joint_rate'),
            'config_path': LaunchConfiguration('config_path'),
        }]
    )

    return LaunchDescription([
        robot_type_arg,
        camera_rate_arg,
        joint_rate_arg,
        config_path_arg,
        mock_publisher_node,
    ])
