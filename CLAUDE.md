# CLAUDE.md — GR00T 추론 환경 구성 (Jetson + omy)

이 문서는 본 작업의 마스터 플랜이자 컨텍스트 레퍼런스다. 새로운 대화에서도 이 문서만 보면
현재 작업의 목표, 시스템 구조, 변경할 지점, 진행 상태를 모두 파악할 수 있어야 한다.

---

## 1. 작업 목표

- **타겟 보드**: NVIDIA Jetson (aarch64, JetPack 6 / l4t r36.4.0 베이스)
- **목표**: 기존 `physical_ai_tools` 레포의 4-컨테이너 환경을 Jetson에서 띄우고,
  Web UI(`physical_ai_manager`)에서 GR00T 모델로 **추론(Inference)** 만 돌리는 것.
- **사용 로봇**: `frontier_omy_f3m` — Open Manipulator Y (omy_f3m) 베이스의 사용자 변형.
  하드웨어/토픽 명세가 upstream `omy_f3m` 와 미묘하게 달라, 기존 `omy_f3m_config.yaml`
  은 손대지 않고 별도 robot_type 으로 관리한다. 기본값인 `ffw_sg2_rev1` (양팔 + head +
  lift + mobile, 22 DoF) 와도 당연히 다르므로 swap 작업이 필요함.

### 1.1 명명 규칙 (중요)

| 종류 | 이름 |
|---|---|
| robot_type 식별자 (config/yaml/launch 인자) | `frontier_omy_f3m` |
| physical_ai_server config 파일 | `physical_ai_server/config/frontier_omy_f3m_config.yaml` |
| RobotClient config 파일 | `third_party/robot_client/robot_client/config/frontier_omy_f3m.yaml` |
| URDF / mesh 파일 (모델 자체 이름이므로 그대로 유지) | `rosbag_recorder/config/urdf/omy_f3m.urdf`, `open_manipulator_description/...` |

URDF/mesh 자산은 모델 형식 이름을 따르고, robot_type 만 사용자 변형 표시를 갖는다.
- **본 보드에서 학습은 하지 않음** (GR00T 학습은 AMD64 권장. Jetson은 inference-only).

### 비목표 (이번 작업에서 제외)

- LeRobot 모델 추론
- GR00T 파인튜닝
- 데이터 수집 / rosbag 기록 흐름 변경 (단, omy 토픽이 충돌하지 않는 선까지만 검토)

---

## 2. 레포 구조 한눈에

```
physical_ai_tools/
├── docker/                          # 도커 환경 진입점
│   ├── docker-compose.yml           # 4-서비스 정의 (manager / server / lerobot / groot)
│   ├── container.sh                 # ARCH 자동 감지 + start/stop/enter 헬퍼
│   ├── s6-agent/  s6-services/      # physical_ai_server 컨테이너의 s6-overlay 서비스 정의
│   ├── huggingface/                 # 모든 ML 컨테이너의 ~/.cache/huggingface 공유 마운트
│   └── workspace/                   # 데이터/체크포인트 마운트
├── physical_ai_server/              # 메인 ROS2 노드 (오케스트레이션 + Zenoh 게이트웨이)
│   ├── Dockerfile.{amd64,arm64}
│   ├── physical_ai_server/          # Python 패키지 (physical_ai_server.py 등)
│   └── config/                      # 로봇별 토픽/조인트 YAML
│       ├── ffw_sg2_rev1_config.yaml ← 기본값
│       ├── ffw_bg2_rev4_config.yaml
│       ├── omy_f3m_config.yaml      ← upstream omy 참고용 (수정 X)
│       ├── frontier_omy_f3m_config.yaml ← 우리가 만들 사용자 변형 (Phase 1)
│       └── omx_f_config.yaml
├── physical_ai_manager/             # React + nginx Web UI (URDF 뷰어 포함)
├── physical_ai_bt/                  # BehaviorTree 노드 (재생/검증용)
├── physical_ai_interfaces/          # 커스텀 ROS2 srv/msg
├── rosbag_recorder/                 # 데이터 수집 + URDF/mesh 보관 위치
│   └── config/
│       ├── urdf/
│       │   ├── ffw_sg2_follower.urdf      ← 기본
│       │   └── omy_f3m.urdf               ← 사용자가 수정/배치한 omy URDF
│       ├── ffw_description/               # FFW 메쉬 패키지
│       └── open_manipulator_description/  ← omy용 새 패키지 (사용자가 추가)
│           ├── urdf/omy_f3m/{*.urdf, *.xacro}
│           ├── abs_urdf/omy_f3m_abs.urdf
│           └── meshes/{omy_f3m, rh_p12_rn_a}/*.stl
├── third_party/
│   ├── groot/                       # GR00T 컨테이너 소스
│   │   ├── Dockerfile.{amd64,arm64}
│   │   ├── inference.py             # GR00TInference (RobotClient + Gr00tPolicy)
│   │   ├── executor.py              # Zenoh service server (RobotServiceServer)
│   │   ├── training.py
│   │   ├── entrypoint.sh
│   │   └── Isaac-GR00T/             # 업스트림 서브모듈
│   ├── lerobot/                     # 동일 패턴의 LeRobot 컨테이너 소스
│   ├── robot_client/robot_client/   # 컨테이너에 마운트되는 공용 RobotClient 라이브러리
│   │   └── config/ffw_sg2_rev1.yaml ← 현재 이 한 개만 존재. frontier_omy_f3m.yaml 신규 작성 필요
│   └── zenoh_ros2_sdk/              # Zenoh ↔ ROS2 SDK 라이브러리
└── docs/, *.md                      # 기존 설계/계획 문서들 (3절 참조)
```

