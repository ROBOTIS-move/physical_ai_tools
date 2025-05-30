from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union, Tuple
import torch
import numpy as np
from pathlib import Path
import yaml


class BasePolicy(ABC):
    """
    통합 정책의 기본 인터페이스 클래스
    
    모든 정책(ACT, Diffusion, Pi0, GR00T N1 등)이 상속받아야 하는 추상 클래스입니다.
    이를 통해 다양한 오픈소스 정책들을 일관된 방식으로 사용할 수 있습니다.
    """
    
    def __init__(self, config_path: Optional[str] = None, config_dict: Optional[Dict[str, Any]] = None):
        """
        정책 초기화
        
        Args:
            config_path: YAML 설정 파일 경로
            config_dict: 설정 딕셔너리 (config_path가 없을 때 사용)
        """
        self.config = self._load_config(config_path, config_dict)
        self.model = None
        self.device = torch.device(self.config.get('device', 'cuda' if torch.cuda.is_available() else 'cpu'))
        self.is_loaded = False
        
    def _load_config(self, config_path: Optional[str], config_dict: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """설정 로드"""
        if config_path:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        elif config_dict:
            return config_dict
        else:
            raise ValueError("config_path 또는 config_dict 중 하나는 제공되어야 합니다.")
    
    @abstractmethod
    def load_model(self, checkpoint_path: str) -> None:
        """
        모델 로드 (추상 메서드)
        
        Args:
            checkpoint_path: 체크포인트 파일 경로
        """
        pass
    
    @abstractmethod
    def predict(self, 
                observation: Union[Dict[str, Any], torch.Tensor, np.ndarray], 
                **kwargs) -> Union[torch.Tensor, np.ndarray, Dict[str, Any]]:
        """
        예측 수행 (추상 메서드)
        
        Args:
            observation: 관측 데이터
            **kwargs: 추가 인자들
            
        Returns:
            액션 또는 예측 결과
        """
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """정책 상태 리셋 (추상 메서드)"""
        pass
    
    def get_config(self) -> Dict[str, Any]:
        """현재 설정 반환"""
        return self.config
    
    def get_device(self) -> torch.device:
        """현재 디바이스 반환"""
        return self.device
    
    def is_model_loaded(self) -> bool:
        """모델 로드 상태 확인"""
        return self.is_loaded
    
    def get_model_info(self) -> Dict[str, Any]:
        """모델 정보 반환"""
        return {
            'policy_type': self.__class__.__name__,
            'device': str(self.device),
            'is_loaded': self.is_loaded,
            'config': self.config
        }
    
    def preprocess_observation(self, observation: Any) -> Any:
        """
        관측 데이터 전처리 (기본 구현, 필요시 오버라이드)
        
        Args:
            observation: 원본 관측 데이터
            
        Returns:
            전처리된 관측 데이터
        """
        return observation
    
    def postprocess_action(self, action: Any) -> Any:
        """
        액션 후처리 (기본 구현, 필요시 오버라이드)
        
        Args:
            action: 원본 액션
            
        Returns:
            후처리된 액션
        """
        return action