#!/usr/bin/env python3
"""
Unit tests for LeRobot Executor.

These tests verify the core functionality of the executor without requiring
actual Zenoh connections or LeRobot training/inference.
"""

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# Mock zenoh_ros2_sdk before importing executor
@pytest.fixture(autouse=True)
def mock_zenoh_sdk():
    """Mock zenoh_ros2_sdk module for testing."""
    mock_module = MagicMock()
    mock_module.ROS2Publisher = MagicMock
    mock_module.ROS2ServiceServer = MagicMock
    mock_module.ROS2Subscriber = MagicMock
    mock_module.get_logger = MagicMock(return_value=MagicMock())
    
    with patch.dict('sys.modules', {'zenoh_ros2_sdk': mock_module}):
        yield mock_module


class TestExecutorState:
    """Tests for ExecutorState enum."""

    def test_executor_states_exist(self, mock_zenoh_sdk):
        """Test that all expected states exist."""
        # Import after mocking
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import ExecutorState
        
        assert hasattr(ExecutorState, 'IDLE')
        assert hasattr(ExecutorState, 'TRAINING')
        assert hasattr(ExecutorState, 'INFERENCE')
        assert hasattr(ExecutorState, 'STOPPING')
        assert hasattr(ExecutorState, 'ERROR')

    def test_executor_state_values(self, mock_zenoh_sdk):
        """Test state enum values."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import ExecutorState
        
        assert ExecutorState.IDLE.value == "idle"
        assert ExecutorState.TRAINING.value == "training"
        assert ExecutorState.INFERENCE.value == "inference"
        assert ExecutorState.STOPPING.value == "stopping"
        assert ExecutorState.ERROR.value == "error"


class TestTrainingProgress:
    """Tests for TrainingProgress dataclass."""

    def test_training_progress_defaults(self, mock_zenoh_sdk):
        """Test default values."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import TrainingProgress
        
        progress = TrainingProgress()
        
        assert progress.step == 0
        assert progress.total_steps == 0
        assert progress.epoch == 0.0
        assert progress.loss == 0.0
        assert progress.learning_rate == 0.0
        assert progress.gradient_norm == 0.0
        assert progress.elapsed_seconds == 0.0
        assert progress.eta_seconds == 0.0

    def test_training_progress_to_dict(self, mock_zenoh_sdk):
        """Test to_dict method."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import TrainingProgress
        
        progress = TrainingProgress(
            step=100,
            total_steps=1000,
            loss=0.5,
            learning_rate=0.001,
        )
        
        result = progress.to_dict()
        
        assert isinstance(result, dict)
        assert result["step"] == 100
        assert result["total_steps"] == 1000
        assert result["loss"] == 0.5
        assert result["learning_rate"] == 0.001


class TestExecutorConfig:
    """Tests for ExecutorConfig dataclass."""

    def test_executor_config_defaults(self, mock_zenoh_sdk):
        """Test default configuration values."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import ExecutorConfig
        
        config = ExecutorConfig()
        
        assert config.router_ip == "127.0.0.1"
        assert config.router_port == 7447
        assert config.domain_id == 0
        assert config.node_name == "lerobot_executor"
        assert config.train_service == "/lerobot/train"
        assert config.infer_service == "/lerobot/infer"
        assert config.stop_service == "/lerobot/stop"
        assert config.status_service == "/lerobot/status"

    def test_executor_config_custom(self, mock_zenoh_sdk):
        """Test custom configuration values."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import ExecutorConfig
        
        config = ExecutorConfig(
            router_ip="192.168.1.100",
            router_port=7448,
            domain_id=42,
        )
        
        assert config.router_ip == "192.168.1.100"
        assert config.router_port == 7448
        assert config.domain_id == 42


class TestAvailablePolicies:
    """Tests for available policies list."""

    def test_available_policies_structure(self, mock_zenoh_sdk):
        """Test that policies have required fields."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import AVAILABLE_POLICIES
        
        required_fields = ["name", "display_name", "category"]
        
        for policy in AVAILABLE_POLICIES:
            for field in required_fields:
                assert field in policy, f"Policy missing field: {field}"

    def test_available_policies_categories(self, mock_zenoh_sdk):
        """Test that all policies have valid categories."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import AVAILABLE_POLICIES
        
        valid_categories = [
            "imitation_learning",
            "reinforcement_learning",
            "vla",
        ]
        
        for policy in AVAILABLE_POLICIES:
            assert policy["category"] in valid_categories, (
                f"Invalid category: {policy['category']}"
            )

    def test_core_policies_present(self, mock_zenoh_sdk):
        """Test that core policies are present."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import AVAILABLE_POLICIES
        
        policy_names = [p["name"] for p in AVAILABLE_POLICIES]
        
        core_policies = ["act", "diffusion", "vqbet", "tdmpc", "pi0", "smolvla"]
        
        for name in core_policies:
            assert name in policy_names, f"Core policy missing: {name}"


