# CLAUDE.md — physical_ai_tools 프로젝트 가이드

이 파일은 Claude가 이 저장소를 처음 볼 때 빠르게 맥락을 파악할 수 있도록 작성된 안내 문서입니다.

---

## 프로젝트 개요

**physical_ai_tools**는 ROBOTIS가 개발하는 로봇 AI 학습·추론 인프라입니다.
ROS 2(Jazzy) 기반으로 동작하며, Docker 컨테이너 환경(`/root/ros2_ws/src/physical_ai_tools/`) 안에서 실행됩니다.

주요 기능:
- 로봇 데이터 수집 및 LeRobot v2 포맷 데이터셋 생성
- 다양한 AI 정책(LeRobot 계열, GR00T N1) 파인튜닝
- 학습된 모델로 실시간 추론(inference)

---

## 패키지 구조

```
physical_ai_tools/
├── Isaac-GR00T/              # NVIDIA GR00T N1 학습 라이브러리 (editable install)
├── lerobot/                  # LeRobot 라이브러리 (editable install)
├── physical_ai_interfaces/   # ROS 2 커스텀 메시지/서비스 정의
├── physical_ai_server/       # 핵심 서버 노드 (학습·추론·데이터 관리)
├── physical_ai_bt/           # Behavior Tree 기반 태스크 실행
├── physical_ai_manager/      # 전체 시스템 관리 노드
├── physical_ai_tools/        # 유틸리티 CLI 도구
├── rosbag_recorder/          # ROS bag 녹화
└── docker/                   # Docker 환경 설정
```

---

## 핵심 패키지: physical_ai_server

```
physical_ai_server/physical_ai_server/
├── physical_ai_server.py         # 메인 ROS 2 노드 (모든 서비스/토픽 진입점)
├── training/
│   ├── training_manager.py       # 학습 파이프라인 오케스트레이션
│   └── trainers/
│       ├── trainer.py            # 추상 베이스 클래스 (Trainer ABC)
│       ├── lerobot/
│       │   └── lerobot_trainer.py    # LeRobot 계열 전체 구현 (504줄)
│       ├── gr00tn1/
│       │   └── gr00tn1_trainer.py    # GR00T N1 구현 (구현 완료)
│       └── openvla/
│           └── openvla_trainer.py    # stub (미구현)
├── inference/
│   ├── inference_manager.py      # 추론 파이프라인 관리
│   ├── client_inference.py
│   └── server_inference.py
├── data_processing/
│   ├── data_manager.py           # 데이터셋 녹화·업로드 (972줄)
│   ├── lerobot_dataset_wrapper.py # LeRobot 데이터셋 래퍼
│   ├── data_converter.py         # ROS 메시지 → 텐서 변환
│   └── progress_tracker.py
├── device_manager/               # CPU/RAM/Storage 모니터링
└── video_encoder/                # FFmpeg/GStreamer 비디오 인코딩
```

---

## 학습 아키텍처

### Trainer 패턴
```
TrainingManager
  ├── _get_training_config()   # policy_type에 따라 config 생성
  │     ├── 'gr00tn1'  → Gr00tN1TrainingConfig (dataclass)
  │     └── 나머지     → TrainPipelineConfig (draccus 파싱)
  ├── _get_trainer()           # TRAINER_MAPPING에서 클래스 선택
  └── train()                  # trainer.train(cfg, stop_event) 호출
```

### 지원 policy_type
| policy_type | Trainer 클래스 | 비고 |
|---|---|---|
| `pi0`, `pi0fast`, `diffusion`, `act`, `tdmpc`, `vqbet`, `smolvla` | `LerobotTrainer` | LeRobot 라이브러리 사용 |
| `gr00tn1` | `Gr00tN1Trainer` | Isaac-GR00T 라이브러리 사용 |

### 학습 실행 흐름 (ROS 서비스)
```
/training/command (SendTrainingCommand) → START
  → TrainingManager 초기화
  → _get_training_config()
  → _get_trainer()
  → 별도 스레드에서 trainer.train(cfg, stop_event) 실행
  → /training/status 토픽으로 step/loss 실시간 발행

FINISH 커맨드 → stop_event.set() → 학습 루프 graceful 종료
```

---

## GR00T N1 학습 구현 상세

> 2025-04 구현 완료. 이전에는 stub이었음.

