# Physical AI Tools - Docker Architecture (Revised)

## Overview

Physical AI Tools는 4개의 Docker 컨테이너로 구성됩니다:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Host Machine                                    │
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │ physical_ai_    │                                                        │
│  │ manager (UI)    │◄────── HTTP (rosbridge) ──────┐                        │
│  │ React + Nginx   │                               │                        │
│  │ Port: 80        │                               │                        │
│  └─────────────────┘                               │                        │
│                                                    │                        │
│  ┌─────────────────┐      Zenoh P2P + SHM      ┌───┴───────────┐            │
│  │   lerobot       │◄─────────────────────────►│ physical_ai_  │            │
│  │   server        │      (zenoh_ros2_sdk)     │ server (ROS2) │            │
│  │  LeRobot +      │                           │               │            │
│  │  Zenoh SDK      │                           │ rmw_zenoh_cpp │            │
│  └─────────────────┘                           └───────────────┘            │
│                                                        ▲                    │
│  ┌─────────────────┐      Zenoh P2P + SHM             │                    │
│  │   groot         │◄─────────────────────────────────┘                    │
│  │   server        │      (zenoh_ros2_sdk)                                 │
│  │  GR00T +        │                                                       │
│  │  Zenoh SDK      │                                                       │
│  └─────────────────┘                                                       │
│                                                                             │
│  ※ lerobot과 groot는 서로 직접 통신하지 않음 (physical_ai_server 경유)      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 통신 구조 설명
- **physical_ai_manager ↔ physical_ai_server**: rosbridge를 통한 WebSocket/HTTP 통신
- **physical_ai_server ↔ lerobot**: Zenoh P2P + zenoh_ros2_sdk
- **physical_ai_server ↔ groot**: Zenoh P2P + zenoh_ros2_sdk
- **lerobot ↔ groot**: 직접 통신 없음 (필요 시 physical_ai_server 경유)

---

## Zenoh 통신 모드 설명

### Peer Mode (현재 사용)
- 모든 노드가 직접 P2P 통신
- Multicast scouting (224.0.0.224:7446)으로 자동 발견
- **장점**: 라우터 없이 직접 통신, 낮은 지연시간 (Client 대비 70% 낮음)
- **단점**: 각 노드가 여러 세션 유지 필요

### Client Mode
- 단일 라우터에 연결하여 통신
- 리소스 제약 디바이스에 적합
- **장점**: 단순한 구조, 적은 메모리 사용
- **단점**: 라우터 의존성, 상대적으로 높은 지연시간

### Router Mode
- 클라이언트들 간 데이터 라우팅
- 서로 다른 네트워크 연결 시 사용

**현재 설정**: Client Mode (외부 Router 연결)

```
┌─────────────────┐
│  외부 관리      │
│  Zenoh Router   │◄──── ros2 run rmw_zenoh_cpp rmw_zenohd
│  (rmw_zenohd)   │      (다른 Docker 컨테이너에서 실행)
└────────┬────────┘
         │
    ┌────┴────┬─────────────┐
    ▼         ▼             ▼
┌───────┐ ┌───────┐ ┌───────────┐
│ ROS2  │ │lerobot│ │   groot   │
│Server │ │       │ │           │
│(Client)│ │(Client)│ │ (Client)  │
└───────┘ └───────┘ └───────────┘
```

- Zenoh Router는 **외부에서 관리** (우리 컨테이너에서 실행 안 함)
- 모든 컨테이너는 Client로 Router에 연결
- Shared Memory 활성화: `transport/shared_memory/enabled=true`

