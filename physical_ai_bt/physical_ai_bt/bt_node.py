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
from physical_ai_interfaces.srv import SendCommand
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

        # --- Dual-tree architecture state ---
        self.current_tree_type = None  # 'init' or 'main'
        self.tree_execution_mode = 'stopped'  # 'stopped', 'running', 'stopping'
        self.init_tree_path = None
        self.main_tree_path = None

        # Service server to receive commands from Physical AI Manager (no-op for compatibility)
        self.command_service = self.create_service(
            SendCommand,
            '/task/command',
            self._command_callback
        )

        # Service server for demo control (STOP/IDLE only)
        self.demo_service = self.create_service(
            SendCommand,
            '/demo/command',
            self._demo_start_callback
        )

        self.declare_parameter('robot_type', 'ffw_sg2_rev1')
        self.declare_parameter('tree_xml', 'ffw_test.xml')
        self.declare_parameter('tick_rate', 30.0)
        self.declare_parameter('inference_fps', 5)

        # robot_type = self.get_parameter('robot_type').value
        robot_type = 'ffw_sg2_rev1'
        tree_xml = self.get_parameter('tree_xml').value
        tick_rate = self.get_parameter('tick_rate').value
        self.inference_fps = self.get_parameter('inference_fps').value

        self.get_logger().info(f'Inference FPS: {self.inference_fps}')
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

        # Store init tree path
        self.init_tree_path = os.path.join(pkg_share, 'trees', 'init.xml')
        if not os.path.exists(self.init_tree_path):
            # Try relative path
            self.init_tree_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'trees',
                'init.xml'
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
                self.current_tree_type = 'main'
                self.tree_execution_mode = 'running'
                self.get_logger().info(f'Main tree loaded successfully: {self.root.name}')
            else:
                self.get_logger().error(f'Main tree file not found: {self.main_tree_path}')
                self.current_tree_type = None
                self.tree_execution_mode = 'stopped'
        except Exception as e:
            self.get_logger().error(f'Failed to load main tree: {str(e)}')
            self.root = None
            self.current_tree_type = None
            self.tree_execution_mode = 'stopped'

        # Create timer for BT tick
        self.timer = self.create_timer(1.0 / tick_rate, self.tick_callback)

        self.get_logger().info('Behavior Tree Node initialized')
        self.get_logger().info(f'  Robot type: {robot_type}')
        self.get_logger().info(f'  Joint names: {self.joint_names}')
        self.get_logger().info(f'  Main tree XML: {tree_xml}')
        self.get_logger().info(f'  Init tree: init.xml')
        if self.root:
            self.get_logger().info(f'  Tree auto-loaded and ready for execution')
        else:
            self.get_logger().warn(f'  Tree failed to load - waiting for manual command')
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

    def _command_callback(self, request, response):
        """
        Legacy service for compatibility - BT is auto-running on launch.
        This service no longer relays to AI Server or triggers tree execution.
        """
        self.get_logger().info(
            f'Received /task/command: {request.command} (ignored - BT is auto-running)'
        )
        response.success = True
        response.message = "BT is auto-running, /task/command no longer needed"
        return response


    def _demo_start_callback(self, request, response):
        """
        Handle demo commands: IDLE and STOP only.

        IDLE (0): Load and execute init.xml tree
        STOP (3): Immediately halt current tree execution
        """
        try:
            command = request.command

            # ===== IDLE COMMAND =====
            if command == SendCommand.Request.IDLE:
                self.get_logger().info('IDLE command received - loading init tree')

                # Check if init tree exists
                if not os.path.exists(self.init_tree_path):
                    self.get_logger().error(f'Init tree not found: {self.init_tree_path}')
                    response.success = False
                    response.message = 'init.xml not found'
                    return response

                # Stop current execution if running
                if self.tree_execution_mode == 'running':
                    self._immediate_halt()

                # Load init tree
                try:
                    self.root = self.xml_loader.load_tree_from_file(self.init_tree_path)
                    self.current_tree_type = 'init'
                    self.tree_execution_mode = 'running'
                    self.get_logger().info(f'Init tree loaded and running: {self.root.name}')
                except Exception as e:
                    self.get_logger().error(f'Failed to load init tree: {str(e)}')
                    response.success = False
                    response.message = f'Failed to load init tree: {str(e)}'
                    return response

                response.success = True
                response.message = 'Init tree started'

            # ===== STOP COMMAND =====
            elif command == SendCommand.Request.STOP:
                self.get_logger().info('STOP command received - halting BT execution')

                if self.tree_execution_mode != 'running':
                    self.get_logger().warn('STOP requested but no tree is running')
                    response.success = True
                    response.message = 'No tree running'
                    return response

                # Immediate halt (do NOT wait for current action to finish)
                self._immediate_halt()

                response.success = True
                response.message = 'BT execution halted'

            else:
                self.get_logger().warn(
                    f'Unsupported command in /demo/command: {command} '
                    '(only IDLE and STOP supported in auto-run mode)'
                )
                response.success = False
                response.message = f'Command {command} not supported in auto-run mode'

        except Exception as e:
            self.get_logger().error(f'Error in demo command callback: {str(e)}')
            response.success = False
            response.message = f'Error: {str(e)}'

        return response

    def _immediate_halt(self):
        """
        Immediately halt BT execution without waiting for current action.
        Called by STOP command and when switching trees.
        """
        self.get_logger().info('Executing immediate halt of BT tree')

        # Prevent tick from continuing
        self.tree_execution_mode = 'stopping'

        # Reset all nodes (calls reset() recursively)
        if self.root is not None:
            self.root.reset()
            self.get_logger().info('All BT nodes reset')

        # Clear tree and reset state
        self.root = None
        self.tree_execution_mode = 'stopped'

        self.get_logger().info('BT execution halted - ready for next command')

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
        """
        Handle tree completion (SUCCESS or FAILURE).
        Resets state and prepares for next command.
        """
        # Reset tree
        if self.root is not None:
            self.root.reset()

        # Reset execution state
        self.tree_execution_mode = 'stopped'

        # Log based on tree type
        if self.current_tree_type == 'init':
            self.get_logger().info('Init tree complete - ready for next command')
        elif self.current_tree_type == 'main':
            self.get_logger().info('Main tree complete - ready for next command')
        else:
            self.get_logger().info('Tree execution complete')

    def _reset_tree(self):
        """
        DEPRECATED: Tree reset now handled by _handle_tree_completion().
        Kept for backward compatibility only.
        """
        self.get_logger().warn('_reset_tree() is deprecated - use _handle_tree_completion()')
        pass


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
