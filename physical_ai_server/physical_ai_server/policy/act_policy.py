from typing import Any, Dict, Union
import torch
import numpy as np
import os
import sys
from .base_policy import BasePolicy

# Add the lerobot path to sys.path for imports
lerobot_paths = [
    '/home/dongyun/ros2_ws/src/physical_ai_tools/lerobot',
    '/home/dongyun/ros2_ws/src/lerobot'
]

for path in lerobot_paths:
    if path not in sys.path and os.path.exists(path):
        sys.path.insert(0, path)

try:
    from lerobot.common.policies.act.modeling_act import ACTPolicy as LeRobotACTPolicy
    from lerobot.common.policies.act.configuration_act import ACTConfig
    LEROBOT_AVAILABLE = True
except ImportError as e:
    print(f"Warning: LeRobot ACT modules not available: {e}")
    print("Creating mock classes for demonstration...")
    LEROBOT_AVAILABLE = False
    
    # Create mock classes for demonstration purposes
    class MockACTPolicy:
        def __init__(self, *args, **kwargs):
            pass
        
        @classmethod
        def from_pretrained(cls, *args, **kwargs):
            return cls()
        
        def to(self, device):
            return self
        
        def eval(self):
            return self
        
        def select_action(self, batch):
            # Return dummy action tensor
            return torch.zeros((1, 7))  # 7-DOF action
            
        def __call__(self, *args, **kwargs):
            # Return dummy action tensor
            return torch.zeros((1, 7))  # 7-DOF action
    
    class MockACTConfig:
        def __init__(self, *args, **kwargs):
            pass
    
    LeRobotACTPolicy = MockACTPolicy
    ACTConfig = MockACTConfig

from huggingface_hub import snapshot_download


