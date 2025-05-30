# Unified Policy Framework

통합 정책 프레임워크는 LeRobot과 GR00T N1의 다양한 정책들(ACT, Diffusion, Pi0, GR00T N1)을 하나의 일관된 인터페이스로 사용할 수 있게 해주는 프레임워크입니다.

## ✨ 주요 특징

- **통합 인터페이스**: 모든 정책 타입에 대한 공통 `BasePolicy` 추상 클래스
- **YAML 설정**: LeRobot의 Python 설정을 YAML로 변환하여 쉽게 편집 가능
- **정책 팩토리**: 자동 정책 생성 및 등록 시스템
- **확장 가능한 구조**: 새로운 오픈소스 정책을 쉽게 추가 가능

## 📁 프로젝트 구조

```
physical_ai_server/inference/policy/
├── __init__.py                 # 패키지 초기화 및 export
├── base_policy.py              # 추상 기본 정책 인터페이스
├── policy_factory.py           # 정책 팩토리 및 설정 관리자
├── act_policy.py              # ACT 정책 래퍼
├── diffusion_policy.py        # Diffusion 정책 래퍼  
├── pi0_policy.py              # Pi0 정책 래퍼
├── gr00t_n1_policy.py         # GR00T N1 정책 래퍼
├── class_diagram.md           # UML 클래스 다이어그램
└── configs/                   # YAML 설정 파일 템플릿
    ├── act_config.yaml
    ├── diffusion_config.yaml
    ├── pi0_config.yaml
    └── gr00t_n1_config.yaml
```

## 🚀 빠른 시작

### 1. 기본 사용법

```python
from physical_ai_server.inference.policy import PolicyFactory

# YAML 설정 파일로 정책 생성
policy = PolicyFactory.create_policy('act', config_path='configs/act_config.yaml')

# 모델 로드
policy.load_model()

# 추론 실행
observation = {
    'observation.images.top': image_tensor,
    'observation.state': state_tensor
}
action = policy.predict(observation)
```

### 2. 설정 딕셔너리 사용

```python
config = {
    'policy_type': 'diffusion',
    'device': 'cuda',
    'model': {
        'name': 'DiffusionPolicy',
        'pretrained_policy_name_or_path': 'lerobot/diffusion_pusht'
    }
}

policy = PolicyFactory.create_policy('diffusion', config_dict=config)
```

## 🤖 지원되는 정책들

### 1. ACT (Action Chunking Transformer)
- **소스**: LeRobot
- **구조**: Vision backbone + Transformer + VAE
- **용도**: 양손 조작, 순차적 액션
- **주요 기능**: Action chunking, 변분 인코딩

### 2. Diffusion Policy
- **소스**: LeRobot  
- **구조**: Vision backbone + U-Net + Noise scheduler
- **용도**: 복잡한 조작, 노이즈 견고 플래닝
- **주요 기능**: Denoising diffusion, 다단계 예측

### 3. Pi0 Policy
- **소스**: LeRobot
- **구조**: PaliGemma VLM + Action projector
- **용도**: 언어 조건부 조작
- **주요 기능**: 비전-언어 이해, flow matching

### 4. GR00T N1 Policy
- **소스**: Isaac-GR00T
- **구조**: Eagle backbone + Diffusion transformer
- **용도**: 휴머노이드 제어, embodied AI
- **주요 기능**: 다중 embodiment, 시퀀스 처리

## ⚙️ 설정 시스템

### YAML 설정 파일 예시

#### ACT Policy 설정
```yaml
# act_config.yaml
policy_type: act
device: cuda

model:
  name: ACTPolicy
  pretrained_policy_name_or_path: lerobot/act_aloha_mobile_base
  revision: main

inference:
  batch_size: 1
  num_inference_steps: 10
```

#### Diffusion Policy 설정
```yaml
# diffusion_config.yaml
policy_type: diffusion
device: cuda

model:
  name: DiffusionPolicy
  pretrained_policy_name_or_path: lerobot/diffusion_pusht
  revision: main

inference:
  batch_size: 1
  num_inference_steps: 20
```

#### GR00T N1 설정
```yaml
# gr00t_n1_config.yaml
policy_type: gr00t_n1
device: cuda

model:
  checkpoint_path: "/path/to/gr00t_checkpoint.pt"
  config_path: "/path/to/gr00t_config.yaml"

inference:
  batch_size: 1
  sequence_length: 50
```

