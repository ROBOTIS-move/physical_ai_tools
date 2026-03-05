# gr00t inference.py에 RobotClient 도입

## Context

gr00t inference.py가 ROS2 subscriber를 직접 생성/관리하고 있는데, 이 로직은 RobotClient가 이미 제공하는 기능과 완전히 중복된다. RobotClient를 도입하면 inference 코드가 크게 단순화되고, 앞으로 새 모델 추가 시 동일한 패턴을 따를 수 있다.

gr00t에서 먼저 검증 후 lerobot에도 동일하게 적용 예정.

---

## 수정 파일 (6개)

### Part 1: `robot_type` 서비스 필드 추가 (5개)

| # | 파일 | 변경 |
|---|------|------|
| 1 | `physical_ai_interfaces/srv/StartInference.srv` | `string robot_type` 필드 추가 |
| 2 | `third_party/robot_client/robot_client/messages/__init__.py` | 동일하게 `string robot_type` 추가 (CDR 호환) |
| 3 | `physical_ai_server/.../communication/zenoh_service_client.py` | `start_inference()`에 `robot_type` 파라미터 추가 |
| 4 | `physical_ai_server/.../inference/inference_manager.py` | `start()`에 `robot_type` 파라미터 추가 |
| 5 | `physical_ai_server/.../physical_ai_server.py` | `self.robot_type` 전달 |

-- 코멘트: 근데, physical ai manager UI에서 처음 홈에서 로봇 타입을 고른 후 데이터 취득. 학습, 추론 ... 등등 기능을 활용하거든. 그래서 내 생각에는 굳이 robot type을 모두 가져갈 필요는 없지 않나 싶긴한데. 어떻게 생각해? 내가 잘못 생각하고 있는건가 ... 한번 UI에서 선택하는것부터 Inference가 될때까지 구조를 시각적으로 보면 좋겠어.

### Part 2: gr00t inference 리팩터링 (1개)

| # | 파일 | 변경 |
|---|------|------|
| 6 | `third_party/groot/inference.py` | 수동 subscriber → RobotClient로 교체 |

---

## Part 1: robot_type 서비스 필드 추가

### 1.1 StartInference.srv

```diff
 string model_path
 string embodiment_tag
 string[] camera_topic_map
 string[] joint_topic_map
 string task_instruction
+string robot_type
```

### 1.2 messages/__init__.py

`START_INFERENCE_REQUEST_DEF`에 동일하게 `string robot_type` 추가 (필드 순서 반드시 .srv와 동일)

### 1.3 zenoh_service_client.py (~line 310)

```python
def start_inference(self, ..., robot_type: str = ""):
    request.robot_type = robot_type
```

### 1.4 inference_manager.py (~line 103)

```python
def start(self, ..., robot_type: str = ""):
    response = self._client.start_inference(..., robot_type=robot_type)
```

### 1.5 physical_ai_server.py (~line 831)

```python
self.inference_manager.start(
    ...,
    robot_type=self.robot_type,
)
```

---

## Part 2: gr00t inference.py 리팩터링

### 모듈 상태 변경

```python
# 제거
_ros2_subscribers: list = []
_latest_observations: dict = {"video": {}, "state": {}, "language": {}, "timestamp": None}

# 추가
_robot_client: Optional[RobotClient] = None
_video_keys: list = []     # 모델이 사용하는 카메라 modality keys  
_state_keys: list = []     # 모델이 사용하는 조인트 modality keys
```

-- 코멘트: 여기에서는 video_keys, state_keys는 어디에서 받아오는거야? robot type에 따라서 달라질텐데. 아니면 모델에서 받아오는건가 어떻게 이 정보를 받아올거야? 그리고 video_keysㅇ와 매칭되는 topic name은 어떻게 가져올거야? 그리고, 변수들 앞에 _가 있는게 별로 마음에 들지 않아.

### import 변경

```python
# 제거: from zenoh_ros2_sdk import ROS2Subscriber
# 추가: from robot_client import RobotClient
```

### load_policy() 수정

```python
def load_policy(server, request):
    robot_type = request.robot_type  # 새 필드

    # 1. 모델 로드 (기존과 동일)
    _loaded_policy = _load_groot_policy(model_path, embodiment_tag)

    # 2. modality config에서 키 추출 (기존과 동일)
    video_keys, state_keys, action_keys, language_keys = ...

    # 3. RobotClient 생성 (topic map 파싱 + subscriber 생성 대체)
    _robot_client = RobotClient(robot_type)

    # 4. YAML 키 → modality 키 매핑 및 필터링
    active_cameras = [k for k in _robot_client.camera_names if k in video_keys]
    active_joints = _get_active_follower_joints(_robot_client, state_keys)
    # → {"arm_left": "follower_arm_left", "arm_right": "follower_arm_right", ...}

    # 5. 센서 준비 대기
    _robot_client.wait_for_ready(timeout=10.0)

    return {action_keys: action_keys}
```