class ACTPolicy(BasePolicy):
    """
    Enhanced ACT (Action Chunking with Transformers) Policy Wrapper
    
    LeRobot의 ACT 정책을 통합 인터페이스로 래핑한 클래스입니다.
    Enhanced configuration management를 지원하여 pretrained model의 설정을 
    자동으로 로드하고 사용자 설정과 병합합니다.
    """
    
    def __init__(self, 
                 config_path: str = None, 
                 config_dict: Dict[str, Any] = None,
                 pretrained_model_path: str = None,
                 merge_strategy: str = "user_priority"):
        """
        Initialize ACT policy with enhanced configuration management
        
        Args:
            config_path: YAML configuration file path
            config_dict: Configuration dictionary
            pretrained_model_path: Path to pretrained model for auto-config loading
            merge_strategy: Strategy for merging configurations
        """
        super().__init__(config_path, config_dict, pretrained_model_path, merge_strategy)
        self.policy = None
        self.stats = None
        
    def load_model(self, checkpoint_path: str = None) -> None:
        """
        Load ACT model with enhanced configuration management
        
        Args:
            checkpoint_path: Checkpoint path (optional, can be taken from config)
        """
        model_config = self.config.get('model', {})
        
        # Determine the model path to use
        model_path_to_use = None
        
        if checkpoint_path:
            # Use explicitly provided checkpoint path
            model_path_to_use = checkpoint_path
        elif self.pretrained_model_path:
            # Use the pretrained model path from initialization
            model_path_to_use = self.pretrained_model_path
        elif model_config.get('pretrained_policy_name_or_path'):
            # Use path from configuration
            model_path_to_use = model_config.get('pretrained_policy_name_or_path')
        else:
            raise ValueError("No model path specified. Provide checkpoint_path, set pretrained_model_path, or specify pretrained_policy_name_or_path in config.")
        
        revision = model_config.get('revision', 'main')
        
        try:
            if not LEROBOT_AVAILABLE:
                # Use mock policy for demonstration
                self.logger.warning("Using mock ACT policy for demonstration purposes")
                self.policy = LeRobotACTPolicy()
                self.is_loaded = True
                self.logger.info("Mock ACT policy initialized successfully")
                return
            
            # If the path exists locally, load from local path
            if os.path.exists(model_path_to_use):
                self.logger.info(f"Loading ACT model from local path: {model_path_to_use}")
                self.policy = LeRobotACTPolicy.from_pretrained(model_path_to_use)
            else:
                # Try to load from Hugging Face Hub
                self.logger.info(f"Loading ACT model from Hub: {model_path_to_use}")
                self.policy = LeRobotACTPolicy.from_pretrained(
                    model_path_to_use,
                    revision=revision
                )
            
            self.policy.to(self.device)
            self.policy.eval()
            self.is_loaded = True
            
            # Load normalization statistics if available
            self._load_normalization_stats(model_path_to_use, revision)
            
            self.logger.info(f"ACT model loaded successfully on device: {self.device}")
            
        except Exception as e:
            self.logger.error(f"Failed to load ACT model: {e}")
            raise RuntimeError(f"Failed to load ACT model from {model_path_to_use}: {e}")
    
    def _load_normalization_stats(self, model_path: str, revision: str = "main") -> None:
        """
        Load normalization statistics for the model
        
        Args:
            model_path: Path to the model
            revision: Model revision for Hub models
        """
        try:
            if os.path.exists(model_path):
                # Local model path
                stats_path = os.path.join(model_path, "stats.json")
                if os.path.exists(stats_path):
                    import json
                    with open(stats_path, 'r') as f:
                        self.stats = json.load(f)
                    self.logger.info("Loaded normalization statistics from local file")
            else:
                # Hub model - try to download stats
                repo_path = snapshot_download(
                    model_path,
                    revision=revision,
                    allow_patterns=["*.json", "*.yaml"]
                )
                stats_path = os.path.join(repo_path, "stats.json")
                if os.path.exists(stats_path):
                    import json
                    with open(stats_path, 'r') as f:
                        self.stats = json.load(f)
                    self.logger.info("Loaded normalization statistics from Hub")
        except Exception as e:
            self.logger.warning(f"Failed to load normalization statistics: {e}")
            self.stats = None
    
    def predict(self, 
                observation: Union[Dict[str, Any], torch.Tensor], 
                **kwargs) -> torch.Tensor:
        """
        액션 예측
        
        Args:
            observation: 관측 데이터 (딕셔너리 또는 텐서)
            **kwargs: 추가 인자들
            
        Returns:
            예측된 액션 시퀀스
        """
        if not self.is_loaded:
            raise RuntimeError("모델이 로드되지 않았습니다. load_model()을 먼저 호출하세요.")
        
        if not LEROBOT_AVAILABLE:
            # Return dummy action for demonstration
            self.logger.info("Returning dummy action from mock policy")
            return torch.zeros((1, 7))  # 7-DOF dummy action
        
        # 관측 데이터 전처리
        if isinstance(observation, dict):
            # 딕셔너리 형태의 관측 데이터를 배치 형태로 변환
            batch_obs = {}
            for key, value in observation.items():
                if isinstance(value, np.ndarray):
                    value = torch.from_numpy(value).float()
                if isinstance(value, torch.Tensor):
                    if value.dim() == 3 and key.endswith(('image', 'rgb')):  # H, W, C
                        value = value.permute(2, 0, 1)  # C, H, W
                    if value.dim() <= 2:
                        value = value.unsqueeze(0)  # 배치 차원 추가
                batch_obs[key] = value.to(self.device)
        else:
            raise ValueError("관측 데이터는 딕셔너리 형태여야 합니다.")
        
        # 추론 실행
        with torch.no_grad():
            actions = self.policy.select_action(batch_obs)
        
        return actions
    
    def reset(self) -> None:
        """정책 상태 리셋"""
        if self.policy and hasattr(self.policy, 'reset'):
            self.policy.reset()
    
    def preprocess_observation(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """
        관측 데이터 전처리
        
        Args:
            observation: 원본 관측 데이터
            
        Returns:
            전처리된 관측 데이터
        """
        processed_obs = {}
        
        for key, value in observation.items():
            if isinstance(value, np.ndarray):
                value = torch.from_numpy(value).float()
            
            # 이미지 데이터 정규화
            if key.endswith(('image', 'rgb', 'cam')) and isinstance(value, torch.Tensor):
                if value.dtype == torch.uint8:
                    value = value.float() / 255.0
                
                # 필요시 정규화 통계 적용
                if self.stats and key in self.stats:
                    mean = torch.tensor(self.stats[key]['mean']).to(value.device)
                    std = torch.tensor(self.stats[key]['std']).to(value.device)
                    if value.dim() == 3:  # H, W, C
                        mean = mean.view(1, 1, -1)
                        std = std.view(1, 1, -1)
                    value = (value - mean) / std
            
            processed_obs[key] = value
        
        return processed_obs
    
    def postprocess_action(self, action: torch.Tensor) -> np.ndarray:
        """
        액션 후처리
        
        Args:
            action: 원본 액션 텐서
            
        Returns:
            후처리된 액션 (numpy 배열)
        """
        if isinstance(action, torch.Tensor):
            action = action.cpu().numpy()
        
        # 액션 클리핑 (필요시)
        action_config = self.config.get('action', {})
        if 'min_action' in action_config and 'max_action' in action_config:
            action = np.clip(
                action,
                action_config['min_action'],
                action_config['max_action']
            )
        
        return action
    
    def _get_model_parameters(self) -> Dict[str, Any]:
        """
        Get ACT model parameter information if model is loaded
        
        Returns:
            Dictionary containing model parameter statistics
        """
        if not self.is_loaded or self.policy is None:
            return None
        
        if not LEROBOT_AVAILABLE:
            # Return mock parameters for demonstration
            return {
                'total_parameters': 1_000_000,
                'trainable_parameters': 1_000_000,
                'model_size_mb': 4.0,
                'device': str(self.device)
            }
        
        try:
            # For LeRobot ACT Policy, access the underlying model
            if hasattr(self.policy, 'model'):
                model = self.policy.model
            else:
                model = self.policy
            
            total_params = sum(p.numel() for p in model.parameters())
            trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
            
            return {
                'total_parameters': total_params,
                'trainable_parameters': trainable_params,
                'model_size_mb': total_params * 4 / (1024 * 1024),  # Assuming float32
                'device': str(next(model.parameters()).device) if total_params > 0 else str(self.device)
            }
        except Exception as e:
            self.logger.warning(f"Failed to get ACT model parameters: {e}")
            return None

# 정책 팩토리에 등록
from .policy_factory import PolicyFactory
PolicyFactory.register_policy('act', ACTPolicy)