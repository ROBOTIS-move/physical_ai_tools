# Merge Summary: feature-add-new-topic + feature-1.0.0

**Branch**: `feature-temp-merge`
**Date**: 2026-02-09
**Commit**: `4152080` (Merge branch 'feature-1.0.0' into feature-temp-merge)
**Test**: 50/50 passed (physical_ai_server/tests/data_processing/)

---

## 1. Docker / Infrastructure

| 파일 | 결정 | 설명 |
|------|------|------|
| `docker/docker-compose.yml` | **feature-1.0.0** | lerobot, groot 컨테이너 추가. Zenoh shared memory (`ipc: host`, `/dev/shm`). `RMW_IMPLEMENTATION=rmw_zenoh_cpp` |
| `docker/container.sh` | **feature-1.0.0** | 아키텍처 자동감지 (`uname -m`), `docker compose pull --ignore-pull-failures`, `--build` |
| `physical_ai_server/Dockerfile.amd64` | **feature-1.0.0** | `rmw_zenoh_cpp` 설치. `COPY .` 방식 빌드. lerobot 인컨테이너 설치 제거 (별도 컨테이너) |
| `physical_ai_server/Dockerfile.arm64` | **feature-1.0.0** | amd64와 동일 + ARM numpy/pandas 호환성, Zenoh shared memory config |
| `.dockerignore` | **feature-1.0.0** (신규) | Docker 빌드 최적화 |

**확인 포인트**: Docker compose로 3개 컨테이너 (physical_ai_server, lerobot, groot)가 정상 올라오는지

---

## 2. Communication (Zenoh 전환)

| 파일 | 결정 | 설명 |
|------|------|------|
| `communication/__init__.py` | **feature-1.0.0** | `ZenohLeRobotClient` import 추가 |
| `communication/communicator.py` | **양쪽 머지** | feature-1.0.0: `ReplayDataHandler`, `GetReplayData` 서비스, `BrowseFile` / HEAD: `action_event_publisher`, `joystick_handler`, `register_joystick_handler` |
| `communication/multi_subscriber.py` | **HEAD** | `rclpy.qos` import 스타일 유지 |
| `communication/zenoh_lerobot_client.py` | **feature-1.0.0** (신규) | Zenoh 기반 LeRobot 통신 클라이언트 |

**확인 포인트**:
- Zenoh 통신이 정상 동작하는지
- action_event 퍼블리시가 정상인지 (HEAD 기능)
- joystick handler가 동작하는지 (HEAD 기능)

---

## 3. Data Processing (변환 파이프라인)

| 파일 | 결정 | 설명 |
|------|------|------|
| `data_processing/__init__.py` | **양쪽 머지** | HEAD의 try/except converter imports + feature-1.0.0의 `ReplayDataHandler` |
| `data_processing/bag_reader.py` | **HEAD** | mcap 기반 구현 (`mcap.reader.make_reader`, `mcap_ros2.decoder.DecoderFactory`) |
| `data_processing/data_manager.py` | **HEAD** | HuggingFace 직접 import, URDF mesh 복사, `needs_review` 플래그, `device_serial`, `episode_info.json` |
| `data_processing/lerobot_dataset_wrapper.py` | **HEAD** | lerobot 직접 import, `write_episode`/`write_episode_stats` API |
| `data_processing/video_metadata_extractor.py` | **HEAD** | 새 카메라 네이밍 (`/robot/camera/{cam_name}/`) + 레거시 패턴 fallback. leading underscore 매칭 버그 수정 포함 |
| `data_processing/convert_rosbag2mp4.py` | **HEAD** (충돌 없음) | MP4 변환 스크립트 |
| `data_processing/rosbag_to_lerobot_converter.py` | **HEAD** (충돌 없음) | rosbag-to-lerobot 변환기 |
| `data_processing/replay_data_handler.py` | **feature-1.0.0** (신규) | 리플레이 데이터 핸들러 |

**확인 포인트**:
- rosbag -> lerobot 변환이 정상 동작하는지
- MP4 변환이 정상인지
- 새 카메라 네이밍 + 레거시 네이밍 모두 인식되는지

---

## 4. Core Server (`physical_ai_server.py`)

| 파일 | 결정 | 설명 |
|------|------|------|
| `physical_ai_server.py` | **양쪽 머지** (가장 복잡) | 아래 상세 |

