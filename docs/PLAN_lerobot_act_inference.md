# LeRobot ACT Inference 테스트를 위한 코드 수정 계획

## Context

GR00T inference 테스트는 완료된 상태. 이제 LeRobot Docker에서 ACT 정책의 학습과 inference를 테스트하려 한다. 테스트 플로우는 `physical_ai_manager → physical_ai_server → lerobot` Docker 파이프라인을 통해 사용자가 직접 수행한다.

**현재 문제점:**
1. LeRobot `inference.py`가 gr00t과 다른 topic 인터페이스 사용 (단일 joint_topic, camera_topics list vs "name:topic" map)
2. `physical_ai_server.py`의 START_INFERENCE가 `service_prefix="/groot"`로 하드코딩
3. LeRobot inference가 multi-joint-group을 지원하지 않음
4. `action_keys`를 반환하지 않아 InferenceManager의 action_joint_map 구축 불가

**데이터셋:** `ROBOTIS/robotis_1f_demo_dataset_0226_merged` (HuggingFace에서 다운로드)
**Rosbag:** `Dongkkka/ffw_sg2_test_rosbag` (physical_ai_server에서 ros2 bag play)

---

## 수정 1: LeRobot inference.py 리팩터링

### 파일: `third_party/lerobot/inference.py`

gr00t의 inference.py 패턴을 따라서 다음을 수정:

### 1.1 `_parse_topic_map()` 추가
gr00t과 동일한 "name:topic" 파싱 헬퍼 추가:
```python
def _parse_topic_map(topic_map_list: list) -> dict:
    result = {}
    for entry in topic_map_list:
        if ":" in entry:
            name, topic = entry.split(":", 1)
            result[name.strip()] = topic.strip()
    return result
```

### 1.2 `_latest_observations` 구조 변경
```python
# Before (단일 joint)
_latest_observations = {"images": {}, "joint_state": None, "timestamp": None}

# After (multi-joint group, gr00t 패턴)
_latest_observations = {"images": {}, "joint_states": {}, "timestamp": None}
```

### 1.3 `load_policy()` 수정
- `request`에서 `camera_topic_map`, `joint_topic_map`을 "name:topic" 형식으로 파싱
- `joint_topic_map`의 key 목록을 `action_keys`로 반환
- `_inference_config`에 joint modality key 정보 저장

**action_keys 추출 로직:**
- `action_keys = list(joint_topic_map.keys())`
- LeRobot은 단일 concatenated action vector를 출력하므로, joint_topic_map의 modality_key 순서가 action 순서와 일치

### 1.4 `_setup_ros2_subscribers()` 수정
- camera: `{cam_name: topic}` dict 기반 (gr00t 패턴)
- joint: `{modality_key: topic}` dict 기반 다중 group
- 각 joint group마다 per-key 콜백 생성

### 1.5 `_on_joint_state_received()` 수정
- modality_key 파라미터 추가
- `_latest_observations["joint_states"][modality_key]` 에 저장

### 1.6 `get_action_chunk()` 수정
- 다중 joint group의 state를 joint_topic_map 순서대로 concatenate → `observation.state`
- 모든 그룹의 positions를 하나로 합쳐서 모델에 전달

---

## 수정 2: physical_ai_server.py service_prefix 동적 결정

### 파일: `physical_ai_server/physical_ai_server/physical_ai_server.py`

### 2.1 `_determine_service_prefix()` 메서드 추가

**로직:**
1. `task_info`에 `service_type` 필드가 있으면 직접 사용 (예: "lerobot", "groot")
2. 없으면 `policy_path`의 `config.json`에서 policy type 확인
3. ACT, diffusion 등 LeRobot 정책이면 → `/lerobot`
4. 기본값: `/groot` (하위 호환성)

**LEROBOT_POLICIES** (클래스 속성):
```python
LEROBOT_POLICIES = {
    'tdmpc', 'diffusion', 'act', 'vqbet', 'pi0', 'pi0_fast', 'pi05',
    'smolvla', 'xvla', 'sac',
}
```

### 2.2 하드코딩 제거

