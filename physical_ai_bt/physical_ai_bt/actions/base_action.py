#!/usr/bin/env python3
#
# Copyright 2026 ROBOTIS CO., LTD.
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

"""Base classes for all Behavior Tree nodes."""

from enum import Enum
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from rclpy.node import Node


class NodeStatus(Enum):
    SUCCESS = 1
    FAILURE = 2
    RUNNING = 3


class BTNode:

    def __init__(self, node: 'Node', name: str):

        self.node = node
        self.name = name
        self.status = NodeStatus.RUNNING

    def tick(self) -> NodeStatus:

        raise NotImplementedError("Subclasses must implement tick() method")

    def reset(self):
        self.status = NodeStatus.RUNNING

    def log_info(self, message: str):
        self.node.get_logger().info(f"[{self.name}] {message}")

    def log_warn(self, message: str):
        self.node.get_logger().warn(f"[{self.name}] {message}")

    def log_error(self, message: str):
        self.node.get_logger().error(f"[{self.name}] {message}")


class BaseAction(BTNode):
    pass


class BaseControl(BTNode):

    def __init__(self, node: 'Node', name: str):

        super().__init__(node, name)
        self.children: List[BTNode] = []

    def add_child(self, child: BTNode):
        self.children.append(child)

    def reset(self):
        super().reset()
        for child in self.children:
            child.reset()


class BaseDecorator(BTNode):

    def __init__(self, node: 'Node', name: str, child: BTNode = None):

        super().__init__(node, name)
        self.child = child

    def set_child(self, child: BTNode):
        self.child = child

    def reset(self):
        super().reset()
        if self.child:
            self.child.reset()