### 관련 파일
- `physical_ai_server/physical_ai_server/training/trainers/gr00tn1/gr00tn1_trainer.py`
- `physical_ai_interfaces/msg/TrainingInfo.msg` (GR00T 전용 필드 추가됨)
- `Isaac-GR00T/gr00t/experiment/experiment.py` (학습 루프 원본 참조)

### 핵심 클래스
- **`Gr00tN1TrainingConfig`**: GR00T 전용 dataclass config (draccus 미사용)
- **`Gr00tN1Trainer`**: `Trainer` ABC 구현체
  - `_build_gr00t_config()`: `Gr00tN1TrainingConfig` → `gr00t.configs.base_config.Config` 변환
  - `_run_training()`: `experiment.py:run()`을 인라인 재현 + 커스텀 HF 콜백 주입

### 커스텀 HF Trainer 콜백
- **`_StopCallback`**: `threading.Event` → `control.should_training_stop = True` 전달
- **`_ProgressCallback`**: HF Trainer의 step/loss → `Gr00tN1Trainer.current_step/current_loss` 갱신 (ROS 상태 발행에 사용)

### GR00T 데이터셋 요구사항
LeRobot v2 포맷 + `meta/modality.json` 필수:
```
dataset/
├── meta/
│   ├── modality.json     ← GR00T 필수 파일
│   ├── info.json
│   └── episodes.jsonl
├── videos/chunk-000/
└── data/chunk-000/
```

### TrainingInfo.msg GR00T 전용 필드
```
string base_model_path       # 기본값: "nvidia/GR00T-N1-2B"
string embodiment_tag        # 기본값: "new_embodiment"
string modality_config_path  # 없으면 사전 등록 태그 사용
```

### 체크포인트 저장 경로
`/root/ros2_ws/src/physical_ai_tools/Isaac-GR00T/outputs/train/<output_folder_name>/`

---

## LeRobot 학습 구현 상세

### 관련 파일
- `physical_ai_server/physical_ai_server/training/trainers/lerobot/lerobot_trainer.py`
- `lerobot/` (editable install된 LeRobot 라이브러리)

### 특징
- draccus 기반 `TrainPipelineConfig` 사용
- 커스텀 학습 루프 직접 구현 (HF Trainer 미사용)
- resume 지원: `train_config.json` 로드 후 user override 병합
- WandB 로깅 지원

### 체크포인트 저장 경로
`/root/ros2_ws/src/physical_ai_tools/lerobot/outputs/train/<output_folder_name>/`

---

## ROS 2 인터페이스 (주요 토픽/서비스)

| 타입 | 이름 | 설명 |
|---|---|---|
| Service | `/training/command` | START / FINISH 학습 제어 |
| Topic | `/training/status` | 현재 step, loss 발행 |
| Service | `/training/get_available_policy` | 지원 policy 목록 |
| Service | `/training/get_training_info` | 현재 학습 정보 |

---

## 환경 정보

- **OS**: Ubuntu (Docker 컨테이너)
- **ROS**: ROS 2 Jazzy
- **Python**: 3.x
- **주요 의존성**:
  - `lerobot` (editable, `/root/ros2_ws/src/physical_ai_tools/lerobot/`)
  - `Isaac-GR00T` (editable, `/root/ros2_ws/src/physical_ai_tools/Isaac-GR00T/`)
  - `transformers`, `torch`, `draccus`, `wandb`

---

## 작업 이력 (주요 변경)

### 2025-04
- **GR00T N1 학습 구현**: `gr00tn1_trainer.py` stub → 전체 구현
  - `Gr00tN1TrainingConfig` dataclass 신규 작성
  - `_run_training()`: Isaac-GR00T의 `experiment.run()` 로직 인라인 재현
  - HF Trainer에 stop_event 콜백, progress 트래킹 콜백 주입
- **TrainingInfo.msg 확장**: GR00T 전용 필드 3개 추가
- **TrainingManager 확장**: GR00T 분기 처리, `gr00tn1` policy 등록

---

## 미구현 항목

- `openvla_trainer.py`: stub 상태, 미구현
- GR00T resume 학습: 현재 새 학습만 지원
- GR00T 추론(`inference_manager.py`): 주석 처리 상태
- Web UI (`physical_ai_manager`) GR00T 전용 입력 필드 미추가
  - `base_model_path`, `embodiment_tag`, `modality_config_path` 입력 컴포넌트 필요
  - LeRobot용 옵션 입력만 구현된 상태
  - 서버 쪽(TrainingManager, Gr00tN1Trainer)은 이미 연동 준비 완료