### 기존 참고 문서

루트 또는 `docs/` 의 다음 문서들이 본 분석의 1차 자료다. 새로 글을 추가하기 전에
중복 여부를 확인할 것.

- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) — 전체 ROS2/React 레이어
- [docs/DOCKER_ARCHITECTURE.md](docs/DOCKER_ARCHITECTURE.md) — 4-컨테이너 + Zenoh 토폴로지
- [docs/BUILD_TROUBLESHOOTING.md](docs/BUILD_TROUBLESHOOTING.md) — Jetson 빌드 이슈와 해결책
- [groot_inference_plan.md](groot_inference_plan.md) — 추론 파이프라인 설계 의도
- [docs/PLAN_lerobot_act_inference.md](docs/PLAN_lerobot_act_inference.md) — service prefix 동적 라우팅
- [MERGE_SUMMARY.md](MERGE_SUMMARY.md) — feature-1.0.0 머지 히스토리

---

## 3. 4-컨테이너 시스템 구조

### 3.1 컨테이너 한눈에

| 컨테이너 | 이미지 태그 | 베이스 이미지 (arm64) | 역할 |
|---|---|---|---|
| `physical_ai_manager` | `robotis/physical-ai-manager:1.0.0-arm64` | `node:22` → `nginx:1.27.5-alpine` | React Web UI (rosbridge WebSocket) |
| `physical_ai_server` | `robotis/physical-ai-server:1.0.0-arm64` | `robotis/ros:jazzy-ros-base-torch2.7.0-cuda12.8.0` | ROS2 Jazzy + rmw_zenoh + rosbridge + s6-overlay |
| `lerobot_server` | `robotis/lerobot-zenoh:1.0.0-arm64` | `nvcr.io/nvidia/l4t-jetpack:r36.4.0` | LeRobot 정책 학습/추론 |
| `groot_server` | `robotis/groot-zenoh:1.0.0-arm64` | `nvcr.io/nvidia/l4t-jetpack:r36.4.0` | GR00T N1.6 추론 (Jetson은 inference-only) |

모두 `network_mode: host` + `ipc: host` + `runtime: nvidia` (manager 제외).
ML 컨테이너는 `rtprio: 99, memlock: 8GB` 실시간 우선순위.

### 3.2 통신 토폴로지 (Zenoh)

```
┌─────────────────────┐  HTTP/WebSocket (rosbridge :9090)
│ physical_ai_manager │ ─────────────────────────┐
└─────────────────────┘                          │
                                                 ▼
                                    ┌────────────────────────┐
                                    │   physical_ai_server   │
                                    │  (ROS2 + rmw_zenoh)    │
                                    │  Zenoh router ?        │  ← rmw_zenohd 가 띄우는 라우터
                                    └─────────┬──────────────┘
                                              │ Zenoh P2P + SHM (/dev/shm)
                                ┌─────────────┴─────────────┐
                                ▼                           ▼
                       ┌────────────────┐         ┌────────────────┐
                       │ groot_server   │         │ lerobot_server │
                       │ (RobotClient + │         │ (RobotClient + │
                       │  Gr00tPolicy)  │         │  LeRobot)      │
                       └────────────────┘         └────────────────┘
```

- ROS2 미들웨어: `RMW_IMPLEMENTATION=rmw_zenoh_cpp`
- 라우터 주소: `127.0.0.1:7447` (server, lerobot 환경변수). **groot 는 `ZENOH_ROUTER_IP=`
  비어있음** — peer 모드로 multicast 디스커버리에 의존. 디버깅 시 주의.
- 셰어드 메모리: `transport/shared_memory/enabled=true` + `/dev/shm` 마운트 + `ipc: host`
- Zenoh Python SDK: `eclipse-zenoh>=1.6.0,<1.7.0` (rmw_zenoh_cpp 번들 zenoh-c v1.6.x 와 일치 必)

### 3.3 핵심 마운트 (host → container)

