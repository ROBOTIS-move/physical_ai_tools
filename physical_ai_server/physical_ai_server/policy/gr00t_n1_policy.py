from typing import Any, Dict, Union
import torch
import numpy as np
from .base_policy import BasePolicy
from gr00t.model.policy import PolicyModel
from gr00t.utils.config import load_config as load_gr00t_config
import yaml
import os


class GR00TN1Policy(BasePolicy):
    """
    GR00T N1 Policy Wrapper
    
    NVIDIA GR00T N1 정책을 통합 인터페이스로 래핑한 클래스입니다.
    """
    
    def __init__(self, config_path: str = None, config_dict: Dict[str, Any] = None):
        super().__init__(config_path, config_dict)
        self.policy = None
        self.gr00t_config = None
        self.sequence_buffer = []
        self.max_sequence_length = 50
        
    def load_model(self, checkpoint_path: str = None) -> None:
        """
        GR00T N1 모델 로드
        
        Args:
            checkpoint_path: 체크포인트 경로 (선택사항, config에서 가져올 수 있음)
        """
        model_config = self.config['model']
        checkpoint_path = checkpoint_path or model_config.get('checkpoint_path')
        gr00t_config_path = model_config.get('config_path')
        
        if not checkpoint_path:
            raise ValueError("checkpoint_path가 필요합니다.")
        
        # GR00T 설정 로드
        if gr00t_config_path and os.path.exists(gr00t_config_path):
            self.gr00t_config = load_gr00t_config(gr00t_config_path)
        else:
            # 기본 설정 사용
            self.gr00t_config = self._get_default_config()
        
        # 모델 로드
        self.policy = PolicyModel(self.gr00t_config)
        
        # 체크포인트 로드
        if os.path.exists(checkpoint_path):
            checkpoint = torch.load(checkpoint_path, map_location=self.device)
            self.policy.load_state_dict(checkpoint['model_state_dict'])
        else:
            raise FileNotFoundError(f"체크포인트를 찾을 수 없습니다: {checkpoint_path}")
        
        self.policy.to(self.device)
        self.policy.eval()
        self.is_loaded = True
        
        # 시퀀스 길이 설정
        inference_config = self.config.get('inference', {})
        self.max_sequence_length = inference_config.get('sequence_length', 50)
    
    def _get_default_config(self) -> Dict[str, Any]:
        """기본 GR00T 설정 반환"""
        return {
            'model': {
                'backbone': 'transformer',
                'hidden_dim': 512,
                'num_layers': 8,
                'num_heads': 8,
                'dropout': 0.1
            },
            'data': {
                'observation_dim': 256,
                'action_dim': 32,
                'sequence_length': 50
            }
        }
    
    def predict(self, 
                observation: Union[Dict[str, Any], torch.Tensor], 
                **kwargs) -> torch.Tensor:
        """
        액션 예측
        
        Args:
            observation: 관측 데이터
            **kwargs: 추가 인자들
            
        Returns:
            예측된 액션
        """
        if not self.is_loaded:
            raise RuntimeError("모델이 로드되지 않았습니다. load_model()을 먼저 호출하세요.")
        
        # 관측 데이터 전처리
        processed_obs = self.preprocess_observation(observation)
        
        # 시퀀스 버퍼에 추가
        self.sequence_buffer.append(processed_obs)
        if len(self.sequence_buffer) > self.max_sequence_length:
            self.sequence_buffer.pop(0)
        
        # 배치 형태로 변환
        if isinstance(processed_obs, dict):
            batch_obs = {}
            for key, value in processed_obs.items():
                if isinstance(value, torch.Tensor):
                    if value.dim() <= 2:
                        value = value.unsqueeze(0)  # 배치 차원 추가
                    batch_obs[key] = value.to(self.device)
        else:
            if isinstance(processed_obs, np.ndarray):
                processed_obs = torch.from_numpy(processed_obs).float()
            batch_obs = processed_obs.unsqueeze(0).to(self.device)
        
        # 추론 실행
        with torch.no_grad():
            if hasattr(self.policy, 'forward'):
                actions = self.policy.forward(batch_obs)
            else:
                actions = self.policy(batch_obs)
        
        return actions
    
    def reset(self) -> None:
        """정책 상태 리셋"""
        self.sequence_buffer = []
        if self.policy and hasattr(self.policy, 'reset'):
            self.policy.reset()
    
    def preprocess_observation(self, observation: Union[Dict[str, Any], torch.Tensor, np.ndarray]) -> torch.Tensor:
        """
        관측 데이터 전처리
        
        Args:
            observation: 원본 관측 데이터
            
        Returns:
            전처리된 관측 데이터
        """
        if isinstance(observation, dict):
            # 딕셔너리 형태의 관측을 텐서로 변환
            obs_list = []
            for key in sorted(observation.keys()):  # 일관된 순서 보장
                value = observation[key]
                if isinstance(value, np.ndarray):
                    value = torch.from_numpy(value).float()
                elif not isinstance(value, torch.Tensor):
                    value = torch.tensor(value).float()
                
                # 이미지 데이터 처리
                if key.endswith(('image', 'rgb', 'cam')) and value.dim() == 3:
                    if value.dtype == torch.uint8:
                        value = value.float() / 255.0
                    value = value.flatten()  # 평탄화
                elif value.dim() > 1:
                    value = value.flatten()
                
                obs_list.append(value)
            
            return torch.cat(obs_list, dim=0)
        
        elif isinstance(observation, np.ndarray):
            observation = torch.from_numpy(observation).float()
        elif not isinstance(observation, torch.Tensor):
            observation = torch.tensor(observation).float()
        
        return observation
    
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
        
        # 배치 차원 제거
        if action.ndim > 1 and action.shape[0] == 1:
            action = action.squeeze(0)
        
        # 액션 클리핑 (필요시)
        action_config = self.config.get('action', {})
        if 'min_action' in action_config and 'max_action' in action_config:
            action = np.clip(
                action,
                action_config['min_action'],
                action_config['max_action']
            )
        
        return action
    
    def get_sequence_buffer(self) -> list:
        """현재 시퀀스 버퍼 반환"""
        return self.sequence_buffer.copy()
    
    def set_sequence_length(self, length: int) -> None:
        """
        시퀀스 길이 설정
        
        Args:
            length: 새로운 시퀀스 길이
        """
        self.max_sequence_length = max(1, length)
        # 버퍼 크기 조정
        while len(self.sequence_buffer) > self.max_sequence_length:
            self.sequence_buffer.pop(0)
    
    def get_policy_info(self) -> Dict[str, Any]:
        """
        GR00T N1 정책의 특정 정보 반환
        
        Returns:
            정책 정보 딕셔너리
        """
        info = self.get_model_info()
        info.update({
            'sequence_length': self.max_sequence_length,
            'buffer_size': len(self.sequence_buffer),
            'gr00t_config': self.gr00t_config
        })
        return info


# 정책 팩토리에 등록
from .policy_factory import PolicyFactory
PolicyFactory.register_policy('gr00t_n1', GR00TN1Policy)