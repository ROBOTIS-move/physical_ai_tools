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
# Author: Dongyun Kim

"""
Unit tests for Zenoh communication layer.

Tests the ROS2 rmw_zenoh based communication with LeRobot Docker container.

Architecture:
- physical_ai_server uses ROS2 + rmw_zenoh (standard ROS2 API)
- lerobot container uses zenoh_ros2_sdk (no ROS2 installed)
- rmw_zenoh converts ROS2 messages to Zenoh protocol = COMPATIBLE
"""

import unittest
import sys


class TestZenohLeRobotClient(unittest.TestCase):
    """Test ZenohLeRobotClient with ROS2 rmw_zenoh."""

    def test_01_import_ros2_interfaces(self):
        """Test that ROS2 interfaces can be imported."""
        try:
            from physical_ai_interfaces.msg import TrainingProgress
            from physical_ai_interfaces.srv import (
                TrainModel,
                StartInference,
                StopTraining,
                TrainingStatus,
                PolicyList,
                CheckpointList,
                ModelList,
            )
            self.assertTrue(True)
            print("PASS: ROS2 interfaces imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import ROS2 interfaces: {e}")

    def test_02_import_zenoh_lerobot_client(self):
        """Test that ZenohLeRobotClient can be imported."""
        try:
            from physical_ai_server.communication.zenoh_lerobot_client import (
                ZenohLeRobotClient,
                LeRobotResponse,
            )
            self.assertTrue(True)
            print("PASS: ZenohLeRobotClient imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import ZenohLeRobotClient: {e}")

    def test_03_import_training_manager(self):
        """Test that ZenohTrainingManager can be imported."""
        try:
            from physical_ai_server.training.zenoh_training_manager import (
                ZenohTrainingManager,
            )
            self.assertTrue(True)
            print("PASS: ZenohTrainingManager imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import ZenohTrainingManager: {e}")

    def test_04_import_inference_manager(self):
        """Test that ZenohInferenceManager can be imported."""
        try:
            from physical_ai_server.inference.zenoh_inference_manager import (
                ZenohInferenceManager,
            )
            self.assertTrue(True)
            print("PASS: ZenohInferenceManager imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import ZenohInferenceManager: {e}")

    def test_05_create_client_default(self):
        """Test creating ZenohLeRobotClient with default parameters."""
        from physical_ai_server.communication.zenoh_lerobot_client import (
            ZenohLeRobotClient,
        )

        client = ZenohLeRobotClient()
        self.assertIsNotNone(client)
        self.assertEqual(client.timeout_sec, 30.0)
        self.assertFalse(client._connected)
        print("PASS: ZenohLeRobotClient created with default parameters")

    def test_06_create_client_custom_params(self):
        """Test creating ZenohLeRobotClient with custom parameters."""
        from physical_ai_server.communication.zenoh_lerobot_client import (
            ZenohLeRobotClient,
        )

        client = ZenohLeRobotClient(
            timeout_sec=10.0,
            # These params are ignored but accepted for compatibility
            router_ip='192.168.1.100',
            router_port=7448,
            domain_id=42,
        )
        self.assertIsNotNone(client)
        self.assertEqual(client.timeout_sec, 10.0)
        print("PASS: ZenohLeRobotClient created with custom parameters")

    def test_07_connect_requires_node(self):
        """Test that connect() requires a ROS2 node."""
        from physical_ai_server.communication.zenoh_lerobot_client import (
            ZenohLeRobotClient,
        )

        client = ZenohLeRobotClient()
        result = client.connect()

        # Should fail without a ROS2 node
        self.assertFalse(result)
        self.assertFalse(client._connected)
        print("PASS: connect() correctly requires ROS2 node")

    def test_08_service_names_defined(self):
        """Test that service names are defined."""
        from physical_ai_server.communication.zenoh_lerobot_client import (
            ZenohLeRobotClient,
        )

        self.assertEqual(ZenohLeRobotClient.SERVICE_TRAIN, '/lerobot/train')
        self.assertEqual(ZenohLeRobotClient.SERVICE_INFER, '/lerobot/infer')
        self.assertEqual(ZenohLeRobotClient.SERVICE_STOP, '/lerobot/stop')
        self.assertEqual(ZenohLeRobotClient.SERVICE_STATUS, '/lerobot/status')
        self.assertEqual(
            ZenohLeRobotClient.SERVICE_POLICY_LIST, '/lerobot/policy_list'
        )
        self.assertEqual(
            ZenohLeRobotClient.SERVICE_CHECKPOINT_LIST, '/lerobot/checkpoint_list'
        )
        self.assertEqual(
            ZenohLeRobotClient.SERVICE_MODEL_LIST, '/lerobot/model_list'
        )
        print("PASS: Service names are correctly defined")

    def test_09_topic_names_defined(self):
        """Test that topic names are defined."""
        from physical_ai_server.communication.zenoh_lerobot_client import (
            ZenohLeRobotClient,
        )

        self.assertEqual(ZenohLeRobotClient.TOPIC_PROGRESS, '/lerobot/progress')
        self.assertEqual(ZenohLeRobotClient.TOPIC_ACTION, '/lerobot/action')
        print("PASS: Topic names are correctly defined")


class TestLeRobotResponse(unittest.TestCase):
    """Test LeRobotResponse dataclass."""

    def test_create_response(self):
        """Test creating LeRobotResponse."""
        from physical_ai_server.communication.zenoh_lerobot_client import (
            LeRobotResponse,
        )

        response = LeRobotResponse(
            success=True,
            message="Test message",
            data={"key": "value"},
            request_id="test-123"
        )

        self.assertTrue(response.success)
        self.assertEqual(response.message, "Test message")
        self.assertEqual(response.data["key"], "value")
        self.assertEqual(response.request_id, "test-123")
        print("PASS: LeRobotResponse created successfully")

    def test_from_service_response_none(self):
        """Test from_service_response with None."""
        from physical_ai_server.communication.zenoh_lerobot_client import (
            LeRobotResponse,
        )

        response = LeRobotResponse.from_service_response(None, "test-id")

        self.assertFalse(response.success)
        self.assertIn("No response", response.message)
        self.assertEqual(response.request_id, "test-id")
        print("PASS: from_service_response handles None correctly")

    def test_extract_data_with_attributes(self):
        """Test _extract_data extracts various attributes."""
        from physical_ai_server.communication.zenoh_lerobot_client import (
            LeRobotResponse,
        )

        class MockResponse:
            success = True
            message = "OK"
            job_id = "job-123"
            state = "training"
            step = 100
            total_steps = 1000
            loss = 0.5
            learning_rate = 0.001
            policies = ["act", "diffusion"]
            checkpoints = ["ckpt1", "ckpt2"]
            models = ["model1"]

        response = LeRobotResponse.from_service_response(MockResponse())

        self.assertTrue(response.success)
        self.assertEqual(response.data['job_id'], "job-123")
        self.assertEqual(response.data['state'], "training")
        self.assertEqual(response.data['step'], 100)
        self.assertEqual(response.data['policies'], ["act", "diffusion"])
        print("PASS: _extract_data extracts all attributes correctly")


def main():
    """Run tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add tests in order
    suite.addTests(loader.loadTestsFromTestCase(TestLeRobotResponse))
    suite.addTests(loader.loadTestsFromTestCase(TestZenohLeRobotClient))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