**HEAD에서 가져온 기능:**
- `Mp4ConversionWorker` (MP4 변환 백그라운드 워커)
- `action_event` 퍼블리싱
- cancel 시 `needs_review` 플래그 저장
- `_auto_create_recording_session`
- `CONVERT_MP4` 커맨드 처리
- `register_joystick_handler`

**feature-1.0.0에서 가져온 기능:**
- `ZenohInferenceManager` / `ZenohTrainingManager`
- `ReplayDataHandler` / `VideoFileServer`
- `get_replay_data_callback` / `browse_file_callback`
- `_init_video_server`

**확인 포인트**:
- MP4 변환 커맨드 (`CONVERT_MP4 = 9`)가 정상 처리되는지
- Zenoh inference/training이 초기화되는지
- replay 데이터 요청이 응답되는지
- 녹화 cancel 시 review 플래그가 저장되는지

---

## 5. Inference / Training

| 파일 | 결정 | 설명 |
|------|------|------|
| `inference/__init__.py` | **feature-1.0.0** | `ZenohInferenceManager` import |
| `inference/zenoh_inference_manager.py` | **feature-1.0.0** (신규) | Zenoh 기반 추론 매니저 |
| `training/__init__.py` | **feature-1.0.0** | `ZenohTrainingManager` import |
| `training/zenoh_training_manager.py` | **feature-1.0.0** (신규) | Zenoh 기반 학습 매니저 |

**확인 포인트**: Zenoh를 통한 inference/training 파이프라인 동작 여부

---

## 6. Manager UI (React)

### feature-1.0.0 기반 (UI 기능 추가)

| 파일 | 변경 내용 |
|------|----------|
| `App.js` | Replay 페이지 라우팅, 사이드바 버튼 추가 |
| `ControlPanel.js` | ProgressBar 추가, `proceedTime / totalTime` 표시 |
| `DatasetSelector.js` | FileBrowserModal + DatasetDownloadModal 방식으로 교체 |
| `EpisodeStatus.js` | `currentEpisode / numEpisodes` 표시 |
| `ImageGridCell.js` | 스트리밍 포트 8080 -> 8085 |
| `PolicyDownloadModal.js` | repo ID 검증 UI 개선, 접이식 토큰 섹션 |
| `pageType.js` | `REPLAY` 페이지 타입 추가 |
| `trainingSlice.js` | `selectedCheckpoint` state 추가 |
| `store.js` | `replaySlice` 리듀서 등록 |
| `package.json` / `package-lock.json` | `recharts` 의존성 추가 |

### HEAD 고유 기능 보존

| 파일 | 보존된 기능 |
|------|------------|
| `taskCommand.js` | `CONVERT_MP4: 9` 커맨드 |
| `taskPhases.js` | `CONVERTING: 7` 페이즈 |
| `InfoPanel.js` | Convert MP4 버튼 UI, `isConverting` 상태, `handleConvertMp4` 핸들러 |

### 양쪽 머지

| 파일 | HEAD | feature-1.0.0 |
|------|------|--------------|
| `useRosServiceCaller.js` | `convert_mp4` 커맨드 | `browseFile` 배열 처리, `getReplayData`/`getRosbagList` |
| `useRosTopicSubscription.js` | `actionEventTopicRef`, `speakText` (음성 피드백) | recording beep 사운드 |

### feature-1.0.0 신규 파일

- `CheckpointSelector.js` - 체크포인트 선택 UI
- `DatasetDownloadModal.js` - 데이터셋 다운로드 모달
- `replay/` 컴포넌트 (JointChart, PlaybackControls, RosbagInfoPanel, VideoPlayer)
- `ReplayPage.js` - 리플레이 페이지 전체
- `useHybridVideoLoader.js`, `useKeyboardShortcuts.js`, `useVideoSync.js` - 리플레이용 훅
- `chartUtils.js` - 차트 유틸리티
- `replaySlice.js` - 리플레이 Redux 상태

**확인 포인트**:
- Replay 페이지가 정상 로드되는지
- Convert MP4 버튼이 동작하는지
- 음성 피드백 (speakText)이 동작하는지
- 스트리밍 포트 8085에서 영상이 보이는지

---

