# Data Conversion Pipeline

ROSbag2 녹화 데이터를 LeRobot 학습 데이터셋으로 변환하는 3단계 파이프라인.

## Overview

```
ROSbag2 (MCAP)
     │
     ▼
┌─────────────────────────────────────┐
│  Stage 0: Merge (optional)          │  여러 데이터셋을 하나로 병합 (symlink)
└─────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────┐
│  Stage 1: ROSbag → MP4              │  ScaleAIConverter
│  이미지 토픽 → MP4 비디오 추출       │  convert_rosbag2mp4.py
└─────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────┐
│  Stage 2: MP4 → LeRobot v2.1       │  RosbagToLerobotConverter
│  조인트 데이터 + MP4 → Parquet/MP4  │  rosbag_to_lerobot_converter.py
└─────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────┐
│  Stage 3: v2.1 → LeRobot v3.0      │  lerobot 내장 변환기
│  파일 구조 재구성                    │  (docker exec lerobot_server)
└─────────────────────────────────────┘
     │
     ▼
LeRobot v3.0 Dataset (학습 가능)
```

## Directory Structure

```
/workspace/rosbag2/
├── {robot}_{task}/                          # 원본 + Stage 1 출력
│   ├── 0/                                   # 원본 에피소드
│   │   ├── 0_0.mcap                         #   ROSbag2 MCAP 파일
│   │   ├── episode_info.json                #   에피소드 메타
│   │   ├── metadata.yaml                    #   ROS2 메타데이터
│   │   └── robot.urdf                       #   로봇 URDF
│   ├── 0_converted/                         # Stage 1 출력
│   │   ├── episode.mcap                     #   이미지 제거된 MCAP
│   │   ├── cam_left_head.mp4                #   카메라별 MP4
│   │   ├── cam_right_head.mp4
│   │   ├── cam_left_wrist.mp4
│   │   ├── cam_right_wrist.mp4
│   │   ├── video_stats.json                 #   사전 계산된 비디오 통계
│   │   ├── episode_info.json                #   드롭 프레임 정보 포함
│   │   ├── robot.urdf
│   │   └── meshes/
│   ├── 1/
│   ├── 1_converted/
│   └── ...
│
├── {robot}_{task}_lerobot_v21/              # Stage 2 출력
│   ├── data/
│   │   └── chunk-000/
│   │       ├── episode_000000.parquet       #   에피소드별 Parquet
│   │       ├── episode_000001.parquet
│   │       └── ...
│   ├── meta/
│   │   ├── info.json                        #   데이터셋 메타정보
│   │   ├── episodes.jsonl                   #   에피소드 목록
│   │   ├── episodes_stats.jsonl             #   에피소드별 통계
│   │   └── tasks.jsonl                      #   태스크 목록
│   └── videos/
│       └── chunk-000/
│           ├── observation.images.cam_left_head/
│           │   ├── episode_000000.mp4
│           │   └── ...
│           ├── observation.images.cam_right_head/
│           ├── observation.images.cam_left_wrist/
│           └── observation.images.cam_right_wrist/
│
└── {robot}_{task}_lerobot_v30/              # Stage 3 출력 (최종)
    ├── data/
    │   └── chunk-000/
    │       └── file-000.parquet             #   여러 에피소드 통합
    ├── meta/
    │   ├── info.json
    │   ├── stats.json                       #   전체 통계
    │   ├── tasks.parquet
    │   └── episodes/
    │       └── chunk-000/
    │           └── file-000.parquet         #   에피소드 메타 (Parquet)
    └── videos/
        └── {camera_key}/
            └── chunk-000/
                └── file-000.mp4             #   에피소드 연결된 MP4
```

---

## Stage 0: Merge (Optional)

여러 데이터셋 폴더를 하나로 병합. UI에서 "Merge & Convert" 모드를 선택할 때만 실행.

| 항목 | 내용 |
|------|------|
| 클래스 | `Mp4ConversionWorker._merge_episodes()` |
| 파일 | `mp4_conversion_worker.py` |
| 입력 | 소스 폴더 목록 (예: `task_A/`, `task_B/`) |
| 출력 | 병합 폴더 (symlink로 에피소드 연결) |
| 진행률 | 0% ~ 5% |

### 동작
1. 출력 폴더 생성
2. 소스 폴더들을 순회하며 숫자 이름 디렉토리(에피소드)를 수집
3. 에피소드 번호를 0부터 연속으로 재부여
4. 각 에피소드를 symlink로 연결 (데이터 복사 없음)

### 예시
```
source_a/ (ep 0-6) + source_b/ (ep 0-7)
    ↓
merged_output/
  0 -> /workspace/rosbag2/source_a/0   (symlink)
  1 -> /workspace/rosbag2/source_a/1
  ...
  7 -> /workspace/rosbag2/source_b/0
  ...
  14 -> /workspace/rosbag2/source_b/7
```

