from typing import Any, Dict, Union
import torch
import numpy as np
from .base_policy import BasePolicy
from lerobot.common.policies.diffusion.modeling_diffusion import DiffusionPolicy as LeRobotDiffusionPolicy
from lerobot.common.policies.diffusion.configuration_diffusion import DiffusionConfig
from huggingface_hub import snapshot_download
import os


class DiffusionPolicy(BasePolicy):
    """
    Diffusion Policy Wrapper
    
    LeRobot의 Diffusion 정책을 통합 인터페이스로 래핑한 클래스입니다.
    """
    
    def __init__(self, config_path: str = None, config_dict: Dict[str, Any] = None):
        super().__init__(config_path, config_dict)
        self.policy = None
        self.stats = None
        
    def load_model(self, checkpoint_path: str = None) -> None:
        """
        Diffusion 모델 로드
        
        Args:
            checkpoint_path: 체크포인트 경로 (선택사항, config에서 가져올 수 있음)
        """
        model_config = self.config['model']
        pretrained_policy_name_or_path = model_config.get('pretrained_policy_name_or_path')
        revision = model_config.get('revision', 'main')
        
        if checkpoint_path:
            # 로컬 체크포인트 로드
            self.policy = LeRobotDiffusionPolicy.from_pretrained(checkpoint_path)
        elif pretrained_policy_name_or_path:
            # Hugging Face Hub에서 로드
            self.policy = LeRobotDiffusionPolicy.from_pretrained(
                pretrained_policy_name_or_path,
                revision=revision
            )
        else:
            raise ValueError("checkpoint_path 또는 pretrained_policy_name_or_path가 필요합니다.")
        
        self.policy.to(self.device)
        self.policy.eval()
        self.is_loaded = True
        
        # 정규화 통계 로드 (있는 경우)
        try:
            if pretrained_policy_name_or_path:
                repo_path = snapshot_download(
                    pretrained_policy_name_or_path,
                    revision=revision,
                    allow_patterns=["*.json", "*.yaml"]
                )
                stats_path = os.path.join(repo_path, "stats.json")
                if os.path.exists(stats_path):
                    import json
                    with open(stats_path, 'r') as f:
                        self.stats = json.load(f)
        except Exception as e:
            print(f"통계 파일 로드 실패: {e}")
    
    def predict(self, 
                observation: Union[Dict[str, Any], torch.Tensor], 
                **kwargs) -> torch.Tensor:
        """
        액션 예측 (Diffusion 과정 포함)
        
        Args:
            observation: 관측 데이터 (딕셔너리 또는 텐서)
            **kwargs: 추가 인자들 (num_inference_steps 등)
            
        Returns:
            예측된 액션 시퀀스
        """
        if not self.is_loaded:
            raise RuntimeError("모델이 로드되지 않았습니다. load_model()을 먼저 호출하세요.")
        
        # Diffusion 추론 설정
        inference_config = self.config.get('inference', {})
        num_inference_steps = kwargs.get(
            'num_inference_steps', 
            inference_config.get('num_inference_steps', 20)
        )
        
        # 관측 데이터 전처리
        if isinstance(observation, dict):
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
        
        # Diffusion 추론 실행
        with torch.no_grad():
            # Diffusion Policy의 경우 num_inference_steps 파라미터 사용
            if hasattr(self.policy, 'num_inference_steps'):
                original_steps = self.policy.num_inference_steps
                self.policy.num_inference_steps = num_inference_steps
                actions = self.policy.select_action(batch_obs)
                self.policy.num_inference_steps = original_steps
            else:
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
    
    def set_num_inference_steps(self, num_steps: int) -> None:
        """
        Diffusion 추론 스텝 수 설정
        
        Args:
            num_steps: 추론 스텝 수
        """
        if hasattr(self.policy, 'num_inference_steps'):
            self.policy.num_inference_steps = num_steps
        self.config['inference']['num_inference_steps'] = num_steps


# 정책 팩토리에 등록
from .policy_factory import PolicyFactory
PolicyFactory.register_policy('diffusion', DiffusionPolicy)