from typing import Dict, Any, Type
import yaml
from pathlib import Path
from .base_policy import BasePolicy


class PolicyFactory:
    """
    정책 팩토리 클래스
    
    YAML 설정을 기반으로 다양한 정책을 생성하고 관리합니다.
    새로운 정책을 쉽게 추가할 수 있도록 설계되었습니다.
    """
    
    _policy_registry: Dict[str, Type[BasePolicy]] = {}
    
    @classmethod
    def register_policy(cls, policy_name: str, policy_class: Type[BasePolicy]) -> None:
        """
        새로운 정책 등록
        
        Args:
            policy_name: 정책 이름
            policy_class: 정책 클래스
        """
        cls._policy_registry[policy_name] = policy_class
        print(f"정책 '{policy_name}' 등록됨: {policy_class.__name__}")
    
    @classmethod
    def create_policy(cls, 
                     policy_type: str, 
                     config_path: str = None, 
                     config_dict: Dict[str, Any] = None,
                     pretrained_model_path: str = None,
                     merge_strategy: str = "user_priority") -> BasePolicy:
        """
        Create policy with enhanced configuration management
        
        Args:
            policy_type: Policy type (e.g., 'act', 'diffusion', 'pi0', 'gr00t_n1')
            config_path: YAML configuration file path
            config_dict: Configuration dictionary
            pretrained_model_path: Path to pretrained model for auto-config loading
            merge_strategy: Strategy for merging configurations
                - "user_priority": User config overrides pretrained config (default)
                - "pretrained_priority": Pretrained config takes precedence
                - "smart_merge": Intelligent merging based on field types
            
        Returns:
            Created policy instance with enhanced configuration
        """
        if policy_type not in cls._policy_registry:
            available_policies = list(cls._policy_registry.keys())
            raise ValueError(f"Unknown policy type: {policy_type}. "
                           f"Available policies: {available_policies}")
        
        policy_class = cls._policy_registry[policy_type]
        
        # Create policy with enhanced configuration support
        return policy_class(
            config_path=config_path, 
            config_dict=config_dict,
            pretrained_model_path=pretrained_model_path,
            merge_strategy=merge_strategy
        )
    
    @classmethod
    def get_available_policies(cls) -> Dict[str, Type[BasePolicy]]:
        """등록된 모든 정책 반환"""
        return cls._policy_registry.copy()
    
    @classmethod
    def load_from_config_file(cls, config_path: str) -> BasePolicy:
        """
        YAML 설정 파일에서 정책 로드
        
        Args:
            config_path: YAML 설정 파일 경로
            
        Returns:
            생성된 정책 인스턴스
        """
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        policy_type = config.get('policy_type')
        if not policy_type:
            raise ValueError("설정 파일에 'policy_type' 필드가 없습니다.")
        
        return cls.create_policy(policy_type, config_path=config_path)


class ConfigManager:
    """
    설정 관리 클래스
    
    YAML 설정 파일의 검증, 로드, 저장을 담당합니다.
    """
    
    @staticmethod
    def load_config(config_path: str) -> Dict[str, Any]:
        """
        YAML 설정 파일 로드
        
        Args:
            config_path: 설정 파일 경로
            
        Returns:
            설정 딕셔너리
        """
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        ConfigManager.validate_config(config)
        return config
    
    @staticmethod
    def save_config(config: Dict[str, Any], config_path: str) -> None:
        """
        설정을 YAML 파일로 저장
        
        Args:
            config: 설정 딕셔너리
            config_path: 저장할 파일 경로
        """
        config_path = Path(config_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
    
    @staticmethod
    def validate_config(config: Dict[str, Any]) -> None:
        """
        설정 검증
        
        Args:
            config: 검증할 설정 딕셔너리
        """
        required_fields = ['policy_type', 'model']
        
        for field in required_fields:
            if field not in config:
                raise ValueError(f"필수 설정 필드가 없습니다: {field}")
        
        # 정책별 추가 검증
        policy_type = config['policy_type']
        model_config = config['model']
        
        if policy_type in ['act', 'diffusion', 'pi0']:
            # LeRobot 정책들의 공통 필수 필드
            required_model_fields = ['name', 'pretrained_policy_name_or_path']
            for field in required_model_fields:
                if field not in model_config:
                    raise ValueError(f"모델 설정에 필수 필드가 없습니다: {field}")
        
        elif policy_type == 'gr00t_n1':
            # GR00T N1 정책의 필수 필드
            required_model_fields = ['checkpoint_path']
            for field in required_model_fields:
                if field not in model_config:
                    raise ValueError(f"GR00T N1 모델 설정에 필수 필드가 없습니다: {field}")
    
    @staticmethod
    def create_template_config(policy_type: str, save_path: str = None) -> Dict[str, Any]:
        """
        정책 타입별 템플릿 설정 생성
        
        Args:
            policy_type: 정책 타입
            save_path: 저장 경로 (선택사항)
            
        Returns:
            템플릿 설정 딕셔너리
        """
        templates = {
            'act': {
                'policy_type': 'act',
                'device': 'cuda',
                'model': {
                    'name': 'ACTPolicy',
                    'pretrained_policy_name_or_path': 'lerobot/act_aloha_mobile_base',
                    'revision': 'main'
                },
                'inference': {
                    'batch_size': 1,
                    'num_inference_steps': 10
                }
            },
            'diffusion': {
                'policy_type': 'diffusion',
                'device': 'cuda',
                'model': {
                    'name': 'DiffusionPolicy',
                    'pretrained_policy_name_or_path': 'lerobot/diffusion_pusht',
                    'revision': 'main'
                },
                'inference': {
                    'batch_size': 1,
                    'num_inference_steps': 20
                }
            },
            'pi0': {
                'policy_type': 'pi0',
                'device': 'cuda',
                'model': {
                    'name': 'Pi0Policy',
                    'pretrained_policy_name_or_path': 'physicsai/pi0-pusht',
                    'revision': 'main'
                },
                'inference': {
                    'batch_size': 1
                }
            },
            'gr00t_n1': {
                'policy_type': 'gr00t_n1',
                'device': 'cuda',
                'model': {
                    'checkpoint_path': '/path/to/gr00t_checkpoint.pt',
                    'config_path': '/path/to/gr00t_config.yaml'
                },
                'inference': {
                    'batch_size': 1,
                    'sequence_length': 50
                }
            }
        }
        
        if policy_type not in templates:
            available_types = list(templates.keys())
            raise ValueError(f"알 수 없는 정책 타입: {policy_type}. "
                           f"사용 가능한 타입: {available_types}")
        
        template = templates[policy_type]
        
        if save_path:
            ConfigManager.save_config(template, save_path)
            print(f"템플릿 설정이 저장되었습니다: {save_path}")
        
        return template