| Host 경로 | 컨테이너 경로 | 사용처 | 비고 |
|---|---|---|---|
| `physical_ai_tools/` | `/root/ros2_ws/src/physical_ai_tools/` | server | live source mount (개발용) |
| `physical_ai_tools/docker/huggingface/` | `/root/.cache/huggingface` | server, lerobot, groot | **공유 HF 캐시** (모델 가중치 보관) |
| `physical_ai_tools/docker/workspace/` | `/workspace` | server, lerobot | 체크포인트, 데이터 |
| `physical_ai_tools/third_party/groot/workspace/` | `/workspace` | groot | groot 전용 워크스페이스 |
| `physical_ai_tools/third_party/zenoh_ros2_sdk/` | `/zenoh_sdk` | lerobot, groot | RO |
| `physical_ai_tools/third_party/robot_client/robot_client/` | `/robot_client` | lerobot, groot | RO. **로봇별 yaml 여기 있음** |
| `physical_ai_tools/third_party/groot/{executor,training,inference}.py` | `/app/{executor,training,inference}.py` | groot | RO. 로컬 수정 즉시 반영 |
| `physical_ai_tools/rosbag_recorder/config/urdf/` | `/usr/share/nginx/html/urdf/urdf` | manager | URDF 뷰어용 (RO) |
| `physical_ai_tools/rosbag_recorder/config/ffw_description/` | `/usr/share/nginx/html/urdf/ffw_description` | manager | **FFW 메쉬만 마운트됨** ← omy 추가 필요 |
| `/home/hc/gr00t_ws` | `/gr00t_ws` | groot | 외부 사용자 워크스페이스 (RO). 우리 환경에 존재 안 할 수 있음 |

### 3.4 s6-overlay 서비스 (physical_ai_server 컨테이너)

`/etc/s6-overlay/s6-rc.d/` 안에서 longrun 으로 동작:

- `s6-agent` — Talos FastAPI agent (UDS `/var/run/agent/s6_agent.sock`)
- `physical_ai_server` — `ros2 launch physical_ai_server physical_ai_server_bringup.launch.py`
- `physical_ai_server-log` — log 파이프라인

### 3.5 컨테이너 실행 흐름

```bash
cd /GAEMI_SSD/workspace/frontier_ws/src/physical_ai_tools/docker
./container.sh start   # ARCH 자동 감지(arm64) → docker compose up -d --build
./container.sh enter   # physical_ai_server bash
./container.sh stop    # docker compose down (확인 프롬프트)
```

---

## 4. GR00T 추론 파이프라인

### 4.1 End-to-End 데이터 흐름

```
                  Web UI                         physical_ai_server (ROS2)                  groot_server
               ┌─────────┐    rosbridge       ┌──────────────────────────┐   Zenoh srv  ┌──────────────────┐
[start infer]  │ React   │ ──── /api → ROS2 → │ physical_ai_server.py    │ ───────────► │ executor.py      │
               │ UI      │                    │  ├─ TaskInfo             │  /groot/infer│  ├─ load_policy()│
               └─────────┘                    │  └─ InferenceManager     │              │  │   (Gr00tPolicy)│
                                              │      ├─ chunk buffer      │              │  └─ 토픽 자동구독 │
                                              │      ├─ 100Hz timer       │              │     (RobotClient)│
                                              │      └─ /robot/<grp>/*    │              └────────┬─────────┘
                                              └────────────┬──────────────┘                       │
                                              actions       │                                     │ get_images()
                                              JointState    │  Zenoh  /groot/get_action_chunk  ◄──┘ get_joint_pos()
                                                            │  request: { task_instruction }
                                                            │  reply  : { action_chunk[T*D] }
                                                            ▼
                                              ┌──────────────────────────┐
                                              │ Robot leader topics      │   (실로봇 또는 sim)
                                              │  /robot/arm_*_leader/... │
                                              └──────────────────────────┘
```

### 4.2 Zenoh 서비스 (RobotServiceServer 데코레이터 패턴)

`groot_server` 컨테이너는 [executor.py](third_party/groot/executor.py) 에서 다음 서비스를
ROS2 (rmw_zenoh) 로 노출:

| 서비스 | 요청 | 응답 |
|---|---|---|
| `/groot/infer` | `model_path, embodiment_tag, robot_type, task_instruction` | `success, message, action_keys` |
| `/groot/get_action_chunk` | `task_instruction` | `success, action_chunk(float[]), chunk_size, action_dim` |
| `/groot/stop` | (empty) | `success, message` |
| `/groot/train` | (training 전용) | — |
| `/groot/status` | (built-in) | 상태 |

`physical_ai_server` 의 `InferenceManager` 가 `service_prefix` 를 동적으로 결정해서
`/groot/*` 또는 `/lerobot/*` 로 라우팅한다 (LeRobot 통합 후 변경됨).

### 4.3 Isaac-GR00T submodule, 모델 가중치, /home/hc/gr00t_ws

#### Isaac-GR00T submodule (필수)

