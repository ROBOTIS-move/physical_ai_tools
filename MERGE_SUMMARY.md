# Merge Summary: feature-add-new-topic + feature-1.0.0

**Branch**: `feature-temp-merge`
**Date**: 2026-02-09
**Commit**: `4152080` (Merge branch 'feature-1.0.0' into feature-temp-merge)
**Test**: 50/50 passed (physical_ai_server/tests/data_processing/)

---

## 1. Docker / Infrastructure

| File | Decision | Description |
|------|----------|-------------|
| `docker/docker-compose.yml` | **feature-1.0.0** | Added lerobot, groot containers. Zenoh shared memory (`ipc: host`, `/dev/shm`). `RMW_IMPLEMENTATION=rmw_zenoh_cpp` |
| `docker/container.sh` | **feature-1.0.0** | Auto architecture detection (`uname -m`), `docker compose pull --ignore-pull-failures`, `--build` |
| `physical_ai_server/Dockerfile.amd64` | **feature-1.0.0** | Installed `rmw_zenoh_cpp`. Build using `COPY .` method. Removed in-container lerobot installation (separate container) |
| `physical_ai_server/Dockerfile.arm64` | **feature-1.0.0** | Same as amd64 + ARM numpy/pandas compatibility, Zenoh shared memory config |
| `.dockerignore` | **feature-1.0.0** (new) | Docker build optimization |

**Verification point**: Check whether 3 containers (physical_ai_server, lerobot, groot) start normally with Docker compose

---

## 2. Communication (Zenoh migration)

| File | Decision | Description |
|------|----------|-------------|
| `communication/__init__.py` | **feature-1.0.0** | Added `ZenohLeRobotClient` import |
| `communication/communicator.py` | **Both merged** | feature-1.0.0: `ReplayDataHandler`, `GetReplayData` service, `BrowseFile` / HEAD: `action_event_publisher`, `joystick_handler`, `register_joystick_handler` |
| `communication/multi_subscriber.py` | **HEAD** | Kept `rclpy.qos` import style |
| `communication/zenoh_lerobot_client.py` | **feature-1.0.0** (new) | Zenoh-based LeRobot communication client |

**Verification points**:
- Check whether Zenoh communication works properly
- Check whether action_event publishing works properly (HEAD feature)
- Check whether joystick handler works (HEAD feature)

---

## 3. Data Processing (conversion pipeline)

| File | Decision | Description |
|------|----------|-------------|
| `data_processing/__init__.py` | **Both merged** | HEAD's try/except converter imports + feature-1.0.0's `ReplayDataHandler` |
| `data_processing/bag_reader.py` | **HEAD** | mcap-based implementation (`mcap.reader.make_reader`, `mcap_ros2.decoder.DecoderFactory`) |
| `data_processing/data_manager.py` | **HEAD** | Direct HuggingFace import, URDF mesh copy, `needs_review` flag, `device_serial`, `episode_info.json` |
| `data_processing/lerobot_dataset_wrapper.py` | **HEAD** | Direct lerobot import, `write_episode`/`write_episode_stats` API |
| `data_processing/video_metadata_extractor.py` | **HEAD** | New camera naming (`/robot/camera/{cam_name}/`) + legacy pattern fallback. Includes leading underscore matching bug fix |
| `data_processing/convert_rosbag2mp4.py` | **HEAD** (no conflict) | MP4 conversion script |
| `data_processing/rosbag_to_lerobot_converter.py` | **HEAD** (no conflict) | rosbag-to-lerobot converter |
| `data_processing/replay_data_handler.py` | **feature-1.0.0** (new) | Replay data handler |

**Verification points**:
- Check whether rosbag -> lerobot conversion works properly
- Check whether MP4 conversion works properly
- Check whether both new camera naming and legacy naming are recognized

---

## 4. Core Server (`physical_ai_server.py`)

| File | Decision | Description |
|------|----------|-------------|
| `physical_ai_server.py` | **Both merged** (most complex) | Details below |

**Features brought from HEAD:**
- `Mp4ConversionWorker` (MP4 conversion background worker)
- `action_event` publishing
- Saving `needs_review` flag on cancel
- `_auto_create_recording_session`
- `CONVERT_MP4` command handling
- `register_joystick_handler`

**Features brought from feature-1.0.0:**
- `ZenohInferenceManager` / `ZenohTrainingManager`
- `ReplayDataHandler` / `VideoFileServer`
- `get_replay_data_callback` / `browse_file_callback`
- `_init_video_server`

**Verification points**:
- Check whether MP4 conversion command (`CONVERT_MP4 = 9`) is handled properly
- Check whether Zenoh inference/training initializes correctly
- Check whether replay data requests receive responses
- Check whether the review flag is saved when recording is cancelled

---

## 5. Inference / Training

| File | Decision | Description |
|------|----------|-------------|
| `inference/__init__.py` | **feature-1.0.0** | `ZenohInferenceManager` import |
| `inference/zenoh_inference_manager.py` | **feature-1.0.0** (new) | Zenoh-based inference manager |
| `training/__init__.py` | **feature-1.0.0** | `ZenohTrainingManager` import |
| `training/zenoh_training_manager.py` | **feature-1.0.0** (new) | Zenoh-based training manager |

**Verification point**: Whether the inference/training pipeline works via Zenoh

---

## 6. Manager UI (React)

### Based on feature-1.0.0 (UI feature additions)

