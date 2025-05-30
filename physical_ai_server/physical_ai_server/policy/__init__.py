"""
Unified Policy Framework

이 패키지는 LeRobot과 GR00T N1의 다양한 정책들을 통합하여
일관된 인터페이스로 사용할 수 있도록 하는 프레임워크입니다.

사용 예시:
    # YAML 설정으로 정책 생성
    from physical_ai_server.inference.policy import PolicyFactory
    
    policy = PolicyFactory.create_policy('act', config_path='act_config.yaml')
    policy.load_model()
    action = policy.predict(observation)
    
    # 또는 설정 딕셔너리로 생성
    config = {
        'policy_type': 'diffusion',
        'device': 'cuda',
        'model': {
            'name': 'DiffusionPolicy',
            'pretrained_policy_name_or_path': 'lerobot/diffusion_pusht'
        }
    }
    policy = PolicyFactory.create_policy('diffusion', config_dict=config)
"""

from .base_policy import BasePolicy
from .model_config_manager import ModelConfigManager
from .policy_factory import PolicyFactory, ConfigManager

# Import all policy classes to auto-register them with factory
from .act_policy import ACTPolicy
from .diffusion_policy import DiffusionPolicy
from .pi0_policy import Pi0Policy
from .gr00t_n1_policy import GR00TN1Policy

__all__ = [
    'BasePolicy',
    'ModelConfigManager',
    'PolicyFactory', 
    'ConfigManager',
    'ACTPolicy',
    'DiffusionPolicy', 
    'Pi0Policy',
    'GR00TN1Policy'
]

__version__ = '1.0.0'

def get_available_policies():
    """사용 가능한 모든 정책 타입 반환"""
    return list(PolicyFactory.get_available_policies().keys())

def create_template_config(policy_type: str, save_path: str = None):
    """정책 타입별 템플릿 설정 생성"""
    return ConfigManager.create_template_config(policy_type, save_path)

def load_policy_from_config(config_path: str):
    """YAML 설정 파일에서 정책 로드"""
    return PolicyFactory.load_from_config_file(config_path)
