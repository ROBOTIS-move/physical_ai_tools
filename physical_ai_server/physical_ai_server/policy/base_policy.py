from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union, Tuple
import torch
import numpy as np
from pathlib import Path
import yaml
import logging
from .model_config_manager import ModelConfigManager


class BasePolicy(ABC):
    """
    Enhanced unified policy interface class with advanced configuration management
    
    All policies (ACT, Diffusion, Pi0, GR00T N1, etc.) must inherit from this abstract class.
    This provides a consistent interface for using various open-source policies with
    enhanced configuration management including automatic pretrained config loading.
    """
    
    def __init__(self, 
                 config_path: Optional[str] = None, 
                 config_dict: Optional[Dict[str, Any]] = None,
                 pretrained_model_path: Optional[str] = None,
                 merge_strategy: str = "user_priority"):
        """
        Initialize policy with enhanced configuration management
        
        Args:
            config_path: YAML configuration file path
            config_dict: Configuration dictionary (used when config_path is not provided)
            pretrained_model_path: Path to pretrained model for automatic config loading
            merge_strategy: Strategy for merging pretrained and user configs
                - "user_priority": User config overrides pretrained config (default)
                - "pretrained_priority": Pretrained config takes precedence
                - "smart_merge": Intelligent merging based on field types
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config_manager = ModelConfigManager()
        self.pretrained_model_path = pretrained_model_path
        
        # Load and merge configurations using enhanced config management
        self.config = self._load_enhanced_config(
            config_path, config_dict, pretrained_model_path, merge_strategy
        )
        
        self.model = None
        self.device = torch.device(self.config.get('device', 'cuda' if torch.cuda.is_available() else 'cpu'))
        self.is_loaded = False
        self.original_user_config = config_dict.copy() if config_dict else {}
        
    def _load_enhanced_config(self, 
                            config_path: Optional[str], 
                            config_dict: Optional[Dict[str, Any]],
                            pretrained_model_path: Optional[str],
                            merge_strategy: str) -> Dict[str, Any]:
        """
        Load configuration using enhanced configuration management
        
        This method automatically loads pretrained model configurations and merges
        them intelligently with user-provided configurations.
        """
        # Get policy type for validation
        policy_type = self._get_policy_type()
        
        # Load basic user configuration
        user_config = {}
        if config_path:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f)
        elif config_dict:
            user_config = config_dict.copy()
        
        # Create enhanced configuration
        enhanced_config = self.config_manager.create_enhanced_config(
            model_path=pretrained_model_path,
            user_config=user_config,
            policy_type=policy_type,
            merge_strategy=merge_strategy
        )
        
        self.logger.info(f"Loaded enhanced configuration for {policy_type} policy")
        return enhanced_config
    
    def _get_policy_type(self) -> str:
        """
        Extract policy type from class name
        
        Returns:
            Policy type string (e.g., 'act', 'diffusion', 'pi0', 'gr00t_n1')
        """
        class_name = self.__class__.__name__.lower()
        if 'act' in class_name:
            return 'act'
        elif 'diffusion' in class_name:
            return 'diffusion'
        elif 'pi0' in class_name:
            return 'pi0'
        elif 'gr00t' in class_name:
            return 'gr00t_n1'
        else:
            return 'unknown'
    
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
        """
        Get comprehensive model information including configuration details
        
        Returns:
            Dictionary containing detailed model information
        """
        info = {
            'policy_type': self._get_policy_type(),
            'class_name': self.__class__.__name__,
            'device': str(self.device),
            'is_loaded': self.is_loaded,
            'pretrained_model_path': self.pretrained_model_path,
            'config_summary': self._get_config_summary(),
            'model_parameters': self._get_model_parameters() if self.is_loaded else None
        }
        return info
    
    def _get_config_summary(self) -> Dict[str, Any]:
        """
        Get a summary of key configuration parameters
        
        Returns:
            Dictionary containing key configuration information
        """
        summary = {
            'device': self.config.get('device'),
            'policy_type': self.config.get('policy_type')
        }
        
        # Add model-specific configuration summary
        if 'model' in self.config:
            model_config = self.config['model']
            summary['model_config'] = {
                'pretrained_path': model_config.get('pretrained_policy_name_or_path'),
                'revision': model_config.get('revision'),
                'backbone': model_config.get('backbone'),
                'hidden_dim': model_config.get('hidden_dim'),
                'chunk_size': model_config.get('chunk_size')
            }
        
        if 'inference' in self.config:
            summary['inference_config'] = self.config['inference']
        
        return summary
    
    def _get_model_parameters(self) -> Dict[str, Any]:
        """
        Get model parameter information if model is loaded
        
        Returns:
            Dictionary containing model parameter statistics
        """
        if not self.is_loaded or self.model is None:
            return None
        
        try:
            total_params = sum(p.numel() for p in self.model.parameters())
            trainable_params = sum(p.numel() for p in self.model.parameters() if p.requires_grad)
            
            return {
                'total_parameters': total_params,
                'trainable_parameters': trainable_params,
                'model_size_mb': total_params * 4 / (1024 * 1024),  # Assuming float32
                'device': str(next(self.model.parameters()).device) if total_params > 0 else str(self.device)
            }
        except Exception as e:
            self.logger.warning(f"Failed to get model parameters: {e}")
            return None
    
    def update_config(self, 
                     new_config: Dict[str, Any], 
                     merge_with_pretrained: bool = True) -> None:
        """
        Update the current configuration with new parameters
        
        Args:
            new_config: New configuration parameters to merge
            merge_with_pretrained: Whether to re-merge with pretrained config
        """
        if merge_with_pretrained and self.pretrained_model_path:
            # Re-merge with pretrained config
            updated_user_config = self.original_user_config.copy()
            updated_user_config.update(new_config)
            
            self.config = self.config_manager.create_enhanced_config(
                model_path=self.pretrained_model_path,
                user_config=updated_user_config,
                policy_type=self._get_policy_type(),
                merge_strategy="user_priority"
            )
        else:
            # Simple update
            self.config.update(new_config)
        
        # Update device if changed
        if 'device' in new_config:
            self.device = torch.device(new_config['device'])
            if self.is_loaded and self.model is not None:
                self.model.to(self.device)
        
        self.logger.info("Configuration updated successfully")
    
    def save_current_config(self, save_path: str) -> None:
        """
        Save the current configuration to a file
        
        Args:
            save_path: Path where to save the configuration
        """
        self.config_manager.save_config(self.config, save_path)
        self.logger.info(f"Current configuration saved to: {save_path}")
    
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