- 경로: [third_party/groot/Isaac-GR00T/](third_party/groot/Isaac-GR00T/)
- `.gitmodules` 등록 — upstream `https://github.com/NVIDIA/Isaac-GR00T.git`
- `gr00t/` Python 패키지 본체 (model, policy, data, configs, experiment, utils)
- [Dockerfile.arm64:154](third_party/groot/Dockerfile.arm64#L154) `COPY Isaac-GR00T/ ./` →
  컨테이너 `/gr00t/` 로 복사, [:171](third_party/groot/Dockerfile.arm64#L171) `uv pip install -e .`
  로 editable 설치
- `inference.py`, `training.py` 가 `from gr00t.policy ... import Gr00tPolicy`,
  `from gr00t.data.embodiment_tags import EmbodimentTag` 등으로 임포트
- **빌드 전 `git submodule update --init --recursive` 필수.** 안 그러면 컨테이너 import 실패.
- `EmbodimentTag.NEW_EMBODIMENT` 는 [Isaac-GR00T/gr00t/data/embodiment_tags.py:53](third_party/groot/Isaac-GR00T/gr00t/data/embodiment_tags.py#L53)
  에 정의 (사용자 학습 config 와 일치).

#### 모델 가중치 / 체크포인트 배치

| Host 경로 | Container 경로 | 용도 |
|---|---|---|
| `physical_ai_tools/docker/huggingface/` | `/root/.cache/huggingface` (`HF_HOME`) | 베이스 모델 HF 캐시 |
| `physical_ai_tools/third_party/groot/workspace/` | `/workspace` (`GROOT_WORKSPACE`) | 파인튜닝 체크포인트 |

**베이스 모델** (`nvidia/GR00T-N1.6-3B`): 첫 추론 시 HF 가 자동 다운로드, 또는
`docker/huggingface/hub/models--nvidia--GR00T-N1.6-3B/...` 에 사전 배치.

**파인튜닝된 체크포인트** (사용자 보유, 검증 완료):
```
third_party/groot/workspace/checkpoints/
└── checkpoint-4000/                              ← 4000 step 체크포인트
    ├── config.json
    ├── embodiment_id.json                         ← {"new_embodiment": 10, ...}
    ├── model-{00001,00002}-of-00002.safetensors
    ├── experiment_cfg/
    │   ├── conf.yaml                              ← 학습 config + modality_configs
    │   ├── config.yaml
    │   ├── dataset_statistics.json
    │   ├── final_model_config.json
    │   └── final_processor_config.json
    └── ...
```

추론 시 `/groot/infer` 요청 페이로드:
- `model_path = "/workspace/checkpoints/checkpoint-4000"` (컨테이너 내부 절대경로)
- `embodiment_tag = "new_embodiment"` (`EmbodimentTag.NEW_EMBODIMENT.value`, 소문자)
- `robot_type = "frontier_omy_f3m"`
- `task_instruction = "..."` (자연어 프롬프트)

#### 체크포인트 modality 검증 결과

[checkpoint-4000/experiment_cfg/conf.yaml:73-127](third_party/groot/workspace/checkpoints/checkpoint-4000/experiment_cfg/conf.yaml#L73-L127):

| modality | 키 | frontier_omy_f3m yaml 매칭 |
|---|---|---|
| video | `cam_wrist`, `cam_top`, `cam_belly` | ✅ camera_topic_list 와 동일 |
| state | `arm` | ✅ `follower_arm` → `removeprefix("follower_")` → `arm` |
| action | `arm` (delta_indices 0..15, action_horizon=16, RELATIVE NON_EEF) | ✅ command_topic_list `leader_arm` 으로 출력 |
| language | `annotation.human.task_description` | ✅ task_instruction 으로 주입 |

추가 정보:
- 이미지 타겟 사이즈: 224×224 (Eagle Block2A)
- 베이스 모델: `nvidia/GR00T-N1.6-3B`
- **action 형식 RELATIVE → 자동 절대값 변환 확인 완료**:
  [gr00t_policy.py:350](third_party/groot/Isaac-GR00T/gr00t/policy/gr00t_policy.py#L350)
  → [processing_gr00t_n1d6.py:248](third_party/groot/Isaac-GR00T/gr00t/model/gr00t_n1d6/processing_gr00t_n1d6.py#L248)
  → [state_action_processor.py:439-484](third_party/groot/Isaac-GR00T/gr00t/data/state_action/state_action_processor.py#L439-L484).
  `policy.get_action()` 반환 시점에 이미 절대 조인트 포지션. physical_ai_server 는
  그대로 publish 하면 됨. (조건: 호출 시 current state 동행 — RobotClient 가 자동 충족)

**TensorRT 엔진**: `dit_model_bf16.trt` 가 첫 추론 시 자동 빌드되어 `model_path` 옆에 저장
(Orin 에서 1.73x 가속).

#### `/home/hc/gr00t_ws` (제거 대상)

- [docker-compose.yml:162](docker/docker-compose.yml#L162) `- /home/hc/gr00t_ws:/gr00t_ws:ro`
  한 줄에서만 마운트, 컨테이너 내부 코드 참조 0건 (grep 으로 확인).
- 원 개발자 "hc" 의 개인 워크스페이스 흔적. 우리 보드에 해당 경로 없으면 compose up 시
  마운트 에러.
- **조치**: docker-compose.yml 에서 해당 라인 삭제 (Phase 0 에서 처리).

### 4.4 Observation/Action 데이터 컨트랙트

Observation (groot/inference.py:326-369):

```python
{
  "video": {
    "<modality_key>": ndarray(1,1,H,W,C),  # cam_left_head 등. modality_config 기반
    ...
  },
  "state": {
    "<modality_key>": ndarray(1,1,D),       # arm_left, arm_right 등. 라디안
    ...
  },
  "language": {
    "annotation.human.task_description": [["task instruction string"]],
  }
}
```

Action (policy.get_action 반환):

```python
{
  "<modality_key>": ndarray(1, T=16, D),    # 그룹별 청크
  ...
}
# postprocess 후 flatten → list[float]  (chunk_size=16, action_dim=Σ D)
```

`physical_ai_server` 의 `InferenceManager` 가:
- 청크 16 waypoints (~15Hz, 1.07s) → 100Hz 컨트롤 포인트로 선형 보간
- 청크 경계에서 L2 거리 기준 정렬
- 100Hz 타이머마다 1 액션 pop → 그룹별 `JointState` 로 분리하여 leader 토픽에 publish
- 버퍼가 임계 이하면 백그라운드 스레드로 다음 청크 fetch

### 4.5 modality 매칭 (자동 토픽 필터링)

GR00T 컨테이너는 모델의 `modality_config` 를 읽어 필요한 토픽만 구독한다:

```python
# inference.py:251-269
policy_info = {
  "video":   ["cam_left_head", "cam_left_wrist", "cam_right_wrist"],   # 모델이 요구하는 modality
  "state":   ["arm_left", "arm_right"],
  "action":  ["arm_left", "arm_right"],
  "language":["annotation.human.task_description"],
}
```

`init_robot_info()` 에서 `RobotClient` 의 `camera_names` / `joint_group_names` 와 비교해서
교집합만 살린다. 즉 **GR00T 모델 모달리티 ⊆ RobotClient 토픽** 이면 동작.

---

## 5. 기본값(ffw_sg2) → frontier_omy_f3m 스왑 분석

> upstream `omy_f3m_config.yaml` 은 참고만 하고 직접 수정하지 않는다. 우리 변형은
> `frontier_omy_f3m` 이라는 새 robot_type 식별자로 별도 관리한다.

### 5.1 기본 vs frontier_omy_f3m 스펙 비교

| 항목 | ffw_sg2_rev1 (기본) | frontier_omy_f3m (목표, omy_f3m 베이스) |
|---|---|---|
| DoF | 22 (양팔 16 + head 2 + lift 1 + mobile 3) | 7 (joint1-6 + rh_r1_joint) |
| 카메라 | 4 (cam_left_head, cam_right_head, cam_left_wrist, cam_right_wrist) | **3 (cam_wrist, cam_top, cam_belly)** |
| 카메라 토픽 패턴 | `/robot/camera/<name>/image_raw/compressed` | (사용자 확인 필요) |
| follower 조인트 토픽 (관측) | `/robot/<group>_follower/joint_states` (그룹별 5개) | `/joint_states` (단일, `JointState`) |
| leader 조인트 토픽 (액션 출력) | `/robot/<group>_leader/joint_states` | `/leader/joint_trajectory` (`JointTrajectory`) |
| URDF | `rosbag_recorder/config/urdf/ffw_sg2_follower.urdf` | `rosbag_recorder/config/urdf/omy_f3m.urdf` (단일) 또는 `open_manipulator_description/urdf/omy_f3m/omy_f3m.urdf` |
| 메쉬 패키지 | `ffw_description` | `open_manipulator_description` (`meshes/{omy_f3m, rh_p12_rn_a}/`) |
| 추론 시 leader/follower | leader 토픽으로 action 출력, follower state 관측 | 동일 (5.5 참조) |

### 5.2 omy 자산 인벤토리 (사용자가 이미 배치한 것 — frontier_omy_f3m 이 그대로 참조)

- [rosbag_recorder/config/urdf/omy_f3m.urdf](rosbag_recorder/config/urdf/omy_f3m.urdf)
  — 단일 URDF (16KB). 메쉬 ref `package://open_manipulator_description/...`
- [rosbag_recorder/config/open_manipulator_description/urdf/omy_f3m/](rosbag_recorder/config/open_manipulator_description/urdf/omy_f3m/)
  — `omy_f3m.urdf`, `omy_f3m.urdf.xacro`, `omy_f3m_arm.urdf.xacro`, `rh_p12_rn_a.urdf.xacro`
- [rosbag_recorder/config/open_manipulator_description/abs_urdf/omy_f3m_abs.urdf](rosbag_recorder/config/open_manipulator_description/abs_urdf/omy_f3m_abs.urdf)
  — 절대경로 메쉬 ref 버전
- 메쉬 `meshes/omy_f3m/`: `base_unit.stl, flange.stl, link1-6.stl` (8개)
- 메쉬 `meshes/rh_p12_rn_a/`: `base.stl, l1.stl, l2.stl, r1.stl, r2.stl` (5개)

### 5.3 손볼 지점 — 우선순위 순서

#### P0 (이게 안 되면 추론 자체가 시작 안 됨)

1. **`third_party/robot_client/robot_client/config/frontier_omy_f3m.yaml` 신규 작성**
   - 현재 `ffw_sg2_rev1.yaml` 한 개만 있음. `RobotClient("frontier_omy_f3m")` 이
     [robot_client/robot_client.py:47-84](third_party/robot_client/robot_client/robot_client.py)
     에서 `_find_config()` 로 이 파일을 찾는다. 없으면 인스턴스 생성에서 즉시 실패.
   - 작성 시 upstream `omy_f3m_config.yaml` 의 토픽/조인트를 시드로 쓰되, 실제
     하드웨어 토픽 명에 맞춰 수정.
   - 다음 키 필요: `robot_name, total_dof, cameras, joint_groups, sensors, rosbag_extra_topics`.
   - `joint_groups` 의 키 명명은 P0-3 이슈와 직결됨 (아래 참조).

2. **`physical_ai_server/config/frontier_omy_f3m_config.yaml` 신규 작성**
   - upstream `omy_f3m_config.yaml` 을 시드로 복사한 뒤 root 키를 `frontier_omy_f3m` 으로 변경.
   - `urdf_path` 추가 → `physical_ai_server.py:255` 가
     `f'{robot_type}.urdf_path'` 파라미터를 declare 하므로 명시 필요.
   - `command_topic_list` 추가 (action publish 경로).
   - `joint_topic_list` 의 leader 가 `JointTrajectory` 타입인지 `JointState` 인지 5.4
     질문에 답한 결과로 결정.

3. **`third_party/groot/inference.py:286-291` 의 prefix 핸들링 대응**
   ```python
   for group in self.robot.joint_group_names:
       if "follower" not in group:
           continue
       modality_key = group.removeprefix("follower_")   # ← upstream omy 에선 group=="follower"
       if modality_key in self.policy_info["state"]:    # ← "follower" 가 정책 state 에 없음
           joints[modality_key] = group
   ```
   추천 해법: **`frontier_omy_f3m.yaml` 의 joint_groups 명명을 `follower_arm` /
   `leader_arm` 으로 통일** (joint1~6 + rh_r1_joint 묶음). 이러면 inference.py 수정 없이
   modality_key="arm" 으로 깔끔하게 매칭. upstream omy yaml 은 그대로 두므로 부작용 없음.

#### P1 (Web UI URDF 뷰어 동작)

4. **`docker-compose.yml:14-17` manager 마운트에 omy 메쉬 경로 추가**
   ```yaml
   volumes:
     - ../rosbag_recorder/config/urdf:/usr/share/nginx/html/urdf/urdf:ro
     - ../rosbag_recorder/config/ffw_description:/usr/share/nginx/html/urdf/ffw_description:ro
     - ../rosbag_recorder/config/open_manipulator_description:/usr/share/nginx/html/urdf/open_manipulator_description:ro  ← 추가
   ```
   URDF 안의 `package://open_manipulator_description/meshes/...` 가 nginx 경로로 풀려야 한다.
   manager 의 URDF 로더가 어떤 base path 를 쓰는지 React 코드도 확인 필요.

5. **`omy_f3m.urdf` 의 메쉬 ref 점검**
   - `package://` 형태면 manager 가 base path 매핑을 해줘야 함
   - 절대경로 형태 (`abs_urdf/omy_f3m_abs.urdf`) 와 둘 중 어느 것을 사용할지 결정.

#### P2 (런타임 안정성)

6. **`physical_ai_server.py:526-540 get_robot_type_list()`** — config 폴더 스캔으로 자동
   디스커버리. `frontier_omy_f3m_config.yaml` 만 만들어두면 자동으로 목록에 잡힘.

7. **`physical_ai_bt/bt_bringup/launch/bt_node.launch.py:46-47`** — fallback 이
   `ffw_sg2_rev1_config.yaml` 로 하드코딩. `frontier_omy_f3m` 기본 사용 시 launch 인자
   `robot_type:=frontier_omy_f3m` 명시 필요.

8. **`physical_ai_server/utils/video_file_server.py:391`** —
   `robot_type = 'ffw_sg2_rev1'` 하드코딩 (BT 런처용). POST 바디로 override 가능하지만
   기본값을 `frontier_omy_f3m` 으로 둘지 결정.

9. **`docker-compose.yml:162` `/home/hc/gr00t_ws` 마운트** — 이 호스트 경로 우리 환경에
   없을 가능성 높음. compose up 시 에러나면 제거 또는 빈 폴더 생성.

#### P3 (선택)

10. **`rosbag_to_lerobot_converter.py:261-266`** — `follower_/leader_` underscore prefix
    하드코딩. `frontier_omy_f3m` 그룹명을 `follower_arm` / `leader_arm` 으로 정하면 자동 해결됨.
11. **`test_utils/`** mock publisher 들의 default robot — 테스트 안 쓰면 무시.

### 5.4 frontier_omy_f3m 토픽 구조 — 결정 사항

| 질문 | 답 |
|---|---|
| leader 토픽 메시지 타입 | **`JointTrajectory`** (communicator.py:168 가 mobile 외엔 JointTrajectory publish) |
| 추론 시 leader/follower 사용 | **follower 만 관측, leader 토픽으로 액션 출력** (사용자 확인) |
| 카메라 개수 | **3개**: cam_wrist, cam_top, cam_belly |
| 학습 체크포인트 | **사용자 보유** — `embodiment_tag=NEW_EMBODIMENT`, base `nvidia/GR00T-N1.6-3B` 파인튜닝 (LLM/Vision 동결, projector + DiT 학습) |

### 5.5 추론 시 leader/follower 데이터 흐름 (확정)

[communicator.py:85-172](physical_ai_server/physical_ai_server/communication/communicator.py#L85-L172) 분석 결과:

```
[Robot HW]                                      [physical_ai_server]                    [groot_server]
                                                                                        ┌────────────────┐
follower joint_states ──────────────────────────────────────────────────────────────►   │ RobotClient    │
   /joint_states (JointState)                                                           │ (관측 입력)    │
                                                                                        │       ↓        │
                                                                                        │ Gr00tPolicy    │
                                                                                        │       ↓        │
                                                ┌──────────────────────────────────┐    │ action chunk   │
                                                │ communicator.publish_action()    │ ◄──┘                
                                                │  ├─ JointTrajectory publishers   │
                                                │  │     ↓ command_topic_list      │
                                                │  └─ JointState mirror publishers │
                                                │        ↓ leader joint_states     │  (rosbag 기록용)
                                                └──────────────────────────────────┘
                                                       ↓                  ↓
leader 컨트롤러 (실로봇 추종) ◄─── /leader/joint_trajectory (JointTrajectory)
                                                       ↓ (rosbag tap)
                                                /robot/<grp>_leader/joint_states (JointState 미러)
```

따라서 `frontier_omy_f3m_config.yaml` 에서:

- **`joint_topic_list`**: 데이터 기록 시 구독할 토픽 (follower + leader 둘 다, JointState 형태 기준)
- **`command_topic_list`**: 추론 시 액션 publish 경로 (leader, JointTrajectory 형태)
- **`joint_list`**: command publish 대상 그룹 이름 (예: `[leader_arm]`)

`frontier_omy_f3m.yaml` (RobotClient) 에서:

- 추론에는 follower 만 쓰이지만, 데이터 기록 호환을 위해 follower_arm + leader_arm 둘 다 정의 권장
- `cameras`: cam_wrist, cam_top, cam_belly 3개 모두 등록

이 질문들은 사용자에게 확인하면서 진행한다.

---

## 6. 실행 계획 (단계별)

각 단계는 독립적으로 검증 가능하게 끊었다.

### Phase 0: 환경 점검 (완료)

현재 보드: **Jetson AGX Orin Developer Kit, L4T R36 REV 5.0** (SM 8.7).
Dockerfile 가정 (`l4t-jetpack:r36.4.0`, flash-attn SM 8.7) 와 호환. Submodule 도 이미
클론되어 있음 (Isaac-GR00T, zenoh_ros2_sdk 검증 완료).

- [x] `/home/hc/gr00t_ws` 마운트 라인 주석 처리 ([docker-compose.yml](docker/docker-compose.yml))
- [x] 체크포인트 확인: `third_party/groot/workspace/checkpoints/checkpoint-4000/`
      experiment_cfg 포함된 정상 GR00T 체크포인트.

### Phase 1: frontier_omy_f3m RobotClient/서버 설정 (완료)

- [x] [third_party/robot_client/robot_client/config/frontier_omy_f3m.yaml](third_party/robot_client/robot_client/config/frontier_omy_f3m.yaml) 작성
- [x] [physical_ai_server/config/frontier_omy_f3m_config.yaml](physical_ai_server/config/frontier_omy_f3m_config.yaml) 작성
- [x] modality 매칭 검증: video=`cam_wrist/cam_top/cam_belly`, state=`arm`, action=`arm` —
      체크포인트 conf.yaml 과 정확히 일치, inference.py 수정 불필요.
- [x] [docker-compose.yml](docker/docker-compose.yml) physical_ai_manager 에
      `open_manipulator_description` 마운트 추가 (Web UI URDF 뷰어용).

### Phase 2: 컨테이너 빌드 & 기동

- [ ] `cd docker && ./container.sh start` → 4 컨테이너 모두 healthy 까지 확인.
- [ ] `docker logs groot_server` 에서 GR00T executor 가 Zenoh 서비스 등록 메시지 출력하는지.
- [ ] `docker exec -it physical_ai_server bash` → `ros2 topic list`, `ros2 service list` 로
      `/groot/infer`, `/groot/get_action_chunk` 가 보이는지.

### Phase 3: Web UI에서 omy 선택 + URDF 뷰

- [ ] `docker-compose.yml` manager 마운트에 `open_manipulator_description` 추가.
- [ ] manager 컨테이너 재기동 후 브라우저에서 robot_type 드롭다운에 `frontier_omy_f3m` 보이는지.
- [ ] URDF 뷰어가 omy 메쉬 정상 렌더링 (404 없음).

### Phase 4: 추론 실행 검증

- [ ] HF 캐시 또는 워크스페이스에 frontier_omy_f3m 호환 GR00T 체크포인트 배치.
- [ ] Web UI 에서 task instruction + model_path 입력 → Start Inference.
- [ ] `/groot/infer` 응답 success, `action_keys` 가 frontier_omy_f3m modality 와 일치.
- [ ] `/groot/get_action_chunk` 가 주기적으로 호출되며 leader 토픽에 액션 publish 되는지
      `ros2 topic echo` 로 확인.

각 Phase 완료 시 이 문서의 체크박스를 갱신한다.

---

## 7. 환경 가정 / 결정 사항

> 작업 중 새 결정이 나오면 이 절에 누적 기록.

- **Jetson Orin** 가정 (flash-attn SM 8.7 빌드, TensorRT 시스템 라이브러리 심볼릭 링크 필요).
- **추론 전용**. 학습은 본 보드에서 시도하지 않는다 (`docker/groot/Dockerfile.arm64` 주석 참조).
- HF 캐시는 호스트 `physical_ai_tools/docker/huggingface/` 에서 컨테이너로 공유. 모델
  반입은 이 폴더에 직접 풀어두는 것을 기본으로 한다.
- **사용자 변형 robot_type 은 `frontier_omy_f3m`**. upstream `omy_f3m_config.yaml` /
  `omy_f3m.yaml` (RobotClient) 은 손대지 않고 시드로만 활용. URDF/mesh 파일명은 모델
  자체 이름(`omy_f3m.urdf`, `open_manipulator_description/`)을 유지한다.
- `frontier_omy_f3m` 의 joint_groups 명명은 `follower_arm` / `leader_arm` 으로 통일 (Phase 1 결정).

### 7.1 Jetson 빌드 트러블슈팅 (2026-04-30 정리)

`groot/Dockerfile.arm64` 의 flash-attn 빌드는 다음 함정들 때문에 한 번 망가진 적 있음.
재발 시 같은 곳을 다시 디버깅하지 않도록 결정 사항 박제:

1. **flash-attn 은 tag 로 pin (`v2.7.4.post1`)**.
   - 이유: main 브랜치 `setup.py` 의 `cuda_archs()` 기본값이 시간이 지나며 바뀐다 (예:
     `"80;90;100;120"` → `"80;90;100;110;120"`). 우리가 sed 로 그 문자열을 `"87"` 로
     치환하는데 패턴이 mismatch 되면 **silent 실패** (sed 는 매치 못해도 에러 안 냄).
     원본이 그대로 빌드되면 nvcc 가 `compute_120` 시도 → CUDA 12.6 (JetPack 6) 미지원
     → `nvcc fatal : Unsupported gpu architecture 'compute_120'`.
   - v2.7.4.post1 은 setup.py 형식이 우리 sed 와 정확히 일치 + SM 100/120 추가가
     `bare_metal_version >= 12.8` 가드라 CUDA 12.6 에서 자동 스킵 (이중 안전장치).

2. **`uv venv` 는 venv 안에 pip 자체를 설치하지 않는다**.
   - `/gr00t/.venv/bin/pip` 절대경로로 호출하면 `not found`. uv 는 자체 패키지 매니저
     (`uv pip install ...`) 사용이 정석. 정 venv 의 pip 가 필요하면 `uv venv --seed`.
   - 빌드 단계에서 `pip download flash-attn` 같이 venv 의존하는 명령 쓰지 말 것 →
     `git clone --depth 1 --branch <tag>` 로 소스 받는 게 더 robust.

3. **`packaging`, `wheel`, `setuptools` 는 build-time 의존성이라 venv 에 미리 깔아야 함**.
   - flash-attn `setup.py` 가 import 단계에서 `packaging` 사용. `--no-build-isolation`
     으로 빌드 격리 끄지 않으면 isolated build env 에서 packaging 못 찾음.
   - 따라서 `uv pip install --no-cache packaging wheel setuptools` 를 flash-attn 빌드
     RUN 의 첫 줄로 넣고, `uv pip install . --no-build-isolation` 으로 빌드.

4. **rosbridge fastcdr 심볼 미스매치**: `physical_ai_server/Dockerfile.arm64` 에서
   `ros-${ROS_DISTRO}-fastcdr` (2.2.7) 와 `rosidl-typesupport-fastrtps-{c,cpp}` (3.6.3)
   를 함께 설치해야 rosbridge 가 `libfastcdr.so.2` 의 `_ZN8...3Cdr9serializeEj` 심볼을
   찾을 수 있음. 기본 apt 의 2.2.5 는 ABI 충돌.

5. **eclipse-zenoh 버전 핀 (`>=1.6.0,<1.7.0`)**: rmw_zenoh_cpp 번들 zenoh-c v1.6.x 와
   ABI 일치 必. 1.7.x 면 디스커버리는 되지만 service call 실패 (silent).

6. **물리 보드 SM 8.7 (Orin) gencode**: flash-attn 빌드 결과 `.o` 파일들이
   `-gencode arch=compute_80,code=sm_80 -gencode arch=compute_87,code=sm_87` 양쪽
   포함하고 있어야 정상. 빌드 로그에서 한쪽만 보이면 sed 패치가 부분 적용된 것.

---

## 8. 빠른 명령 레퍼런스

```bash
# 컨테이너 라이프사이클
cd /GAEMI_SSD/workspace/frontier_ws/src/physical_ai_tools/docker
./container.sh start | enter | stop

# server 컨테이너에서 ROS2 디버그
ros2 topic list | grep -E '/robot|/joint|/camera|/cmd_vel|/odom'
ros2 service list | grep -E '/groot|/lerobot'
ros2 param get /physical_ai_server frontier_omy_f3m.urdf_path

# Zenoh 라우터 상태
docker logs physical_ai_server 2>&1 | grep -i zenoh
docker exec groot_server python -c "import zenoh; print(zenoh.__version__)"

# GR00T 추론 실행 (수동)
docker exec -it groot_server bash
# inside container:
python /app/inference.py  # (executor가 server 모드로 띄워져 있어야 자동 동작)
```

---

마지막 갱신: 2026-04-28 (초기 분석 완료).
