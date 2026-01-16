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

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING, Dict, Type

from physical_ai_bt.actions import (
    MoveArms,
    MoveLift,
    MoveHead,
    Rotate,
)
from physical_ai_bt.actions.base_action import BTNode, BaseAction, BaseControl
from physical_ai_bt.controls import Sequence

if TYPE_CHECKING:
    from rclpy.node import Node


class TreeLoader:

    def __init__(self, node: 'Node', joint_names: list = None, topic_config: dict = None):

        self.node = node
        self.joint_names = joint_names or []
        self.topic_config = topic_config or {}

        self.control_types: Dict[str, Type[BaseControl]] = {
            'Sequence': Sequence,
        }

        self.action_types: Dict[str, Type[BaseAction]] = {
            'Rotate': Rotate,
            'MoveHead': MoveHead,
            'MoveArms': MoveArms,
            'MoveLift': MoveLift,
        }

    def load_tree_from_file(self, xml_path: str, main_tree_id: str = None) -> BTNode:

        tree = ET.parse(xml_path)
        root = tree.getroot()

        if main_tree_id is None:
            main_tree_id = root.get('main_tree_to_execute')
            if not main_tree_id:
                raise ValueError("No main_tree_to_execute specified in XML")

        for behavior_tree in root.findall('BehaviorTree'):
            if behavior_tree.get('ID') == main_tree_id:
                return self._load_node(behavior_tree[0])

        raise ValueError(f"BehaviorTree with ID '{main_tree_id}' not found")

    def _load_node(self, xml_node: ET.Element) -> BTNode:

        node_type = xml_node.tag
        node_id = xml_node.get('ID', node_type)
        node_name = xml_node.get('name', node_id)

        if node_type in self.control_types:
            control_class = self.control_types[node_type]
            control_node = control_class(self.node, name=node_name)

            for child_xml in xml_node:
                child_node = self._load_node(child_xml)
                control_node.add_child(child_node)

            return control_node

        elif node_id in self.action_types:
            action_class = self.action_types[node_id]
            params = self._parse_node_params(xml_node)
            return self._create_action(action_class, node_name, params)

    def _parse_node_params(self, xml_node: ET.Element) -> Dict:

        params = {}

        for key, value in xml_node.attrib.items():
            if key not in ['ID', 'name']:
                params[key] = self._convert_value(value)

        return params

    def _convert_value(self, value: str):
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'

        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        if ',' in value:
            parts = [p.strip() for p in value.split(',')]
            try:
                return [float(p) if '.' in p else int(p) for p in parts]
            except ValueError:
                return parts

        return value

    def _create_action(self, action_class: Type[BaseAction], name: str, params: Dict) -> BaseAction:

        if action_class == Rotate:
            return action_class(
                node=self.node,
                angle_deg=params.get('angle_deg', 90.0),
                topic_config=self.topic_config
            )

        elif action_class == MoveHead:
            return action_class(
                node=self.node,
                head_positions=params.get('head_positions', [0.0, 0.0]),
                position_threshold=params.get('position_threshold', 0.01),
                duration=params.get('duration', 5.0)
            )

        elif action_class == MoveArms:
            return action_class(
                node=self.node,
                left_positions=params.get('left_positions', [0.0]*8),
                right_positions=params.get('right_positions', [0.0]*8),
                position_threshold=params.get('position_threshold', 0.01),
                duration=params.get('duration', 2.0)
            )

        elif action_class == MoveLift:
            return action_class(
                node=self.node,
                lift_position=params.get('lift_position', 0.0),
                position_threshold=params.get('position_threshold', 0.01),
                duration=params.get('duration', 5.0)
            )

        else:
            raise ValueError(f"Unknown action class: {action_class}")
