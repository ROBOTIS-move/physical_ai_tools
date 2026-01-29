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
# Author: Physical AI Team

"""
Unit tests for Zenoh communication layer.

Tests the zenoh_ros2_sdk based communication with LeRobot Docker container.

Architecture:
- physical_ai_server uses ROS2 + rmw_zenoh for INTERNAL ROS2 communication
- physical_ai_server uses zenoh_ros2_sdk for EXTERNAL communication with lerobot
- lerobot container uses zenoh_ros2_sdk only (no ROS2 installed)
- Both sides use the same zenoh_ros2_sdk protocol = COMPATIBLE
"""

import unittest
import sys
import os


class TestZenohLeRobotClient(unittest.TestCase):
    """Test ZenohLeRobotClient with zenoh_ros2_sdk."""

    def test_01_import_zenoh_ros2_sdk(self):
        """Test that zenoh_ros2_sdk can be imported."""
        try:
            from zenoh_ros2_sdk import (
                ROS2ServiceClient,
                ROS2Subscriber,
                ROS2Publisher,
            )
            self.assertTrue(True)
            print("PASS: zenoh_ros2_sdk imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import zenoh_ros2_sdk: {e}")

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
        self.assertEqual(client.router_ip, os.getenv('ZENOH_ROUTER_IP', '127.0.0.1'))
        self.assertEqual(client.router_port, 7447)
        self.assertEqual(client.domain_id, int(os.getenv('ROS_DOMAIN_ID', '30')))
        print("PASS: ZenohLeRobotClient created with default parameters")

    def test_06_create_client_custom_params(self):
        """Test creating ZenohLeRobotClient with custom parameters."""
        from physical_ai_server.communication.zenoh_lerobot_client import (
            ZenohLeRobotClient,
        )

        client = ZenohLeRobotClient(
            timeout_sec=10.0,
            router_ip='192.168.1.100',
            router_port=7448,
            domain_id=42,
        )
        self.assertIsNotNone(client)
        self.assertEqual(client.timeout_sec, 10.0)
        self.assertEqual(client.router_ip, '192.168.1.100')
        self.assertEqual(client.router_port, 7448)
        self.assertEqual(client.domain_id, 42)
        print("PASS: ZenohLeRobotClient created with custom parameters")

    def test_07_connect_creates_service_clients(self):
        """Test that connect() creates zenoh_ros2_sdk service clients."""
        from physical_ai_server.communication.zenoh_lerobot_client import (
            ZenohLeRobotClient,
        )

        client = ZenohLeRobotClient()
        result = client.connect()
        self.assertTrue(result)
        self.assertTrue(client._connected)
        print("PASS: connect() succeeded")

        # Verify service clients are created
        self.assertIsNotNone(client._train_client)
        self.assertIsNotNone(client._infer_client)
        self.assertIsNotNone(client._stop_client)
        self.assertIsNotNone(client._status_client)
        print("PASS: Service clients created")

        client.disconnect()
        self.assertFalse(client._connected)
        print("PASS: disconnect() succeeded")

    def test_08_training_manager_connect(self):
        """Test ZenohTrainingManager connect."""
        from physical_ai_server.training.zenoh_training_manager import (
            ZenohTrainingManager,
        )

        manager = ZenohTrainingManager()
        self.assertIsNotNone(manager)

        result = manager.connect()
        self.assertTrue(result)
        print("PASS: ZenohTrainingManager connected")

        manager.disconnect()

    def test_09_inference_manager_connect(self):
        """Test ZenohInferenceManager connect."""
        from physical_ai_server.inference.zenoh_inference_manager import (
            ZenohInferenceManager,
        )

        manager = ZenohInferenceManager()
        self.assertIsNotNone(manager)

        result = manager.connect()
        self.assertTrue(result)
        print("PASS: ZenohInferenceManager connected")

        manager.disconnect()

    def test_10_get_training_status_without_server(self):
        """Test get_training_status when lerobot server is not available."""
        from physical_ai_server.communication.zenoh_lerobot_client import (
            ZenohLeRobotClient,
        )

        client = ZenohLeRobotClient(timeout_sec=5.0)
        client.connect()

        # This should return a timeout response (no lerobot server running)
        response = client.get_training_status()
        self.assertIsNotNone(response)
        # Will timeout since no lerobot server is running
        print(f"INFO: get_training_status response: success={response.success}, "
              f"message={response.message}")

        client.disconnect()


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


class TestServiceDefinitions(unittest.TestCase):
    """Test service definition constants."""

    def test_service_definitions_exist(self):
        """Test that SERVICE_DEFINITIONS are defined."""
        from physical_ai_server.communication.zenoh_lerobot_client import (
            SERVICE_DEFINITIONS,
            MESSAGE_DEFINITIONS,
        )

        expected_services = [
            'TrainModel',
            'StartInference',
            'StopTraining',
            'TrainingStatus',
            'PolicyList',
            'CheckpointList',
            'ModelList',
        ]

        for svc in expected_services:
            self.assertIn(svc, SERVICE_DEFINITIONS)
            self.assertIn('type', SERVICE_DEFINITIONS[svc])
            self.assertIn('request', SERVICE_DEFINITIONS[svc])
            self.assertIn('response', SERVICE_DEFINITIONS[svc])

        print("PASS: All service definitions exist")

    def test_message_definitions_exist(self):
        """Test that MESSAGE_DEFINITIONS are defined."""
        from physical_ai_server.communication.zenoh_lerobot_client import (
            MESSAGE_DEFINITIONS,
        )

        self.assertIn('TrainingProgress', MESSAGE_DEFINITIONS)
        self.assertIn('type', MESSAGE_DEFINITIONS['TrainingProgress'])
        self.assertIn('definition', MESSAGE_DEFINITIONS['TrainingProgress'])

        print("PASS: Message definitions exist")


def main():
    """Run tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add tests in order
    suite.addTests(loader.loadTestsFromTestCase(TestLeRobotResponse))
    suite.addTests(loader.loadTestsFromTestCase(TestServiceDefinitions))
    suite.addTests(loader.loadTestsFromTestCase(TestZenohLeRobotClient))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