## 🛠️ API 사용법

### PolicyFactory 클래스

```python
from physical_ai_server.inference.policy import PolicyFactory

# 사용 가능한 정책들 확인
available_policies = PolicyFactory.get_available_policies()
print(f"사용 가능한 정책들: {list(available_policies.keys())}")

# 설정 파일에서 정책 로드
policy = PolicyFactory.load_from_config_file('configs/act_config.yaml')

# 템플릿 설정 생성
template = ConfigManager.create_template_config('diffusion', 'my_diffusion_config.yaml')
```

### BasePolicy 인터페이스

모든 정책이 상속받는 기본 클래스입니다:

```python
# 필수 구현 메서드들
def load_model(self, checkpoint_path: str) -> None:
    """모델 로드"""
    pass

def predict(self, observation, **kwargs):
    """추론 실행"""
    pass

def reset(self) -> None:
    """정책 상태 리셋"""
    pass

# 공통 유틸리티 메서드들
def get_config(self) -> Dict[str, Any]:
    """현재 설정 반환"""

def get_device(self) -> torch.device:
    """현재 디바이스 반환"""

def is_model_loaded(self) -> bool:
    """모델 로드 상태 확인"""
```

## 🔧 새로운 정책 추가하기

### 1. 정책 클래스 생성

```python
from .base_policy import BasePolicy

class MyCustomPolicy(BasePolicy):
    def __init__(self, config_path: str = None, config_dict: Dict[str, Any] = None):
        super().__init__(config_path, config_dict)
        self.policy = None
    
    def load_model(self, checkpoint_path: str = None) -> None:
        # 모델 로드 로직 구현
        pass
        
    def predict(self, observation: Dict[str, Any], **kwargs) -> torch.Tensor:
        # 추론 로직 구현
        pass
        
    def reset(self) -> None:
        # 상태 리셋 로직 구현
        pass
```

### 2. 정책 등록

```python
# __init__.py에서 또는 모듈 로드시
from .policy_factory import PolicyFactory
PolicyFactory.register_policy('my_custom', MyCustomPolicy)
```

### 3. 설정 템플릿 추가

`policy_factory.py`의 `ConfigManager.create_template_config`에 새로운 정책 타입을 추가합니다.

## 📝 사용 예시

### 기본 추론 예시

```python
import torch
import numpy as np
from physical_ai_server.inference.policy import PolicyFactory

# ACT 정책 생성 및 로드
policy = PolicyFactory.create_policy('act', config_path='configs/act_config.yaml')
policy.load_model()

# 관측 데이터 준비
observation = {
    'observation.images.top': torch.randn(3, 224, 224),  # RGB 이미지
    'observation.state': torch.randn(14)  # 로봇 상태
}

# 추론 실행
action = policy.predict(observation)
print(f"예측된 액션: {action}")

# 정책 상태 리셋
policy.reset()
```

### 다중 정책 사용

```python
# 여러 정책을 동시에 사용
policies = {}
policy_types = ['act', 'diffusion', 'pi0']

for policy_type in policy_types:
    config_path = f'configs/{policy_type}_config.yaml'
    policies[policy_type] = PolicyFactory.create_policy(policy_type, config_path=config_path)
    # policies[policy_type].load_model()  # 실제 모델 경로 설정 후 주석 해제

# 앙상블 추론
observations = get_observation()  # 실제 관측 데이터
ensemble_actions = []

for name, policy in policies.items():
    if policy.is_model_loaded():
        action = policy.predict(observations)
        ensemble_actions.append(action)
        print(f"{name} 정책 액션: {action}")
```

### GR00T N1 시퀀스 처리

```python
# GR00T N1의 시퀀스 기능 활용
gr00t_policy = PolicyFactory.create_policy('gr00t_n1', config_path='configs/gr00t_n1_config.yaml')
# gr00t_policy.load_model()  # 실제 체크포인트 경로 설정 후 사용

# 시퀀스 길이 조정
gr00t_policy.set_sequence_length(100)

# 연속적인 추론
for timestep in range(1000):
    observation = get_observation_at_timestep(timestep)
    action = gr00t_policy.predict(observation)
    execute_action(action)
    
    # 매 100 스텝마다 시퀀스 버퍼 확인
    if timestep % 100 == 0:
        buffer_info = gr00t_policy.get_sequence_buffer()
        print(f"시퀀스 버퍼 크기: {len(buffer_info)}")
```