| File | Changes |
|------|---------|
| `App.js` | Added Replay page routing, sidebar button |
| `ControlPanel.js` | Added ProgressBar, `proceedTime / totalTime` display |
| `DatasetSelector.js` | Replaced with FileBrowserModal + DatasetDownloadModal approach |
| `EpisodeStatus.js` | Display `currentEpisode / numEpisodes` |
| `ImageGridCell.js` | Streaming port 8080 -> 8085 |
| `PolicyDownloadModal.js` | Improved repo ID validation UI, collapsible token section |
| `pageType.js` | Added `REPLAY` page type |
| `trainingSlice.js` | Added `selectedCheckpoint` state |
| `store.js` | Registered `replaySlice` reducer |
| `package.json` / `package-lock.json` | Added `recharts` dependency |

### Preserved HEAD-specific features

| File | Preserved feature |
|------|-------------------|
| `taskCommand.js` | `CONVERT_MP4: 9` command |
| `taskPhases.js` | `CONVERTING: 7` phase |
| `InfoPanel.js` | Convert MP4 button UI, `isConverting` state, `handleConvertMp4` handler |

### Both merged

| File | HEAD | feature-1.0.0 |
|------|------|--------------|
| `useRosServiceCaller.js` | `convert_mp4` command | `browseFile` array handling, `getReplayData`/`getRosbagList` |
| `useRosTopicSubscription.js` | `actionEventTopicRef`, `speakText` (voice feedback) | recording beep sound |

### New files from feature-1.0.0

- `CheckpointSelector.js` - Checkpoint selection UI
- `DatasetDownloadModal.js` - Dataset download modal
- `replay/` components (JointChart, PlaybackControls, RosbagInfoPanel, VideoPlayer)
- `ReplayPage.js` - Full replay page
- `useHybridVideoLoader.js`, `useKeyboardShortcuts.js`, `useVideoSync.js` - Hooks for replay
- `chartUtils.js` - Chart utilities
- `replaySlice.js` - Replay Redux state

**Verification points**:
- Check whether Replay page loads properly
- Check whether Convert MP4 button works
- Check whether voice feedback (speakText) works
- Check whether video is visible on streaming port 8085

---

## 7. Interfaces (ROS2 messages/services)

| File | Decision | Description |
|------|----------|-------------|
| `CMakeLists.txt` | **Both merged** | Added 9 items from feature-1.0.0: `TrainingProgress.msg`, `GetReplayData.srv`, etc. |
| `TaskStatus.msg` | **HEAD** | Preserved `CONVERTING = 7` constant |
| `SendCommand.srv` | **HEAD** | Preserved `CONVERT_MP4 = 9` constant |

**New srv/msg from feature-1.0.0**: `CheckpointList`, `GetReplayData`, `ModelList`, `PolicyList`, `StartInference`, `StopTraining`, `TrainModel`, `TrainingStatus`, `TrainingProgress`

**Verification point**: Whether interface build succeeds in `colcon build`

---

## 8. Rosbag Recorder (C++)

| File | Decision | Description |
|------|----------|-------------|
| `CMakeLists.txt` | **feature-1.0.0** | Added `image_compressor`, `image_bag_recorder`, `ImageMetadata.msg` |
| `service_bag_recorder.hpp` | **Both merged** | feature-1.0.0: image handling members / HEAD: `std::atomic<bool> is_recording_` (thread-safe) |
| `service_bag_recorder.cpp` | **Both merged** | feature-1.0.0: `generic_subscriptions_` naming / HEAD: `memory_order_acquire/release`, double-check locking |
| `package.xml` | **Both merged** | feature-1.0.0: Added `cv_bridge`, `image_transport`, `libopencv-dev` |

**New files from feature-1.0.0**: `image_bag_recorder.hpp/cpp`, `image_compressor.hpp/cpp`, `ImageMetadata.msg`, `recorder_config.yaml`

**Verification points**:
- Check whether rosbag_recorder builds in `colcon build`
- Check whether image recording works
- Check whether `std::atomic` thread safety works properly

---

## 9. Third Party (new - feature-1.0.0)

| Directory | Contents |
|-----------|----------|
| `third_party/lerobot/` | Dockerfile (amd64/arm64), executor.py, entrypoint.sh, lerobot submodule |
| `third_party/groot/` | Dockerfile (amd64/arm64), executor.py, entrypoint.sh, Isaac-GR00T submodule |
| `third_party/zenoh_ros2_sdk` | Zenoh ROS2 SDK submodule |

---

## 10. Config / Launch

| File | Decision | Description |
|------|----------|-------------|
| `ffw_sg2_rev1_config.yaml` | **HEAD** | Preserved `follower_mobile` joints (`linear_x`, `linear_y`, `angular_z`) |
| `physical_ai_server_bringup.launch.py` | **feature-1.0.0** | rosbridge `fragment_timeout: 600`, `max_message_size: 100MB`, web_video_server `port: 8085` |
| `.gitmodules` | **Both merged** | HEAD: `lerobot` (feature-robotis) / feature-1.0.0: `third_party/lerobot`, `zenoh_ros2_sdk`, `groot/Isaac-GR00T` |
| `.gitignore` | **Both merged** | feature-1.0.0: Added `.claude/`, third_party workspace, model file patterns |

---

## Bug fixes (discovered during merge)

| File | Fix details |
|------|-------------|
| `video_metadata_extractor.py` | Fixed leading underscore matching failure in `_find_matching_topic`. Applied `lstrip("_")` when comparing video filename `_zed_...` with sanitized topic `zed_...` |

---

## Build/test checklist

- [ ] `colcon build` succeeds (interfaces, recorder, server)
- [ ] Docker compose (3 containers) starts normally
- [ ] data_processing tests 50/50 passed (verified)
- [ ] Data acquisition (rosbag recording) works properly
- [ ] MP4 conversion works properly
- [ ] rosbag -> lerobot conversion works properly
- [ ] Replay page loads and works
- [ ] Zenoh inference/training pipeline
- [ ] Web UI streaming (port 8085)
- [ ] joystick handler / action event