```python
# Before
service_prefix = "/groot"

# After
service_prefix = self._determine_service_prefix(task_info)
```

### 2.3 response.message 수정

```python
# Before
response.message = 'GR00T inference started'

# After
response.message = f'{service_prefix.strip("/").upper()} inference started'
```

---

## 수정 대상 파일 요약

| # | 파일 | 수정 내용 |
|---|------|-----------|
| 1 | `third_party/lerobot/inference.py` | gr00t 패턴으로 topic map 인터페이스 통일, multi-joint, action_keys 반환 |
| 2 | `physical_ai_server/physical_ai_server/physical_ai_server.py` | service_prefix 동적 결정, response message 범용화 |

---

## 구현 상태: 완료

- [x] inference.py `_parse_topic_map()` 추가
- [x] inference.py `_latest_observations` 구조 변경 (joint_states dict)
- [x] inference.py `load_policy()` topic map 파싱 + action_keys 반환
- [x] inference.py `_setup_ros2_subscribers()` dict 기반으로 변경
- [x] inference.py `_on_joint_state_received()` modality_key 지원
- [x] inference.py `get_action_chunk()` multi-joint concatenation
- [x] inference.py `cleanup_inference()` _action_keys 정리
- [x] physical_ai_server.py `_determine_service_prefix()` 추가
- [x] physical_ai_server.py 하드코딩 `/groot` 제거
- [x] physical_ai_server.py response message 범용화

---

## 구현 요약 (수도코드)

### `third_party/lerobot/inference.py`

**모듈 상태 변수:**
```
_loaded_model = None
_inference_config = None        # {model_path, camera_topic_map, joint_topic_map, joint_modality_keys}
_ros2_subscribers = []
_latest_observations = {images: {}, joint_states: {}, timestamp: None}
_action_keys = []               # [NEW] joint group 순서 = action 순서
```

**`_parse_topic_map(topic_map_list) -> dict`** [NEW]
```
# ["arm_left:/joint_states", "gripper_left:/gripper"] -> {"arm_left": "/joint_states", ...}
for entry in list:
    name, topic = entry.split(":", 1)
    result[name] = topic
```

**`load_policy(server, request) -> dict`** [MODIFIED]
```
model = _load_lerobot_policy(model_path)

# Before: camera_topics(list), joint_topic(str)
# After:  camera_topic_map(dict), joint_topic_map(dict) — "name:topic" 파싱
camera_topic_map = _parse_topic_map(request.camera_topic_map)
joint_topic_map  = _parse_topic_map(request.joint_topic_map)

action_keys = list(joint_topic_map.keys())   # ["arm_left", "gripper_left", ...]
_inference_config["joint_modality_keys"] = action_keys

_setup_ros2_subscribers(server, camera_topic_map, joint_topic_map)
return {success, message, action_keys}       # Before: action_keys=[]
```

**`_setup_ros2_subscribers(server, active_cameras: dict, active_joints: dict)`** [MODIFIED]
```
# Before: camera_topics: list, joint_topic: str (단일)
# After:  active_cameras: {cam_name: topic}, active_joints: {modality_key: topic}

for cam_name, topic in active_cameras.items():
    subscribe(topic, callback=_on_image_received(cam_name))

for modality_key, topic in active_joints.items():       # 다중 joint group
    subscribe(topic, callback=_on_joint_state_received(modality_key))
```

**`_on_joint_state_received(modality_key, msg)`** [MODIFIED]
```
# Before: _latest_observations["joint_state"] = joint_data (단일)
# After:  _latest_observations["joint_states"][modality_key] = joint_data (그룹별)
```

**`get_action_chunk(server, request) -> dict`** [MODIFIED]
```
# 이미지 처리 (변경 없음)
for cam_name, image in obs["images"]:
    observation["observation.images.{cam_name}"] = preprocess(image)

# Before: obs["joint_state"]["positions"] 그대로 사용
# After:  joint_modality_keys 순서대로 모든 그룹 concatenate
all_positions = []
for modality_key in joint_modality_keys:
    all_positions.extend(obs["joint_states"][modality_key]["positions"])
observation["observation.state"] = tensor(all_positions)

action_tensor = model.select_action(batch)
return {action_chunk, chunk_size, action_dim}
```

