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
# Author: Seongwoo Kim

import os
import rclpy
from ament_index_python.packages import get_package_share_directory
from physical_ai_bt.actions.base_action import BTNode, NodeStatus
from physical_ai_bt.blackboard import Blackboard
from physical_ai_bt.bt_nodes_loader import XMLTreeLoader
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

class BehaviorTreeNode(Node):
    """Generic ROS2 node for Behavior Tree execution."""

    def __init__(self):
        super().__init__('physical_ai_bt_node')

        # Blackboard initialization
        self.blackboard = Blackboard()

        # Tree execution state
        self.tree_execution_mode = 'stopped'  # 'stopped', 'running', 'stopping'
        self.main_tree_path = None

        self.declare_parameter('robot_type', 'ffw_sg2_rev1')
        self.declare_parameter('tree_xml', 'ffw_test.xml')
        self.declare_parameter('tick_rate', 30.0)

        robot_type = 'ffw_sg2_rev1'
        tree_xml = self.get_parameter('tree_xml').value
        tick_rate = self.get_parameter('tick_rate').value

        self.robot_type = robot_type
        self.joint_names = self._load_joint_order(robot_type)
        self.topic_config = self._load_topic_config(robot_type)

        pkg_share = get_package_share_directory('physical_ai_bt')

        # Store main tree path (don't load yet - wait for command)
        self.main_tree_path = os.path.join(pkg_share, 'trees', tree_xml)
        if not os.path.exists(self.main_tree_path):
            # Try relative path
            self.main_tree_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'trees',
                tree_xml
            )

        # Initialize XML loader
        self.xml_loader = XMLTreeLoader(
            self,
            joint_names=self.joint_names,
            topic_config=self.topic_config
        )

        # Load main tree immediately on startup
        self.root = None
        try:
            self.get_logger().info(f'Loading main tree: {self.main_tree_path}')
            if os.path.exists(self.main_tree_path):
                self.root = self.xml_loader.load_tree_from_file(self.main_tree_path)
                self.tree_execution_mode = 'running'
                self.get_logger().info(f'Main tree loaded successfully: {self.root.name}')
            else:
                self.get_logger().error(f'Main tree file not found: {self.main_tree_path}')
                self.tree_execution_mode = 'stopped'
        except Exception as e:
            self.get_logger().error(f'Failed to load main tree: {str(e)}')
            self.root = None
            self.tree_execution_mode = 'stopped'

        # Create timer for BT tick
        self.timer = self.create_timer(1.0 / tick_rate, self.tick_callback)

        self.get_logger().info('Behavior Tree Node initialized')
        self.get_logger().info(f'  Robot type: {robot_type}')
        self.get_logger().info(f'  Main tree XML: {tree_xml}')
        if self.root:
            self.get_logger().info(f'  Tree auto-loaded and executing')
        else:
            self.get_logger().error(f'  Tree failed to load')
        self.get_logger().info(f'  Tick rate: {tick_rate} Hz')

    def _load_joint_order(self, robot_type: str) -> list:
        """Load joint order from ROS2 parameters (config file)."""
        # Load from bt_node namespace (from bt_node_params.yaml)
        self.declare_parameter(f'{robot_type}.joint_list', [''])
        joint_list_param = self.get_parameter(f'{robot_type}.joint_list').value

        if not joint_list_param or joint_list_param == ['']:
            self.get_logger().warn(
                f'No joint_list found in config for {robot_type}, using default'
            )
            return []

        # Collect joint orders from all joint groups
        all_joint_order = []
        for joint_name in joint_list_param:
            # Load joint_order from bt_node namespace
            param_name = f'{robot_type}.joint_order.{joint_name}'
            self.declare_parameter(param_name, [''])
            joint_order = self.get_parameter(param_name).value

            if joint_order and joint_order != ['']:
                all_joint_order.extend(joint_order)
                self.get_logger().info(f'Loaded {len(joint_order)} joints from {joint_name}')

        if not all_joint_order:
            self.get_logger().error(f'No joint_order found for any joint group')
            return []

        self.get_logger().info(f'Total joints loaded: {len(all_joint_order)}')
        return all_joint_order

    def _load_topic_config(self, robot_type: str) -> dict:
        """
        Load topic configuration for multi-publisher support.

        Returns:
            dict: {
                'joint_list': ['leader_left', 'leader_right', ...],
                'joint_topic_list': ['leader_left:/topic1', 'leader_right:/topic2', ...],
                'topic_map': {
                    'leader_left': '/topic1',
                    'leader_right': '/topic2',
                    ...
                },
                'joint_order': {
                    'leader_left': ['arm_l_joint1', ...],
                    'leader_right': ['arm_r_joint1', ...],
                    ...
                }
            }
        """
        # joint_list is already declared in _load_joint_order, just get it
        joint_list = self.get_parameter(f'{robot_type}.joint_list').value

        # Load joint_topic_list
        self.declare_parameter(f'{robot_type}.joint_topic_list', [''])
        joint_topic_list = self.get_parameter(f'{robot_type}.joint_topic_list').value

        # Build topic_map: parse "joint_group:/topic" format
        topic_map = {}
        for topic_entry in joint_topic_list:
            if ':' in topic_entry:
                joint_group, topic = topic_entry.split(':', 1)
                topic_map[joint_group] = topic

        # Load joint_order for each joint group (already declared in _load_joint_order)
        joint_order = {}
        for joint_name in joint_list:
            param_name = f'{robot_type}.joint_order.{joint_name}'
            order = self.get_parameter(param_name).value
            if order and order != ['']:
                joint_order[joint_name] = order

        config = {
            'joint_list': joint_list,
            'joint_topic_list': joint_topic_list,
            'topic_map': topic_map,
            'joint_order': joint_order
        }

        self.get_logger().info(f'Loaded topic config for {len(topic_map)} joint groups')
        return config


    def tick_callback(self):
        """Timer callback for BT tick execution."""
        # Skip if no tree loaded
        if self.root is None:
            return

        # Skip if being stopped
        if self.tree_execution_mode == 'stopping':
            return

        # Only tick if running
        if self.tree_execution_mode != 'running':
            return

        # Tick the root node
        status = self.root.tick()

        # Handle tree completion
        if status in [NodeStatus.SUCCESS, NodeStatus.FAILURE]:
            status_name = 'successfully' if status == NodeStatus.SUCCESS else 'with failure'
            self.get_logger().info(f'Behavior Tree completed {status_name}')
            self._handle_tree_completion(status)

    def _handle_tree_completion(self, status: NodeStatus):
        """Handle tree completion (SUCCESS or FAILURE)."""
        if self.root is not None:
            self.root.reset()

        self.tree_execution_mode = 'stopped'
        self.get_logger().info('Behavior tree completed')


def main(args=None):
    """Main entry point for the BT node."""
    rclpy.init(args=args)

    try:
        bt_node = BehaviorTreeNode()
        executor = MultiThreadedExecutor()
        executor.add_node(bt_node)

        bt_node.get_logger().info('Behavior Tree Node is running')
        executor.spin()

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f'Error in BT node: {e}')
    finally:
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