-- 코멘트: 근데 변수 앞에 _를 붙이는건 왜그러는거야? 굳이 붙이고 싶지 않은데... 

### 새 헬퍼: _get_active_follower_joints()

```python
def _get_active_follower_joints(robot_client, state_keys) -> dict:
    """YAML follower 그룹 → modality key 매핑.
    follower_arm_left → arm_left (state_keys에 있는 것만)
    Returns: {modality_key: yaml_group_name}
    """
    result = {}
    for group_name, cfg in robot_client._config["joint_groups"].items():
        if cfg.get("role") != "follower":
            continue
        modality_key = group_name.removeprefix("follower_")
        if modality_key in state_keys:
            result[modality_key] = group_name
    return result
```

### get_action_chunk() 수정

```python
def get_action_chunk(server, request):
    # 1. RobotClient에서 이미지 조회
    images = _robot_client.get_images(resize=IMAGE_SIZE, format="rgb")

    # 2. 카메라별: 회전 적용 → (1, 1, H, W, C) 변환
    for cam_key in _video_keys:
        img = images[cam_key]
        img = apply_rotation_if_configured(img)
        video_obs[cam_key] = img[np.newaxis, np.newaxis, ...]

    -- 코멘트: 여기에 회전 적용하는 것도 get_images에 들어가면 안되나? 그럼 좀 더 간결해질 것 같은데. 만약 파라미터가 없다면, 그냥 로테이션 안하면 되는거고. 로테이션 필요한 카메라가 있으면 그 카메라 이름을 list로 넣어주면 될 것 같긴한데...

    # 3. follower 조인트별: (D,) → (1, 1, D) 변환
    for modality_key, yaml_group in active_joints.items():
        positions = _robot_client.get_joint_positions(group=yaml_group)
        state_obs[modality_key] = positions[np.newaxis, np.newaxis, :]

    # 4. inference 실행 (기존과 동일)
    observation = {"video": video_obs, "state": state_obs, "language": language_obs}
    action, info = _loaded_policy.get_action(observation)
```

### cleanup_inference() 수정

```python
def cleanup_inference():
    if _robot_client is not None:
        _robot_client.close()
        _robot_client = None
    # 모델 정리 (기존과 동일)
```

### 제거되는 코드

| 함수/변수 | 이유 |
|-----------|------|
| `_parse_topic_map()` | RobotClient가 YAML에서 자동 처리 |
| `_parse_camera_rotations()` | 미사용 헬퍼 |
| `_setup_ros2_subscribers()` | `RobotClient.__init__()` 대체 |
| `_on_image_received()` | `RobotClient._update_image()` 대체 |
| `_on_joint_state_received()` | `RobotClient._update_joint()` 대체 |
| `_latest_observations` | `_robot_client.get_*()` API 대체 |
| `_ros2_subscribers` | `_robot_client.close()` 대체 |

-- 코멘트: 이 함수들 앞에도 _가 있는게 별로 보기 좋지 않아.
---

## 키 매핑 정리

| 소스 | YAML 키 | modality 키 | 규칙 |
|------|---------|------------|------|
| 카메라 | `cam_left_head` | `cam_left_head` | 1:1 동일 |
| 조인트 | `follower_arm_left` | `arm_left` | `follower_` 제거 |
| 조인트 | `leader_arm_left` | - | 무시 (inference에 불필요) |

## 데이터 변환 정리

| RobotClient 반환 | gr00t 기대 | 변환 |
|-----------------|-----------|------|
| `(H, W, 3)` RGB ndarray | `(1, 1, H, W, C)` | `img[np.newaxis, np.newaxis, ...]` |
| `(D,)` float32 ndarray | `(1, 1, D)` | `pos[np.newaxis, np.newaxis, :]` |

---

## Verification

1. **physical_ai_interfaces 빌드:**
   ```bash
   cd /home/rc/workspace/physical_ai_tools && colcon build --packages-select physical_ai_interfaces
   ```

2. **gr00t inference import 테스트:**
   ```bash
   docker exec -it groot_server python3 -c "from inference import load_policy, get_action_chunk; print('OK')"
   ```

3. **RobotClient 연동 테스트 (rosbag 재생 중):**
   ```bash
   docker exec -it groot_server python3 -c "
   from robot_client import RobotClient
   rc = RobotClient('ffw_sg2_rev1')
   rc.wait_for_ready(timeout=10)
   print(rc.get_status())
   rc.close()
   "
   ```

4. **End-to-end:** physical_ai_manager UI → START_INFERENCE → groot_server logs 확인