---

## Stage 1: ROSbag to MP4

ROSbag2 MCAP에서 이미지 토픽을 MP4 비디오로 추출하고, 이미지가 제거된 MCAP을 생성.

| 항목 | 내용 |
|------|------|
| 클래스 | `ScaleAIConverter` |
| 파일 | `convert_rosbag2mp4.py` |
| 입력 | 에피소드 디렉토리 (`0/`, `1/`, ...) |
| 출력 | `{ep}_converted/` 디렉토리 |
| 진행률 | 단일 모드: 0% ~ 33% / Merge 모드: 5% ~ 35% |

### 처리 단계

#### Step 1: 프레임 추출 및 매칭
- MCAP 파일에서 compressed image 토픽과 camera_info 토픽을 읽음
- 4개 카메라별로 이미지 프레임과 camera_info를 타임스탬프 기준으로 매칭
- 카메라 간 프레임 수 정렬 (최소 프레임 수에 맞춤)
- 드롭된 프레임 감지 및 보간 (이전 프레임 복제)

#### Step 2: MP4 인코딩
- ffmpeg를 이용하여 raw BGR 프레임을 MP4로 인코딩
- 하드웨어 인코더 우선 시도 (h264_nvenc 등), 실패 시 libx264 소프트웨어 폴백
- ThreadPoolExecutor로 카메라별 병렬 인코딩 (최대 4 workers)

#### Step 2.5: 비디오 통계 사전 계산
- 인메모리 프레임에서 100개 샘플 추출
- RGB 채널별 mean, std, min, max 계산 (0~1 정규화)
- `video_stats.json`으로 저장
- Stage 2에서 MP4 디코딩 없이 통계를 재활용할 수 있음

#### Step 3: MCAP 재생성
- 원본 MCAP에서 이미지 토픽을 제거
- 매칭된 camera_info 타임스탬프만 보존
- 타임스탬프 스무딩 적용 (68~71ms 간격 → 67~68ms로 조정)

#### Step 4: 메타 파일 복사 및 드롭 정보 기록
- `episode_info.json`, `metadata.yaml`, `robot.urdf` 복사
- `episode_info.json`에 `dropped_frames` 정보 추가

### 주요 설정
| 설정 | 기본값 | 설명 |
|------|--------|------|
| `fps` | 15 | 목표 프레임 레이트 |
| `use_hardware_encoding` | true | GPU 인코딩 시도 여부 |
| `enable_timestamp_smoothing` | true | 타임스탬프 스무딩 활성화 |
| `trim_start_sec` | 0.5 | 시작부분 트림 (초) |
| `trim_end_sec` | 0.0 | 끝부분 트림 (초) |

---

## Stage 2: MP4 to LeRobot v2.1

Stage 1 출력(MP4 + MCAP)을 LeRobot v2.1 데이터셋 형식으로 변환.

| 항목 | 내용 |
|------|------|
| 클래스 | `RosbagToLerobotConverter` |
| 파일 | `rosbag_to_lerobot_converter.py` |
| 입력 | `{ep}_converted/` 디렉토리들 |
| 출력 | `{dataset}_lerobot_v21/` 디렉토리 |
| 진행률 | 단일 모드: 33% ~ 66% / Merge 모드: 35% ~ 68% |

### 처리 단계

#### 에피소드 파싱 (per episode)
1. MCAP에서 joint_states, cmd_vel, odometry 토픽 읽기
2. 토픽별 조인트 데이터를 `joint_order` 설정에 따라 정렬/병합
3. observation.state (follower) 와 action (leader) 분리
4. 비디오 프레임 수에 맞춰 parquet 행 수 트리밍 (1:1 매칭)

#### 데이터셋 쓰기 (per episode)
1. **Parquet 파일**: 타임스탬프, 프레임 인덱스, 에피소드 인덱스, observation.state, action
2. **MP4 복사**: Stage 1 MP4를 `videos/chunk-000/observation.images.{cam}/` 경로로 복사 (재인코딩 없음)
3. **에피소드 메타**: `episodes.jsonl`에 에피소드 정보 추가
4. **에피소드 통계**: `episodes_stats.jsonl`에 통계 추가

#### 비디오 통계 계산
- `video_stats.json` (Stage 1에서 사전 계산)이 있으면 로드하여 사용
- 없으면 MP4에서 100 프레임 샘플링하여 직접 계산 (폴백)
- 채널별 RGB mean/std/min/max (0~1 정규화)

#### 최종 메타 파일
- `info.json`: 데이터셋 전체 정보 (에피소드 수, 프레임 수, features, splits 등)
- `tasks.jsonl`: 태스크 인덱스-이름 매핑

