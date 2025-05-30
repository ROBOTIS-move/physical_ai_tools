# Unified Policy Framework - Class Diagram

```mermaid
classDiagram
    %% 추상 기본 클래스
    class BasePolicy {
        <<abstract>>
        -config: Dict[str, Any]
        -model: Any
        -device: torch.device
        -is_loaded: bool
        
        +__init__(config_path?, config_dict?)
        +load_model(checkpoint_path)* 
        +predict(observation, **kwargs)*
        +reset()*
        +get_config() Dict[str, Any]
        +get_device() torch.device
        +is_model_loaded() bool
        +get_model_info() Dict[str, Any]
        +preprocess_observation(observation) Any
        +postprocess_action(action) Any
        -_load_config(config_path?, config_dict?) Dict[str, Any]
    }
    
    %% 정책 구현 클래스들
    class ACTPolicy {
        -policy: LeRobotACTPolicy
        -stats: Dict
        
        +__init__(config_path?, config_dict?)
        +load_model(checkpoint_path?)
        +predict(observation, **kwargs) torch.Tensor
        +reset()
        +preprocess_observation(observation) Dict[str, Any]
        +postprocess_action(action) np.ndarray
    }
    
    class DiffusionPolicy {
        -policy: LeRobotDiffusionPolicy
        -stats: Dict
        
        +__init__(config_path?, config_dict?)
        +load_model(checkpoint_path?)
        +predict(observation, **kwargs) torch.Tensor
        +reset()
        +preprocess_observation(observation) Dict[str, Any]
        +postprocess_action(action) np.ndarray
    }
    
    class Pi0Policy {
        -policy: LeRobotPi0Policy
        -stats: Dict
        
        +__init__(config_path?, config_dict?)
        +load_model(checkpoint_path?)
        +predict(observation, **kwargs) torch.Tensor
        +reset()
        +preprocess_observation(observation) Dict[str, Any]
        +postprocess_action(action) np.ndarray
        +get_policy_info() Dict[str, Any]
    }
    
    class GR00TN1Policy {
        -policy: PolicyModel
        -gr00t_config: Dict
        -sequence_buffer: List
        -max_sequence_length: int
        
        +__init__(config_path?, config_dict?)
        +load_model(checkpoint_path?)
        +predict(observation, **kwargs) torch.Tensor
        +reset()
        +preprocess_observation(observation) torch.Tensor
        +postprocess_action(action) np.ndarray
        +get_sequence_buffer() List
        +set_sequence_length(length)
        +get_policy_info() Dict[str, Any]
        -_get_default_config() Dict[str, Any]
    }
    
    %% 팩토리 및 관리 클래스들
    class PolicyFactory {
        <<singleton>>
        -_policy_registry: Dict[str, Type[BasePolicy]]
        
        +register_policy(policy_name, policy_class)$
        +create_policy(policy_type, config_path?, config_dict?)$ BasePolicy
        +get_available_policies()$ Dict[str, Type[BasePolicy]]
        +load_from_config_file(config_path)$ BasePolicy
    }
    
    class ConfigManager {
        <<utility>>
        +load_config(config_path)$ Dict[str, Any]
        +save_config(config, config_path)$
        +validate_config(config)$
        +create_template_config(policy_type, save_path?)$ Dict[str, Any]
    }
    
    %% 외부 라이브러리 클래스들 (simplified)
    class LeRobotACTPolicy {
        <<external>>
        +from_pretrained(path)$
        +select_action(observation)
        +to(device)
        +eval()
    }
    
    class LeRobotDiffusionPolicy {
        <<external>>
        +from_pretrained(path)$
        +select_action(observation)
        +to(device)
        +eval()
    }
    
    class LeRobotPi0Policy {
        <<external>>
        +from_pretrained(path)$
        +select_action(observation)
        +to(device)
        +eval()
    }
    
    class PolicyModel {
        <<external>>
        +__init__(config)
        +load_state_dict(state_dict)
        +forward(observation)
        +to(device)
        +eval()
    }
    
    %% 상속 관계
    BasePolicy <|-- ACTPolicy
    BasePolicy <|-- DiffusionPolicy
    BasePolicy <|-- Pi0Policy
    BasePolicy <|-- GR00TN1Policy
    
    %% 조합 관계
    ACTPolicy *-- LeRobotACTPolicy : uses
    DiffusionPolicy *-- LeRobotDiffusionPolicy : uses
    Pi0Policy *-- LeRobotPi0Policy : uses
    GR00TN1Policy *-- PolicyModel : uses
    
    %% 의존 관계
    PolicyFactory ..> BasePolicy : creates
    PolicyFactory ..> ACTPolicy : creates
    PolicyFactory ..> DiffusionPolicy : creates
    PolicyFactory ..> Pi0Policy : creates
    PolicyFactory ..> GR00TN1Policy : creates
    PolicyFactory ..> ConfigManager : uses
    
    %% 등록 관계
    ACTPolicy ..> PolicyFactory : registers with
    DiffusionPolicy ..> PolicyFactory : registers with
    Pi0Policy ..> PolicyFactory : registers with
    GR00TN1Policy ..> PolicyFactory : registers with

    %% 클래스 노트
    note for BasePolicy "모든 정책의 추상 기본 클래스\n공통 인터페이스 정의"
    note for PolicyFactory "정책 생성 및 등록 관리\n팩토리 패턴 구현"
    note for ConfigManager "YAML 설정 파일 관리\n검증 및 템플릿 생성"
```

## 클래스 관계 설명

### 🏗️ 상속 구조
- **BasePolicy** (추상 클래스): 모든 정책의 공통 인터페이스
- **구체 정책들**: ACTPolicy, DiffusionPolicy, Pi0Policy, GR00TN1Policy

### 🔧 주요 패턴
- **Factory Pattern**: PolicyFactory가 정책 생성 담당
- **Strategy Pattern**: BasePolicy 인터페이스로 정책 교체 가능
- **Template Method**: BasePolicy의 공통 메서드들

### 📦 의존성
- **Internal**: 각 정책은 해당하는 외부 라이브러리 모델을 포함
- **External**: LeRobot 및 GR00T 라이브러리의 실제 모델들
- **Configuration**: ConfigManager가 YAML 설정 관리

### 🔄 등록 시스템
- 각 정책 클래스는 모듈 로드시 PolicyFactory에 자동 등록
- 런타임에 새로운 정책 타입 추가 가능