## 7. Interfaces (ROS2 메시지/서비스)

| 파일 | 결정 | 설명 |
|------|------|------|
| `CMakeLists.txt` | **양쪽 머지** | feature-1.0.0의 `TrainingProgress.msg`, `GetReplayData.srv` 등 9개 추가 |
| `TaskStatus.msg` | **HEAD** | `CONVERTING = 7` 상수 보존 |
| `SendCommand.srv` | **HEAD** | `CONVERT_MP4 = 9` 상수 보존 |

**feature-1.0.0 신규 srv/msg**: `CheckpointList`, `GetReplayData`, `ModelList`, `PolicyList`, `StartInference`, `StopTraining`, `TrainModel`, `TrainingStatus`, `TrainingProgress`

**확인 포인트**: `colcon build`에서 인터페이스 빌드가 성공하는지

---

## 8. Rosbag Recorder (C++)

| 파일 | 결정 | 설명 |
|------|------|------|
| `CMakeLists.txt` | **feature-1.0.0** | `image_compressor`, `image_bag_recorder`, `ImageMetadata.msg` 추가 |
| `service_bag_recorder.hpp` | **양쪽 머지** | feature-1.0.0: image handling 멤버들 / HEAD: `std::atomic<bool> is_recording_` (thread-safe) |
| `service_bag_recorder.cpp` | **양쪽 머지** | feature-1.0.0: `generic_subscriptions_` 네이밍 / HEAD: `memory_order_acquire/release`, double-check locking |
| `package.xml` | **양쪽 머지** | feature-1.0.0: `cv_bridge`, `image_transport`, `libopencv-dev` 추가 |

**feature-1.0.0 신규 파일**: `image_bag_recorder.hpp/cpp`, `image_compressor.hpp/cpp`, `ImageMetadata.msg`, `recorder_config.yaml`

**확인 포인트**:
- `colcon build`에서 rosbag_recorder가 빌드되는지
- image recording이 동작하는지
- `std::atomic` thread safety가 정상인지

---

## 9. Third Party (신규 - feature-1.0.0)

| 디렉토리 | 내용 |
|----------|------|
| `third_party/lerobot/` | Dockerfile (amd64/arm64), executor.py, entrypoint.sh, lerobot submodule |
| `third_party/groot/` | Dockerfile (amd64/arm64), executor.py, entrypoint.sh, Isaac-GR00T submodule |
| `third_party/zenoh_ros2_sdk` | Zenoh ROS2 SDK submodule |

---

## 10. Config / Launch

| 파일 | 결정 | 설명 |
|------|------|------|
| `ffw_sg2_rev1_config.yaml` | **HEAD** | `follower_mobile` 조인트 (`linear_x`, `linear_y`, `angular_z`) 보존 |
| `physical_ai_server_bringup.launch.py` | **feature-1.0.0** | rosbridge `fragment_timeout: 600`, `max_message_size: 100MB`, web_video_server `port: 8085` |
| `.gitmodules` | **양쪽 머지** | HEAD: `lerobot` (feature-robotis) / feature-1.0.0: `third_party/lerobot`, `zenoh_ros2_sdk`, `groot/Isaac-GR00T` |
| `.gitignore` | **양쪽 머지** | feature-1.0.0: `.claude/`, third_party 워크스페이스, 모델 파일 패턴 추가 |

---

## 버그 수정 (머지 과정에서 발견)

| 파일 | 수정 내용 |
|------|----------|
| `video_metadata_extractor.py` | `_find_matching_topic`에서 leading underscore 매칭 실패 수정. 비디오 파일명 `_zed_...`과 sanitized topic `zed_...` 비교 시 `lstrip("_")` 적용 |

---

## 빌드/테스트 체크리스트

- [ ] `colcon build` 성공 (interfaces, recorder, server)
- [ ] Docker compose (3 컨테이너) 정상 기동
- [ ] data_processing 테스트 50/50 통과 (확인 완료)
- [ ] 데이터 취득 (rosbag recording) 정상
- [ ] MP4 변환 정상
- [ ] rosbag -> lerobot 변환 정상
- [ ] Replay 페이지 로드 및 동작
- [ ] Zenoh inference/training 파이프라인
- [ ] 웹 UI 스트리밍 (포트 8085)
- [ ] joystick handler / action event