### Parquet 스키마
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `timestamp` | float32 | 에피소드 시작 기준 상대 시간 (초) |
| `frame_index` | int64 | 에피소드 내 프레임 인덱스 |
| `episode_index` | int64 | 에피소드 번호 |
| `index` | int64 | 데이터셋 전체 기준 인덱스 |
| `task_index` | int64 | 태스크 인덱스 |
| `observation.state` | list\<float32\>[N] | follower 조인트 상태 |
| `action` | list\<float32\>[N] | leader 조인트 명령 |

---

## Stage 3: LeRobot v2.1 to v3.0

LeRobot의 내장 변환기를 사용하여 v2.1 → v3.0 형식으로 변환.

| 항목 | 내용 |
|------|------|
| 실행 | `docker exec lerobot_server` 를 통한 subprocess |
| 스크립트 | `lerobot.datasets.v30.convert_dataset_v21_to_v30` |
| 입력 | `{dataset}_lerobot_v21/` |
| 출력 | `{dataset}_lerobot_v30/` |
| 진행률 | 단일 모드: 66% ~ 100% / Merge 모드: 68% ~ 100% |

### v2.1 vs v3.0 차이점

| 항목 | v2.1 | v3.0 |
|------|------|------|
| 데이터 파일 | 에피소드당 1 Parquet | 여러 에피소드를 하나의 Parquet에 통합 |
| 에피소드 메타 | `episodes.jsonl` (JSONL) | `episodes/chunk-000/file-000.parquet` (Parquet) |
| 태스크 | `tasks.jsonl` (JSONL) | `tasks.parquet` (Parquet) |
| 통계 | `episodes_stats.jsonl` (에피소드별) | `stats.json` (전체 통합) |
| 비디오 | 에피소드별 MP4 | 에피소드를 연결한 MP4 |

### 변환 후 폴더 정리
lerobot 변환기는 in-place로 동작:
1. 원본 v2.1 디렉토리 → `{name}_lerobot_v21_old` 으로 이동
2. 새 v3.0 데이터 → 원본 v2.1 디렉토리 자리에 생성
3. Worker가 이름 교환: v3.0 → `_lerobot_v30`, old → `_lerobot_v21` 복원

---

## Orchestration

`Mp4ConversionWorker` (`mp4_conversion_worker.py`)가 전체 파이프라인을 관리.

### 실행 흐름
```
physical_ai_server.py (ROS2 서비스)
  └─ CONVERT_MP4 command 수신
       └─ Mp4ConversionWorker (multiprocessing.Process)
            ├─ Stage 0: _merge_episodes()        [merge 모드만]
            ├─ Stage 1: _convert_dataset()        [ScaleAIConverter]
            ├─ Stage 2: _convert_to_lerobot_v21() [RosbagToLerobotConverter]
            └─ Stage 3: _convert_to_lerobot_v30() [docker exec lerobot_server]
```

### 진행률 (Progress)

| 단계 | 단일 모드 | Merge 모드 |
|------|-----------|------------|
| Stage 0 (Merge) | - | 0% ~ 5% |
| Stage 1 (MP4) | 0% ~ 33% | 5% ~ 35% |
| Stage 2 (v2.1) | 33% ~ 66% | 35% ~ 68% |
| Stage 3 (v3.0) | 66% ~ 100% | 68% ~ 100% |

### 에러 처리
- 각 Stage 실패 시 에러 메시지와 함께 중단
- 에러 형식: `[Stage N/3 {name}] {message}`
- Merge 모드: 소스 폴더 미존재, 출력 폴더 이미 존재 시 실패

---

## Files

| 파일 | 역할 |
|------|------|
| `mp4_conversion_worker.py` | 파이프라인 오케스트레이션, Stage 0 (Merge) |
| `convert_rosbag2mp4.py` | Stage 1 - ScaleAIConverter |
| `rosbag_to_lerobot_converter.py` | Stage 2 - RosbagToLerobotConverter |
| `rosbag_to_lerobot_v30_converter.py` | Stage 3 보조 (RosbagToLerobotV30Converter) |
| `bag_reader.py` | MCAP 파일 읽기 유틸리티 |
| `metadata_manager.py` | robot_config.yaml 파싱, trim/exclude 관리 |
| `video_metadata_extractor.py` | 비디오 메타데이터 추출 |
| `progress_tracker.py` | 진행률 추적 |

---

## Docker Containers

| 컨테이너 | 역할 |
|-----------|------|
| `physical_ai_server` | Stage 0, 1, 2 실행 (ROS2 환경) |
| `lerobot_server` | Stage 3 실행 (lerobot 환경, `/workspace` 공유) |

두 컨테이너는 `/workspace` 볼륨을 공유하므로 Stage 2 출력을 Stage 3에서 직접 접근 가능.