## 🔍 설정 파일 관리

### 설정 검증

```python
from physical_ai_server.inference.policy import ConfigManager

# 설정 파일 검증
try:
    config = ConfigManager.load_config('configs/act_config.yaml')
    ConfigManager.validate_config(config)
    print("설정 파일이 유효합니다.")
except ValueError as e:
    print(f"설정 오류: {e}")
```

### 템플릿 생성

```python
# 새로운 설정 템플릿 생성
template = ConfigManager.create_template_config('diffusion', 'my_diffusion_config.yaml')
print("템플릿이 생성되었습니다.")

# 설정 수정 후 저장
template['inference']['num_inference_steps'] = 50
ConfigManager.save_config(template, 'modified_diffusion_config.yaml')
```

## 🐛 문제 해결

### 일반적인 문제들

1. **ImportError**: 필요한 라이브러리가 설치되지 않음
   ```bash
   # LeRobot 설치
   pip install lerobot
   
   # GR00T 관련 라이브러리 설치 (필요시)
   pip install isaac-sim  # 또는 해당 패키지
   ```

2. **FileNotFoundError**: 체크포인트나 설정 파일을 찾을 수 없음
   ```python
   # 파일 경로 확인
   import os
   config_path = 'configs/act_config.yaml'
   if os.path.exists(config_path):
       print("설정 파일이 존재합니다.")
   else:
       print("설정 파일을 찾을 수 없습니다.")
   ```

3. **CUDA 메모리 부족**: GPU 메모리 부족
   ```yaml
   # 설정 파일에서 배치 크기 줄이기
   inference:
     batch_size: 1  # 기본값에서 줄이기
   
   # 또는 CPU 모드로 전환
   device: cpu
   ```

### 디버깅 모드

```python
import logging

# 자세한 로그 활성화
logging.basicConfig(level=logging.DEBUG)

# 정책 정보 확인
policy = PolicyFactory.create_policy('act')
print(f"정책 정보: {policy.get_model_info()}")

# 사용 가능한 정책들 확인
available = PolicyFactory.get_available_policies()
print(f"등록된 정책들: {list(available.keys())}")
```

## 🚀 고급 사용법

### 커스텀 전처리/후처리

```python
class CustomACTPolicy(ACTPolicy):
    def preprocess_observation(self, observation):
        # 커스텀 전처리 로직
        processed = super().preprocess_observation(observation)
        
        # 예: 이미지 정규화
        if 'image' in processed:
            processed['image'] = (processed['image'] - 0.5) / 0.5
        
        return processed
    
    def postprocess_action(self, action):
        # 커스텀 후처리 로직
        processed = super().postprocess_action(action)
        
        # 예: 액션 스케일링
        processed = processed * 2.0
        
        return processed

# 커스텀 정책 등록
PolicyFactory.register_policy('custom_act', CustomACTPolicy)
```

### 배치 처리 최적화

```python
# 여러 관측을 효율적으로 배치 처리
observations = [obs1, obs2, obs3]  # 여러 관측 데이터

# 배치로 묶어서 처리 (정책이 지원하는 경우)
if hasattr(policy, 'predict_batch'):
    actions = policy.predict_batch(observations)
else:
    # 개별 처리
    actions = [policy.predict(obs) for obs in observations]
```

## 📄 라이선스

이 프레임워크는 여러 오픈소스 프로젝트를 통합합니다:
- **LeRobot**: Apache 2.0 License
- **GR00T**: Isaac-GR00T 저장소의 라이선스 확인
- **Framework Code**: MIT License

## 🙏 감사의 말

- **LeRobot 팀**: 훌륭한 정책 구현들
- **NVIDIA Isaac Lab**: GR00T N1 정책
- **Hugging Face**: 기반 ML 인프라
- **오픈소스 커뮤니티**: 로보틱스 정책 연구

---

## 🏗️ 아키텍처 다이어그램

프레임워크의 전체 클래스 구조는 [`class_diagram.md`](class_diagram.md)에서 UML 다이어그램으로 확인할 수 있습니다.

더 많은 예시와 자세한 문서는 각 정책 구현 파일을 참조하세요.