Sources:
- [Zenoh Deployment Guide](https://zenoh.io/docs/getting-started/deployment/)
- [Zenoh Peer-to-Peer Performance](https://zenoh.io/blog/2025-07-11-zenoh-pico-peer-to-peer-unicast/)

---

## 1. physical_ai_manager (React UI)

### 역할
- 웹 기반 사용자 인터페이스
- 데이터 수집, 학습, 추론 명령 전송
- rosbridge를 통해 physical_ai_server와 통신

### Base Image
| Architecture | Base Image |
|--------------|------------|
| All | `node:22` (build) → `nginx:1.27.5-alpine` (runtime) |

### 특징
- Multi-stage build로 경량화
- **포트: 80** (표준 HTTP 포트)
- 아키텍처 독립적

### TODO
- [ ] 포트를 8080에서 80으로 변경

---

## 2. physical_ai_server (ROS2 + Zenoh)

### 역할
- ROS2 기반 로봇 제어
- Zenoh (rmw_zenoh_cpp)를 통한 lerobot/groot과 통신
- 데이터 수집 (rosbag 녹화)
- 하드웨어 인터페이스

### Base Image
| Architecture | Base Image |
|--------------|------------|
| AMD64 | `robotis/ros:jazzy-ros-base-torch2.7.0-cuda12.8.0` |
| ARM64 (Jetson) | `robotis/ros:jazzy-ros-base-torch2.7.0-cuda12.8.0` |

### 현재 빌드 방식의 문제점

현재 Dockerfile은 GitHub에서 clone하는 방식:
```dockerfile
RUN git clone -b feature-1.0.0 https://github.com/ROBOTIS-GIT/physical_ai_tools.git --recursive
```

**문제점**:
1. 로컬 변경사항이 반영 안 됨
2. 매번 전체 clone 필요
3. 네트워크 의존성

### 개선 방안: Volume Mount 방식

docker-compose.yml에서 이미 볼륨 마운트가 되어 있음:
```yaml
volumes:
  - ../:/root/ros2_ws/src/physical_ai_tools/
```

**제안**: Dockerfile에서 clone 제거하고 볼륨 마운트된 코드 사용
- 개발 중에는 볼륨 마운트로 실시간 반영
- 배포 시에는 COPY 또는 이미지 빌드

### LeRobot 제거

현재 physical_ai_server에 LeRobot이 설치되어 있지만, 별도 lerobot 컨테이너가 있으므로 제거 필요:
```dockerfile
# 제거 대상
RUN cd ${COLCON_WS}/src/physical_ai_tools/third_party/lerobot/lerobot && pip install -e .
RUN pip install -e ".[smolvla]"
```

### 주요 구성요소 (정리 후)
- **ROS2 Jazzy**: 로봇 미들웨어
- **rmw_zenoh_cpp**: Zenoh 기반 ROS2 통신
- **PyTorch + CUDA**: GPU 가속 (필요 시)

---

## 3. lerobot (LeRobot Server)

### 역할
- HuggingFace LeRobot 프레임워크 실행
- 학습 (ACT, Diffusion Policy, SmolVLA 등)
- 추론 (정책 실행)
- Zenoh SDK를 통해 physical_ai_server와 통신

### Base Image

| Architecture | Base Image | 검증 상태 |
|--------------|------------|-----------|
| AMD64 | `nvcr.io/nvidia/pytorch:24.12-py3` | ✅ 사용 가능 |
| ARM64 (Jetson) | `nvcr.io/nvidia/l4t-jetpack:r36.4.0` | ✅ 사용 가능 (JetPack 6.x) |

### Jetson PyTorch 설치
```dockerfile
# Jetson AI Lab에서 제공하는 CUDA 지원 PyTorch
RUN uv pip install torch torchvision \
    --index-url https://pypi.jetson-ai-lab.io/jp6/cu126/+simple
```
- JetPack 6.x + CUDA 12.6 호환
- Jetson Orin 시리즈 지원

### LeRobot Optional Dependencies 분석

현재 설치되는 것들:
```
.[dynamixel,gamepad,hopejr,lekiwi,reachy2,kinematics]  # 로봇/하드웨어
.[smolvla,xvla,hilserl,async,dev,test]                  # 정책/개발
.[video_benchmark,aloha,pusht,phone,libero,metaworld,sarm,peft]  # 시뮬/기타
```

| Extra | 용도 | 학습/추론에 필요? |
|-------|------|------------------|
| `dynamixel` | Dynamixel 모터 제어 | ❌ (서버에서 제어) |
| `gamepad` | 게임패드 입력 | ❌ |
| `hopejr` | HopeJr 로봇 | ❌ |
| `lekiwi` | LeKiwi 로봇 | ❌ |
| `reachy2` | Reachy2 로봇 | ❌ |
| `kinematics` | 역기구학 | ❌ |
| `smolvla` | SmolVLA 정책 | ✅ |
| `xvla` | X-VLA 정책 | ✅ |
| `hilserl` | HIL-SERL 정책 | ✅ |
| `async` | 비동기 추론 | ✅ |
| `dev` | 개발 도구 | ❌ |
| `test` | 테스트 | ❌ |
| `aloha` | ALOHA 시뮬 | ❌ |
| `pusht` | PushT 시뮬 | ❌ |
| `libero` | Libero 시뮬 | ❌ |
| `metaworld` | MetaWorld 시뮬 | ❌ |
| `peft` | Parameter-efficient fine-tuning | ✅ |

**추천 설치**:
```dockerfile
# 학습/추론에 필요한 것만
RUN uv pip install ".[smolvla,xvla,hilserl,async,peft]"
```

### entrypoint.sh 기능

```bash
case "${1:-server}" in
    server)     # Zenoh 서버 모드 (기본) - executor.py 실행
    train)      # 학습 모드 - python -m lerobot.scripts.train (직접 실행용)
    infer)      # 추론 모드 - python -m lerobot.scripts.eval (직접 실행용)
    shell)      # 대화형 쉘
esac
```

- **server** (기본): `executor.py` 실행
  - Zenoh를 통해 ROS2 서비스 요청 수신
  - LeRobot 코드를 **직접 import**하여 실행 (subprocess 아님)
  ```python
  # executor.py 내부
  from lerobot.scripts.lerobot_train import train as lerobot_train
  lerobot_train(cfg)  # 직접 함수 호출
  ```
- **train/infer**: Docker 외부에서 직접 테스트용 (executor.py 우회)

---

## 4. groot (GR00T N1.6 Server)

### 역할
- NVIDIA Isaac GR00T 모델 실행
- VLA (Vision-Language-Action) 추론
- Fine-tuning
- Zenoh SDK를 통해 physical_ai_server와 통신

### Base Image

| Architecture | Base Image | 검증 상태 |
|--------------|------------|-----------|
| AMD64 | `nvcr.io/nvidia/pytorch:25.04-py3` | ✅ (공식 Dockerfile과 동일) |
| ARM64 (Jetson) | `nvcr.io/nvidia/l4t-jetpack:r36.4.0` | ✅ (JetPack 6.x) |

### Jetson Orin 지원 (Isaac-GR00T 공식 문서 기반)

**성능 벤치마크 (Orin, CUDA 12.6, PyTorch 2.8)**:
| 모드 | E2E 시간 | 주파수 |
|------|----------|--------|
| PyTorch Eager | 300 ms | 3.3 Hz |
| torch.compile | 199 ms | 5.0 Hz |
| TensorRT | 173 ms | 5.8 Hz |

**Jetson용 PyTorch 설치**:
```dockerfile
# Orin용
ENV PIP_INDEX_URL=https://pypi.jetson-ai-lab.io/jp6/cu126/+simple

# Thor용 (향후)
# ENV PIP_INDEX_URL=https://pypi.jetson-ai-lab.io/sbsa/cu130
```

### 공식 Dockerfile과의 차이점

공식 (`Isaac-GR00T/docker/Dockerfile`):
```dockerfile
FROM nvcr.io/nvidia/pytorch:25.04-py3
RUN pip install imageio h5py boto3 transformers[torch] deepspeed timm peft diffusers ...
RUN cd /opt && git clone pytorch3d && pip install .  # 20+ 분 소요
```

**pytorch3d 분석 결과**:
```
gr00t/ (핵심 코드)     → import 없음 ❌
scripts/               → import 없음 ❌
pyproject.toml         → 종속성 아님 ❌
external_dependencies/ → URL 참조만 (import 없음)
```
**결론: pytorch3d는 AMD64/ARM64 모두 제거 가능** (빌드 시간 20분+ 절약)

**개선 제안**:
- pytorch3d 제거 (실제로 사용되지 않음)
- ARM64에서는 flash-attn, deepspeed 설치 제한 (추론 전용)

### ARM64 제한사항
| 패키지 | 상태 | 대안 |
|--------|------|------|
| `flash-attn` | CUDA 컴파일 필요 (메모리 제약) | 기본 attention 사용 |
| `deepspeed` | ARM64 지원 제한적 | 단일 GPU 학습 |
| `torchcodec` | ARM64 미지원 | decord 또는 av 사용 |

---

## Docker Compose 구조

### 아키텍처 자동 감지

`container.sh`에서 자동 감지:
```bash
MACHINE_ARCH=$(uname -m)
if [ "$MACHINE_ARCH" = "aarch64" ] || [ "$MACHINE_ARCH" = "arm64" ]; then
    export ARCH="arm64"
else
    export ARCH="amd64"  # 기본값
fi
```
→ ✅ 자동 감지 동작함 (Jetson에서는 `aarch64`로 감지)

### 서비스 의존성

docker-compose.yml의 `depends_on`:
```yaml
lerobot:
  depends_on:
    - physical_ai_server

groot:
  depends_on:
    - physical_ai_server
```

이는 **시작 순서**를 정의한 것 (Zenoh 연결 보장 목적)
- physical_ai_manager는 독립적으로 시작 가능 (rosbridge는 나중에 연결)

### 볼륨 마운트 구조

| 컨테이너 | 호스트 경로 | 컨테이너 경로 | 공유 여부 |
|----------|-------------|---------------|-----------|
| physical_ai_server | `./docker/workspace` | `/workspace` | - |
| physical_ai_server | `./docker/huggingface` | `/root/.cache/huggingface` | ✅ 공유 |
| lerobot | `./third_party/lerobot/workspace` | `/workspace` | 별도 |
| lerobot | `./docker/huggingface` | `/root/.cache/huggingface` | ✅ 공유 |
| groot | `./third_party/groot/workspace` | `/workspace` | 별도 |
| groot | `./docker/huggingface` | `/root/.cache/huggingface` | ✅ 공유 |

**참고**: 각 컨테이너의 `/workspace`는 **별도** 디렉토리
- HuggingFace 캐시만 공유됨 (모델 다운로드 중복 방지)

---

## 현재 문제점 및 해결 방안

### 문제 1: physical_ai_server의 Git Clone 방식
**현재**: GitHub에서 clone
**해결**: 볼륨 마운트 활용 (이미 설정되어 있음)

Dockerfile 수정:
```dockerfile
# 제거
RUN git clone -b feature-1.0.0 https://github.com/ROBOTIS-GIT/physical_ai_tools.git --recursive

# 볼륨 마운트된 경로 사용
# docker-compose.yml에서: ../:/root/ros2_ws/src/physical_ai_tools/
```

### 문제 2: rosdep OpenCV 키 오류
**증상**: `Cannot locate rosdep definition for [OpenCV]`
**원인**: Jetson/Ubuntu에서 `OpenCV`는 유효한 rosdep 키가 아님
**해결**: `rosbag_recorder/package.xml` 수정
```xml
<!-- 변경 전 -->
<depend>OpenCV</depend>
<!-- 변경 후 -->
<depend>libopencv-dev</depend>
```

### 문제 3: LeRobot 중복 설치
**현재**: physical_ai_server에 LeRobot 설치됨
**해결**: physical_ai_server Dockerfile에서 LeRobot 관련 제거

---

## TODO 정리

### physical_ai_manager
- [ ] 포트 8080 → 80 변경

### physical_ai_server
- [ ] Git clone 제거, 볼륨 마운트 방식으로 변경
- [ ] LeRobot 설치 부분 제거
- [ ] `rosbag_recorder/package.xml`의 `OpenCV` → `libopencv-dev` 수정
- [ ] docker-compose.yml에서 `zenohd` 실행 제거 (외부 Router 사용)

### lerobot
- [ ] Optional dependencies 정리 (학습/추론에 필요한 것만)
  - 유지: `smolvla`, `xvla`, `hilserl`, `async`, `peft`
  - 제거: `dynamixel`, `gamepad`, `hopejr`, `lekiwi`, `reachy2`, `kinematics`, `dev`, `test`, 시뮬레이션 관련

### groot
- [ ] pytorch3d 설치 제거 (AMD64/ARM64 모두 - 실제 사용되지 않음, 20분+ 절약)
- [ ] ARM64: flash-attn, deepspeed 제거 (추론 전용이므로 불필요)