**`cleanup_inference()`** [MODIFIED]
```
# 기존 + _action_keys = [] 추가
```

### `physical_ai_server/physical_ai_server/physical_ai_server.py`

**`LEROBOT_POLICIES`** [NEW] (클래스 속성)
```
{'tdmpc', 'diffusion', 'act', 'vqbet', 'pi0', 'pi0_fast', 'pi05', 'smolvla', 'xvla', 'sac'}
```

**`_determine_service_prefix(task_info) -> str`** [NEW]
```
if task_info.service_type exists:
    return f"/{service_type}"           # 명시적 지정

if task_info.policy_path exists:
    config = read(policy_path / "config.json")
    if config["type"] in LEROBOT_POLICIES:
        return "/lerobot"               # ACT, diffusion 등

return "/groot"                         # 기본값 (하위 호환)
```

**`START_INFERENCE` 핸들러** [MODIFIED]
```
# Before: service_prefix = "/groot"
# After:  service_prefix = self._determine_service_prefix(task_info)

# Before: response.message = 'GR00T inference started'
# After:  response.message = f'{service_prefix.strip("/").upper()} inference started'
#         → "LEROBOT inference started" 또는 "GROOT inference started"
```

---

## 테스트 플로우 (사용자가 직접 수행)

### Step 1: 학습
physical_ai_manager UI → physical_ai_server → `/lerobot/train` 서비스
- policy_type: `act`
- dataset: `ROBOTIS/robotis_1f_demo_dataset_0226_merged`

### Step 2: Rosbag 다운로드 & 리플레이
```bash
# physical_ai_server 컨테이너에서
huggingface-cli download Dongkkka/ffw_sg2_test_rosbag --repo-type dataset --local-dir /workspace/test_rosbag
ros2 bag play /workspace/test_rosbag --rate 1.0 --loop
```

### Step 3: Inference 테스트
physical_ai_manager UI → physical_ai_server → `/lerobot/infer` + `/lerobot/get_action_chunk`
- policy_path: Step 1에서 생성된 체크포인트 경로
- rosbag 리플레이 중 토픽 수신 → inference → action chunk → JointTrajectory 발행

---

## Verification (코드 수정 검증)

1. **inference.py 문법 검증**: lerobot_server에서 import 테스트
   ```bash
   docker exec -it lerobot_server python3 -c "from inference import load_policy, get_action_chunk; print('OK')"
   ```

2. **서비스 등록 확인**: executor.py가 정상 동작하는지 로그 확인
   ```bash
   docker logs lerobot_server --tail 20
   ```

3. **physical_ai_server 빌드 확인**: 수정 후 컨테이너 재시작
   ```bash
   docker restart physical_ai_server
   docker logs physical_ai_server --tail 20
   ```

---

## 다음 단계: RobotClient 도입으로 inference 단순화

### 배경

현재 `inference.py` (groot, lerobot 모두)는 ROS2 subscriber 생성, 콜백 관리, observation 저장을
직접 구현하고 있다. 이 로직은 `RobotClient`가 이미 제공하는 기능과 완전히 중복된다.

**RobotClient (`third_party/robot_client/robot_client/robot_client.py`)가 제공하는 것:**
- YAML config 기반 자동 구독 (카메라, 조인트, 센서)
- thread-safe 데이터 조회 (`get_images()`, `get_joint_positions()`)
- 통합 observation 조회 (`get_observation()`)
- 센서 준비 대기 (`wait_for_ready()`)
- 자동 정리 (`close()`)

### 효과: inference.py에서 제거 가능한 코드

| 함수/변수 | 역할 | RobotClient 대체 |
|-----------|------|-----------------|
| `_setup_ros2_subscribers()` | subscriber 수동 생성 | `RobotClient.__init__()` |
| `_on_image_received()` | 이미지 콜백 | `RobotClient._update_image()` |
| `_on_joint_state_received()` | 조인트 콜백 | `RobotClient._update_joint()` |
| `_latest_observations` | 수동 상태 관리 | `RobotClient.get_observation()` |
| `_ros2_subscribers` + close 로직 | 수동 정리 | `RobotClient.close()` |

