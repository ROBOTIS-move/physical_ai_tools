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

Tests the ROS2 rmw_zenoh based communication with Docker containers.

Architecture:
- physical_ai_server uses ROS2 + rmw_zenoh (standard ROS2 API)
- container uses zenoh_ros2_sdk (no ROS2 installed)
- rmw_zenoh converts ROS2 messages to Zenoh protocol = COMPATIBLE
"""

import unittest
import sys


class TestZenohServiceClient(unittest.TestCase):
    """Test ZenohServiceClient with ROS2 rmw_zenoh."""

    def test_01_import_ros2_interfaces(self):
        """Test that ROS2 interfaces can be imported."""
        try:
            from physical_ai_interfaces.msg import TrainingProgress
            from physical_ai_interfaces.srv import (
                TrainModel,
                StartInference,
                GetActionChunk,
                StopTraining,
                TrainingStatus,
            )
            self.assertTrue(True)
            print("PASS: ROS2 interfaces imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import ROS2 interfaces: {e}")

    def test_02_import_zenoh_service_client(self):
        """Test that ZenohServiceClient can be imported."""
        try:
            from physical_ai_server.communication.zenoh_service_client import (
                ZenohServiceClient,
                ServiceResponse,
            )
            self.assertTrue(True)
            print("PASS: ZenohServiceClient imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import ZenohServiceClient: {e}")

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
        """Test that InferenceManager can be imported."""
        try:
            from physical_ai_server.inference.inference_manager import (
                InferenceManager,
            )
            self.assertTrue(True)
            print("PASS: InferenceManager imported successfully")
        except ImportError as e:
            self.fail(f"Failed to import InferenceManager: {e}")

    def test_05_create_client_default(self):
        """Test creating ZenohServiceClient with default parameters."""
        from physical_ai_server.communication.zenoh_service_client import (
            ZenohServiceClient,
        )

        client = ZenohServiceClient(node=None, service_prefix="/groot")
        self.assertIsNotNone(client)
        self.assertEqual(client.timeout_sec, 30.0)
        self.assertFalse(client._connected)
        print("PASS: ZenohServiceClient created with default parameters")

    def test_06_create_client_custom_params(self):
        """Test creating ZenohServiceClient with custom parameters."""
        from physical_ai_server.communication.zenoh_service_client import (
            ZenohServiceClient,
        )

        client = ZenohServiceClient(
            node=None,
            service_prefix="/lerobot",
            timeout_sec=10.0,
        )
        self.assertIsNotNone(client)
        self.assertEqual(client.timeout_sec, 10.0)
        print("PASS: ZenohServiceClient created with custom parameters")

    def test_07_connect_requires_node(self):
        """Test that connect() requires a ROS2 node."""
        from physical_ai_server.communication.zenoh_service_client import (
            ZenohServiceClient,
        )

        client = ZenohServiceClient(node=None, service_prefix="/groot")
        result = client.connect()

        # Should fail without a ROS2 node
        self.assertFalse(result)
        self.assertFalse(client._connected)
        print("PASS: connect() correctly requires ROS2 node")

    def test_08_service_names_with_prefix(self):
        """Test that service names use the configured prefix."""
        from physical_ai_server.communication.zenoh_service_client import (
            ZenohServiceClient,
        )

        # Test with /groot prefix
        groot_client = ZenohServiceClient(node=None, service_prefix="/groot")
        self.assertEqual(groot_client.service_infer, '/groot/infer')
        self.assertEqual(groot_client.service_stop, '/groot/stop')
        self.assertEqual(groot_client.service_train, '/groot/train')
        self.assertEqual(groot_client.service_status, '/groot/status')
        self.assertEqual(
            groot_client.service_get_action_chunk, '/groot/get_action_chunk'
        )

        # Test with /lerobot prefix
        lerobot_client = ZenohServiceClient(node=None, service_prefix="/lerobot")
        self.assertEqual(lerobot_client.service_infer, '/lerobot/infer')
        self.assertEqual(lerobot_client.service_stop, '/lerobot/stop')
        self.assertEqual(lerobot_client.service_train, '/lerobot/train')
        self.assertEqual(lerobot_client.service_status, '/lerobot/status')

        print("PASS: Service names correctly use configured prefix")

    def test_09_topic_names_with_prefix(self):
        """Test that topic names use the configured prefix."""
        from physical_ai_server.communication.zenoh_service_client import (
            ZenohServiceClient,
        )

        client = ZenohServiceClient(node=None, service_prefix="/lerobot")
        self.assertEqual(client.topic_progress, '/lerobot/progress')

        client2 = ZenohServiceClient(node=None, service_prefix="/groot")
        self.assertEqual(client2.topic_progress, '/groot/progress')

        print("PASS: Topic names correctly use configured prefix")



class TestServiceResponse(unittest.TestCase):
    """Test ServiceResponse dataclass."""

    def test_create_response(self):
        """Test creating ServiceResponse."""
        from physical_ai_server.communication.zenoh_service_client import (
            ServiceResponse,
        )

        response = ServiceResponse(
            success=True,
            message="Test message",
            data={"key": "value"},
            request_id="test-123"
        )

        self.assertTrue(response.success)
        self.assertEqual(response.message, "Test message")
        self.assertEqual(response.data["key"], "value")
        self.assertEqual(response.request_id, "test-123")
        print("PASS: ServiceResponse created successfully")

    def test_from_service_response_none(self):
        """Test from_service_response with None."""
        from physical_ai_server.communication.zenoh_service_client import (
            ServiceResponse,
        )

        response = ServiceResponse.from_service_response(None, "test-id")

        self.assertFalse(response.success)
        self.assertIn("No response", response.message)
        self.assertEqual(response.request_id, "test-id")
        print("PASS: from_service_response handles None correctly")

    def test_extract_data_with_attributes(self):
        """Test _extract_data extracts various attributes."""
        from physical_ai_server.communication.zenoh_service_client import (
            ServiceResponse,
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

        response = ServiceResponse.from_service_response(MockResponse())

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
    suite.addTests(loader.loadTestsFromTestCase(TestServiceResponse))
    suite.addTests(loader.loadTestsFromTestCase(TestZenohServiceClient))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