class TestLeRobotExecutorInit:
    """Tests for LeRobotExecutor initialization."""

    def test_executor_init_default_config(self, mock_zenoh_sdk):
        """Test executor initialization with default config."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import LeRobotExecutor, ExecutorState
        
        executor = LeRobotExecutor()
        
        assert executor.state == ExecutorState.IDLE
        assert executor._running is False
        assert executor._loaded_model is None
        assert executor._inference_running is False

    def test_executor_init_custom_config(self, mock_zenoh_sdk):
        """Test executor initialization with custom config."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import LeRobotExecutor, ExecutorConfig
        
        config = ExecutorConfig(router_port=9999)
        executor = LeRobotExecutor(config)
        
        assert executor.config.router_port == 9999

    def test_executor_state_thread_safety(self, mock_zenoh_sdk):
        """Test that state property is thread-safe."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import LeRobotExecutor, ExecutorState
        
        executor = LeRobotExecutor()
        results = []
        
        def set_state(state, delay):
            time.sleep(delay)
            executor.state = state
            results.append(state)
        
        threads = [
            threading.Thread(target=set_state, args=(ExecutorState.TRAINING, 0.01)),
            threading.Thread(target=set_state, args=(ExecutorState.INFERENCE, 0.02)),
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # Both operations should complete without error
        assert len(results) == 2


class TestBuildTrainingArgs:
    """Tests for training argument building."""

    def test_build_training_args_basic(self, mock_zenoh_sdk):
        """Test basic training args building."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import LeRobotExecutor
        
        executor = LeRobotExecutor()
        
        # Create mock request
        @dataclass
        class MockRequest:
            policy_type: str = "act"
            dataset_path: str = "lerobot/pusht"
            steps: int = 1000
            batch_size: int = 8
            learning_rate: float = 0.0001
            save_freq: int = 500
            push_to_hub: bool = False
            output_dir: str = ""
            wandb_project: str = ""
        
        request = MockRequest()
        args = executor._build_training_args(request)
        
        assert "--policy.type=act" in args
        assert "--dataset.repo_id=lerobot/pusht" in args
        assert "--steps=1000" in args
        assert "--batch_size=8" in args
        assert "--policy.device=cuda" in args

    def test_build_training_args_with_wandb(self, mock_zenoh_sdk):
        """Test training args with wandb project."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import LeRobotExecutor
        
        executor = LeRobotExecutor()
        
        @dataclass
        class MockRequest:
            policy_type: str = "diffusion"
            dataset_path: str = "lerobot/aloha_sim"
            steps: int = 5000
            batch_size: int = 16
            learning_rate: float = 0.0
            save_freq: int = 0
            push_to_hub: bool = False
            output_dir: str = "/outputs/test"
            wandb_project: str = "my-project"
        
        request = MockRequest()
        args = executor._build_training_args(request)
        
        assert "--wandb.project=my-project" in args
        assert "--output_dir=/outputs/test" in args


class TestPreprocessImage:
    """Tests for image preprocessing."""

    def test_preprocess_image_output_shape(self, mock_zenoh_sdk):
        """Test that preprocessed image has correct shape."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        import numpy as np
        
        from executor import LeRobotExecutor
        
        executor = LeRobotExecutor()
        
        # Create dummy BGR image (480x640x3)
        dummy_image = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        with patch('cv2.resize') as mock_resize, \
             patch('cv2.cvtColor') as mock_cvt:
            
            # Mock cv2.resize to return 224x224 image
            mock_resize.return_value = np.random.randint(
                0, 255, (224, 224, 3), dtype=np.uint8
            )
            # Mock cv2.cvtColor to return same image (RGB conversion)
            mock_cvt.return_value = mock_resize.return_value
            
            result = executor._preprocess_image(dummy_image)
            
            # Should be (1, 3, 224, 224) tensor
            assert result.shape == (1, 3, 224, 224)
            assert result.dtype.is_floating_point


class TestPredictDummyAction:
    """Tests for dummy action prediction."""

    def test_predict_dummy_action_format(self, mock_zenoh_sdk):
        """Test that dummy action has correct format."""
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from executor import LeRobotExecutor
        
        executor = LeRobotExecutor()
        action = executor._predict_dummy_action()
        
        assert action is not None
        assert "joint_positions" in action
        assert "gripper" in action
        assert "timestamp" in action
        assert isinstance(action["joint_positions"], list)
        assert len(action["joint_positions"]) == 6
        assert isinstance(action["gripper"], float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