### 방향: YAML config 기반

`robot_type`만 넘기면 RobotClient가 YAML에서 토픽을 자동으로 구독한다.
physical_ai_server에서 `camera_topic_map`/`joint_topic_map` 전달이 불필요해진다.

### 구현 계획 (gr00t 먼저, 이후 lerobot)

#### Phase 1: gr00t inference.py에 RobotClient 도입

**1-1. `load_policy()` 수정**
```
# Before: topic map 파싱 + _setup_ros2_subscribers()
camera_topic_map = _parse_topic_map(request.camera_topic_map)
joint_topic_map = _parse_topic_map(request.joint_topic_map)
_setup_ros2_subscribers(server, active_cameras, active_joints)

# After: RobotClient 생성만
robot_type = request.robot_type        # physical_ai_server에서 전달
_robot_client = RobotClient(robot_type)
_robot_client.wait_for_ready(timeout=10.0)
```

**1-2. `get_action_chunk()` 수정**
```
# Before: _latest_observations에서 수동으로 데이터 조합
obs = _latest_observations
images = obs["video"]
states = obs["state"]

# After: RobotClient에서 한번에 조회
obs = _robot_client.get_observation(resize=(256, 256), format="rgb")
images = obs["images"]                 # {cam_name: ndarray}
joint_positions = obs["joint_positions"]  # {group_name: ndarray}
```

**1-3. `cleanup_inference()` 수정**
```
# Before: subscriber 수동 close
for sub in _ros2_subscribers: sub.close()

# After:
_robot_client.close()
```

**1-4. 제거 가능한 함수/변수**
- `_parse_topic_map()` — 불필요
- `_setup_ros2_subscribers()` — 전체 제거
- `_on_image_received()` — 전체 제거
- `_on_joint_state_received()` — 전체 제거
- `_latest_observations` — 전체 제거
- `_ros2_subscribers` — 전체 제거

**1-5. 해결해야 할 Gap**
- RobotClient의 YAML config에서 `joint_groups` 키 (예: `follower_arm_left`)와
  gr00t modality key (예: `arm_left`) 간 매핑 필요
- RobotClient는 `follower_*` 그룹도 구독하는데, inference에는 follower만 필요
  → `get_joint_positions()` 호출 시 follower 그룹만 필터링
- RobotClient에서 이미지 형식이 BGR인데, gr00t은 RGB 필요
  → `get_images(format="rgb")` 사용
- gr00t은 이미지를 `(1, 1, H, W, C)` shape으로 기대
  → RobotClient 반환값에 차원 추가 필요 (inference.py에서 처리)

#### Phase 2: lerobot inference.py에도 동일 적용

gr00t에서 검증 완료 후 lerobot에도 같은 패턴 적용.
lerobot은 이미지가 `(1, C, H, W)` tensor, state가 `(1, D)` tensor이므로
RobotClient 반환값 → 모델 입력 변환 로직만 다름.

#### Phase 3: physical_ai_server 단순화 (선택)

RobotClient가 YAML에서 토픽을 직접 읽으므로,
physical_ai_server에서 `camera_topic_map`/`joint_topic_map` 조립 & 전달하는 부분을
`robot_type` 문자열 전달로 단순화 가능.

### 참고: RobotClient YAML config 구조 (`ffw_sg2_rev1.yaml`)

```yaml
cameras:
  cam_left_head:
    topic: "/robot/camera/cam_left_head/image_raw/compressed"
    msg_type: "sensor_msgs/msg/CompressedImage"

joint_groups:
  follower_arm_left:
    topic: "/robot/arm_left_follower/joint_states"
    role: "follower"
    joint_names: [arm_l_joint1, ..., gripper_l_joint1]
    dof: 8
  leader_arm_left:
    topic: "/robot/arm_left_leader/joint_states"
    role: "leader"
    ...
```
