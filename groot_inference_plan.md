# Zenoh 기반 GR00T Inference 아키텍처 구현 계획

## Context

현재 `_inference_timer_callback()`이 비활성화("rosbag2-only mode")되어 있고, GR00T executor는 단일 joint topic만 지원하며 continuous inference loop(30Hz)을 돌리는 구조.

**문제점:**
1. physical_ai_server가 데이터를 프록시하는 구조 → 불필요한 레이턴시
2. GR00T가 직접 Zenoh로 토픽을 수신할 수 있는데 활용 못함
3. Continuous loop은 action chunk 기반 비동기 추론과 맞지 않음
4. FFW 로봇의 multi-joint topic (arm_left, arm_right, head, lift, mobile) 미지원

**새 설계:**
- GR00T 컨테이너가 Zenoh로 로봇 토픽을 직접 구독 (이미지 + joint state)
- physical_ai_server는 `/groot/get_action_chunk` 서비스로 action chunk를 요청
- Action buffer에서 10Hz로 1개씩 pop하여 joint command publish
- Buffer가 threshold 이하일 때 background thread에서 다음 chunk 요청

---

## 전체 데이터 흐름

```
Robot Topics (Zenoh)
  ├─ /robot/camera/*/compressed ──────────┐
  ├─ /robot/arm_left_follower/joint_states ┤
  ├─ /robot/arm_right_follower/joint_states┤
  ├─ /robot/head_follower/joint_states ────┤
  ├─ /robot/lift_follower/joint_states ────┘
  │                                     GR00T Container
  │                              ┌─────────────────────────┐
  │                              │ Zenoh subscriber로      │
  │                              │ 직접 토픽 수신           │
  │                              │                         │
  │  /groot/infer (setup) ──────>│ 모델 로드 + 구독 시작    │
  │                              │                         │
  │  /groot/get_action_chunk ───>│ 현재 observation으로     │  --코멘트: 여기에서 observation으로 변환할 때 gr00t에서 등록된 robot config 부분도 생각해야할 것 같아. 현재 /home/hc/gr00t_ws/Isaac-GR00T/examples/ffw_sg2/ffw_sg2_config.py 여기에 우리 로봇의 컨피그를 넣어두거든. 근데 이 컨피그는 ros topic 과는 다른 형태의 이름이 들어가야해. 결국 observation이 dictionary?로 되어 있을 탠데 거기서 해당 데이터의 key가 ffw_sg2_config에 있는 요소들이 들어가야하거든. value 부분은 topic에서 값 부분이 들어가야하고. 무슨 말인지 알거야.
  │                              │ inference 실행           │
  │                              │ → (T,D) action chunk 반환│
  │                              └─────────────────────────┘
  │
  │                           physical_ai_server
  │                    ┌──────────────────────────────┐
  │                    │ GR00TInferenceManager        │
  │                    │ ┌──────────────────────────┐ │
  │                    │ │ Action Buffer [T actions] │ │
  │                    │ │  10Hz timer: pop 1 action │──> /robot/arm_left_leader/joint_states
  │                    │ │  buffer < 6 → request     │──> /robot/arm_right_leader/joint_states
  │                    │ │  next chunk (bg thread)   │──> /robot/head_leader/joint_states
  │                    │ └──────────────────────────┘ │──> /robot/lift_leader/joint_states
  │                    └──────────────────────────────┘
```

---

## 변경 1: GetActionChunk.srv 추가

**파일 (신규)**: `physical_ai_interfaces/srv/GetActionChunk.srv`

```
# Request: task instruction (optional, for language-conditioned policies)
string task_instruction
---
# Response
bool success
string message
float64[] action_chunk    # flattened (T*D) action values
int32 chunk_size          # T (number of timesteps)
int32 action_dim          # D (action dimension per timestep)
```

**파일 (수정)**: `physical_ai_interfaces/CMakeLists.txt`
- `"srv/GetActionChunk.srv"` 항목 추가 (line 41 부근)

---

## 변경 2: StartInference.srv 확장

**파일**: `physical_ai_interfaces/srv/StartInference.srv`

현재:
```
string model_path
string[] image_topics
string joint_state_topic
---
bool success
string message
```

변경:
```
string model_path
string embodiment_tag
string[] image_topics
int32[] image_resize_hw        # [H1, W1, H2, W2, ...] 카메라별 resize 크기  --> 근데 생각해보면 카메라 resize 크기는 모델 input 사이즈 또는 model config 관련된 파일에서 찾아볼 수 있을 것 같긴해. 그래서 굳이 저 resize 정보를 던져줄 필요는 없을듯 
string[] joint_state_topics    # multi-topic 지원 (단수 → 복수)
string[] joint_names           # joint_order 전체 (flat list)
string task_instruction        # language-conditioned policy용
---
bool success
string message
```

---

## 변경 3: GR00T Executor 리팩토링

**파일**: `third_party/groot/executor.py`

### 3-1. InferenceConfig 확장 (line 110-117)

```python
@dataclass
class InferenceConfig:
    model_path: str = ""
    embodiment_tag: str = "new_embodiment"
    inference_freq: float = 10.0      # 변경: 30→10 (action chunk 기반)
    camera_topics: list = field(default_factory=list)
    joint_topics: list = field(default_factory=list)   # 변경: joint_topic(단수) → joint_topics(복수)
    joint_names: list = field(default_factory=list)     # 추가: joint_order flat list
    image_resize_hw: list = field(default_factory=list) # 추가: 카메라별 resize [H,W,...]  --코멘트: 이 부분도 마찬가지로, resize는 모델에서 부터 받아와야 할듯. 
    task_instruction: str = ""                          # 추가
```

### 3-2. ExecutorConfig에 get_action_chunk_service 추가 (line 120-142)

```python
get_action_chunk_service: str = "/groot/get_action_chunk"
```

### 3-3. _handle_infer 수정 (line 747-829)

변경 사항:
- `joint_topic` (단수) → `joint_topics` (복수) 처리
- `image_resize_hw` 파싱하여 카메라별 resize 크기 저장
- `joint_names` 파싱하여 multi-topic merge order 저장
- **continuous inference loop 시작하지 않음** (thread 생성 제거)
- 모델 로드 + subscriber setup까지만 수행
- state를 INFERENCE로 전환하여 get_action_chunk 요청 수신 준비
-- 코멘트: /home/hc/physical_ai_tools/physical_ai_server/config/ffw_sg2_rev1_config.yaml 여기에 있는 topic 들을 써야하는거야. 특히 joint 같은 부분들은 지금 여러 topic으로 쪼개져 있는 부분들이 있어서 그게 observation 부분으로 잘 들어가야할 것 같아. 

```python
# 변경 전: inference_thread 시작
self._inference_thread = threading.Thread(target=self._inference_loop, ...)
self._inference_thread.start()

# 변경 후: setup만 수행, loop 시작하지 않음
self._inference_running = True
self.state = ExecutorState.INFERENCE
# _inference_loop 제거, get_action_chunk service에서 on-demand 호출
```

### 3-4. _setup_ros2_subscribers 수정 (line 864-913)

- 단일 joint_topic → multi-topic 구독
- 각 topic마다 콜백에서 joint_names 기반으로 올바른 인덱스에 값 저장
- `_latest_observations["state"]["joint_positions"]`를 joint_names 순서로 merge된 (1,1,D) array로 유지

```python
def _setup_ros2_subscribers(self, camera_topics, joint_topics, joint_names, image_resize_hw):
    # 카메라 구독 (기존과 동일하되 resize 정보 전달)
    for i, cam_config in enumerate(camera_topics):
        topic = cam_config.get("topic") if isinstance(cam_config, dict) else cam_config
        name = cam_config.get("name", topic.split("/")[-2]) if isinstance(cam_config, dict) else topic.split("/")[-2]
        # resize 크기: image_resize_hw[i*2], image_resize_hw[i*2+1]
        h = image_resize_hw[i*2] if i*2 < len(image_resize_hw) else 0
        w = image_resize_hw[i*2+1] if i*2+1 < len(image_resize_hw) else 0
        sub = ROS2Subscriber(topic=topic, msg_type="sensor_msgs/msg/CompressedImage",
                             callback=make_image_callback(name, h, w))
        self._ros2_subscribers.append(sub)

    # multi-joint 구독
    # joint_names_per_topic: 각 topic에서 어떤 joint_name들이 오는지 매핑
    self._merged_state = np.zeros(len(joint_names), dtype=np.float32)
    for joint_topic in joint_topics:
        sub = ROS2Subscriber(topic=joint_topic, msg_type="sensor_msgs/msg/JointState",
                             callback=make_joint_callback(joint_topic))
        self._ros2_subscribers.append(sub)
```

### 3-5. _on_image_received에 resize 추가 (line 915-930)

```python
def _on_image_received(self, camera_name, msg, target_h=0, target_w=0):
    image_data = np.frombuffer(bytes(msg.data), dtype=np.uint8)
    image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
    if image is not None:
        if target_h > 0 and target_w > 0:
            image = cv2.resize(image, (target_w, target_h))
        image = image[np.newaxis, np.newaxis, ...]  # (1,1,H,W,C)
        self._latest_observations["video"][camera_name] = image
        self._latest_observations["timestamp"] = time.time()
```

### 3-6. _on_multi_joint_state_received 수정 (multi-topic merge)

```python
def _on_multi_joint_state_received(self, topic_name, msg):
    """Multi-topic joint state를 joint_names 순서로 merge."""
    positions = list(msg.position)
    names = list(msg.name)  # JointState.name 필드 활용
    for i, name in enumerate(names):
        if name in self._joint_name_to_index:
            idx = self._joint_name_to_index[name]
            self._merged_state[idx] = positions[i]
    # merged state를 (1,1,D)로 저장
    self._latest_observations["state"]["joint_positions"] = \
        self._merged_state[np.newaxis, np.newaxis, :].copy()
    self._latest_observations["timestamp"] = time.time()
```

### 3-7. _handle_get_action_chunk 추가 (신규 서비스 핸들러)

```python
def _handle_get_action_chunk(self, request):
    """Handle get_action_chunk service request - blocking inference."""
    if self.state != ExecutorState.INFERENCE or self._loaded_policy is None:
        return self._create_response(self._get_action_chunk_service,
            success=False, message="Not in inference mode")

    try:
        obs = self._latest_observations
        if obs["timestamp"] is None or time.time() - obs["timestamp"] > 2.0:
            return self._create_response(self._get_action_chunk_service,
                success=False, message="No recent observations")

        # task instruction
        task = getattr(request, "task_instruction", "") or self._inference_config.task_instruction
        if task:
            obs["language"]["task"] = [[task]]

        observation = {"video": obs["video"], "state": obs["state"], "language": obs["language"]}
        action, info = self._loaded_policy.get_action(observation)

        # action shape: {key: (B, T, D)} - 전체 chunk 반환
        for key, value in action.items():
            if isinstance(value, np.ndarray):
                chunk = value[0]  # (T, D)
                T, D = chunk.shape
                return self._create_action_chunk_response(
                    success=True, chunk=chunk.flatten().tolist(),
                    chunk_size=T, action_dim=D)

        return self._create_response(self._get_action_chunk_service,
            success=False, message="No action output from policy")

    except Exception as e:
        return self._create_response(self._get_action_chunk_service,
            success=False, message=f"Inference failed: {e}")
```

### 3-8. _inference_loop 비활성화

- 기존 continuous loop 코드는 제거하거나 dead code로 남겨둠
- `_handle_infer`에서 thread를 시작하지 않으므로 호출되지 않음

### 3-9. start()에서 get_action_chunk service 등록

```python
self._get_action_chunk_service = ROS2ServiceServer(
    service_name=self.config.get_action_chunk_service,
    service_type="physical_ai_interfaces/srv/GetActionChunk",
    handler=self._handle_get_action_chunk,
    mode="queue"
)
```

---

## 변경 4: GR00TInferenceManager (신규)

**파일 (신규)**: `physical_ai_server/physical_ai_server/inference/groot_inference_manager.py`

Action buffer 관리, background inference thread, chunk alignment을 담당.

```python
class GR00TInferenceManager:
    """GR00T action chunk 기반 비동기 inference manager."""

    BUFFER_REFILL_THRESHOLD = 6   # buffer < 이 값이면 새 chunk 요청
    ACTION_FREQ_HZ = 10.0         # joint command publish 주기 -- 코멘트: 이 부분도 모델에 이미 있을 수 도 있을 것 같은데 어떻게 생각해? 

    def __init__(self, node, joint_topic_types: dict, joint_order: dict):
        self._node = node
        self._joint_topic_types = joint_topic_types  # {name: msg_type}
        self._joint_order = joint_order               # {group: [joint_names]}

        # Action buffer (deque of 1D np arrays, each length = total DOF)
        self._action_buffer = collections.deque()
        self._buffer_lock = threading.Lock()

        # Zenoh service client for GR00T container
        self._groot_client = None  # ZenohGR00TClient instance

        # Background inference thread
        self._inference_thread = None
        self._running = False
        self._requesting = False  # 중복 요청 방지 flag

        # Chunk alignment
        self._last_action = None  # 이전 chunk의 마지막 action (L2 alignment용)

    def start(self, model_path, embodiment_tag, camera_topics,
              image_resize_hw, joint_state_topics, joint_names, task_instruction):
        """Setup GR00T inference: /groot/infer 호출 + buffer loop 시작."""
        self._groot_client = ZenohGR00TClient(node=self._node)
        self._groot_client.connect()

        # /groot/infer 서비스 호출 (setup only)
        response = self._groot_client.start_inference(
            model_path=model_path,
            embodiment_tag=embodiment_tag,
            image_topics=camera_topics,
            image_resize_hw=image_resize_hw,
            joint_state_topics=joint_state_topics,
            joint_names=joint_names,
            task_instruction=task_instruction
        )
        if not response.success:
            raise RuntimeError(f"GR00T infer setup failed: {response.message}")

        self._running = True
        # 첫 chunk 즉시 요청
        self._request_chunk_async()

    def pop_action(self) -> Optional[dict]:
        """10Hz timer에서 호출. buffer에서 1개 action pop → joint_msg_datas로 변환."""
        with self._buffer_lock:
            if not self._action_buffer:
                return None
            action = self._action_buffer.popleft()
            remaining = len(self._action_buffer)

        # Buffer가 threshold 이하이고 이미 요청 중이 아니면 새 chunk 요청
        if remaining < self.BUFFER_REFILL_THRESHOLD and not self._requesting:
            self._request_chunk_async()

        # action (1D np array) → joint_msg_datas dict로 변환
        return self._action_to_joint_msgs(action)

    def _request_chunk_async(self):
        """Background thread에서 /groot/get_action_chunk 호출."""
        self._requesting = True
        self._inference_thread = threading.Thread(target=self._fetch_chunk, daemon=True)
        self._inference_thread.start()

    def _fetch_chunk(self):
        """Blocking service call → buffer에 chunk 추가."""
        try:
            response = self._groot_client.get_action_chunk(
                task_instruction=self._task_instruction)
            if response.success:
                chunk = np.array(response.action_chunk).reshape(
                    response.chunk_size, response.action_dim)  # (T, D)
                self._align_and_enqueue(chunk)
        finally:
            self._requesting = False

    def _align_and_enqueue(self, chunk):
        """L2 distance로 chunk alignment 후 buffer에 추가."""
        with self._buffer_lock:
            if self._last_action is not None and len(chunk) > 1:
                # 새 chunk에서 이전 마지막 action과 가장 가까운 timestep 찾기
                distances = np.linalg.norm(chunk - self._last_action, axis=1)
                start_idx = np.argmin(distances) + 1  # 가장 가까운 다음부터
                if start_idx < len(chunk):
                    chunk = chunk[start_idx:]
            for action in chunk:
                self._action_buffer.append(action)
            if len(chunk) > 0:
                self._last_action = chunk[-1].copy()

    def _action_to_joint_msgs(self, action) -> dict:
        """Flat action array → per-group ROS2 messages."""
        joint_msg_datas = {}
        offset = 0
        for group_name, joint_names in self._joint_order.items():
            n_joints = len(joint_names)
            values = action[offset:offset + n_joints]
            offset += n_joints

            msg_type = self._joint_topic_types.get(group_name)
            if msg_type is None:
                continue

            # JointState 또는 Twist 메시지 생성
            if 'mobile' in group_name.lower():
                msg = Twist()
                msg.linear.x = float(values[0]) if len(values) > 0 else 0.0
                msg.linear.y = float(values[1]) if len(values) > 1 else 0.0
                msg.angular.z = float(values[2]) if len(values) > 2 else 0.0
            else:
                msg = JointState()
                msg.name = list(joint_names)
                msg.position = [float(v) for v in values]

            joint_msg_datas[group_name] = msg

        return joint_msg_datas

    def stop(self):
        """Inference 중지 및 정리."""
        self._running = False
        if self._groot_client:
            self._groot_client.stop_inference()
        with self._buffer_lock:
            self._action_buffer.clear()
        self._last_action = None
```

---

## 변경 5: ZenohGR00TClient (신규)

**파일 (신규)**: `physical_ai_server/physical_ai_server/communication/zenoh_groot_client.py`

기존 `ZenohLeRobotClient` 패턴을 따름 (ROS2 service client + rmw_zenoh).

```python
class ZenohGR00TClient:
    """GR00T 컨테이너와 Zenoh 기반 서비스 통신."""

    SERVICE_INFER = "/groot/infer"
    SERVICE_STOP = "/groot/stop"
    SERVICE_STATUS = "/groot/status"
    SERVICE_GET_ACTION_CHUNK = "/groot/get_action_chunk"

    def __init__(self, node):
        self._node = node
        self._callback_group = MutuallyExclusiveCallbackGroup()
        self._infer_client = None
        self._stop_client = None
        self._action_chunk_client = None

    def connect(self):
        self._infer_client = self._node.create_client(
            StartInference, self.SERVICE_INFER, callback_group=self._callback_group)
        self._stop_client = self._node.create_client(
            StopTraining, self.SERVICE_STOP, callback_group=self._callback_group)
        self._action_chunk_client = self._node.create_client(
            GetActionChunk, self.SERVICE_GET_ACTION_CHUNK, callback_group=self._callback_group)

    def start_inference(self, model_path, embodiment_tag, image_topics,
                        image_resize_hw, joint_state_topics, joint_names,
                        task_instruction) -> LeRobotResponse:
        request = StartInference.Request()
        request.model_path = model_path
        request.embodiment_tag = embodiment_tag
        request.image_topics = image_topics
        request.image_resize_hw = image_resize_hw
        request.joint_state_topics = joint_state_topics
        request.joint_names = joint_names
        request.task_instruction = task_instruction
        return self._call_service(self._infer_client, request, self.SERVICE_INFER)

    def get_action_chunk(self, task_instruction="") -> LeRobotResponse:
        request = GetActionChunk.Request()
        request.task_instruction = task_instruction
        return self._call_service(
            self._action_chunk_client, request, self.SERVICE_GET_ACTION_CHUNK,
            timeout_sec=5.0)  # inference는 100-500ms, 여유 있게 5초

    def stop_inference(self) -> LeRobotResponse:
        request = StopTraining.Request()  # 기존 stop service 재사용
        return self._call_service(self._stop_client, request, self.SERVICE_STOP)

    def _call_service(self, client, request, service_name, timeout_sec=10.0):
        """ZenohLeRobotClient._call_service와 동일한 패턴."""
        # client.wait_for_service() → call_async() → spin_until_future_complete()
        ...
```
--코멘트: 혹시 이거 zenoh sdk를 쓰는거 아니지? ros2+ rmw_zenoh를 쓰는거 아니지 ? 

---

## 변경 6: physical_ai_server.py 수정

**파일**: `physical_ai_server/physical_ai_server/physical_ai_server.py`

### 6-1. import 추가 (line 1-60)

```python
from physical_ai_server.inference.groot_inference_manager import GR00TInferenceManager
```

### 6-2. START_INFERENCE 핸들러 수정 (line 808-829)

```python
elif request.command == SendCommand.Request.START_INFERENCE:
    self.joint_topic_types = self.communicator.get_publisher_msg_types()
    self.operation_mode = 'inference'
    task_info = request.task_info

    # GR00TInferenceManager 생성
    self.groot_manager = GR00TInferenceManager(
        node=self,
        joint_topic_types=self.joint_topic_types,
        joint_order=self.joint_order  # from robot_config.yaml
    )

    # robot_config.yaml에서 topic 정보 추출
    camera_topics = self._get_camera_topics_for_inference()
    image_resize_hw = self._get_image_resize_hw()  # config에서 읽거나 default
    joint_state_topics = self._get_follower_joint_topics()
    joint_names = self._get_flat_joint_names()  # joint_order를 flat list로

    # GR00T setup (모델 로드 + subscriber 시작)
    self.groot_manager.start(
        model_path=task_info.policy_path,
        embodiment_tag='new_embodiment',
        camera_topics=camera_topics,
        image_resize_hw=image_resize_hw,
        joint_state_topics=joint_state_topics,
        joint_names=joint_names,
        task_instruction=task_info.task_instruction[0] if task_info.task_instruction else ""
    )

    self.on_inference = True
    self.timer_manager.start(timer_name='inference')
    response.success = True
    response.message = 'GR00T inference started'
```

### 6-3. _inference_timer_callback 재작성 (line 573-593)

```python
def _inference_timer_callback(self):
    """10Hz timer: action buffer에서 1개 pop → joint command publish."""
    if not self.on_inference or self.groot_manager is None:
        return

    joint_msg_datas = self.groot_manager.pop_action()
    if joint_msg_datas is not None:
        self.communicator.publish_action(joint_msg_datas)
    else:
        # Buffer 비어있음 - inference 지연 또는 아직 첫 chunk 대기 중
        pass

    # Status publish
    current_status = TaskStatus()
    current_status.phase = TaskStatus.RUNNING
    self.communicator.publish_status(status=current_status)
```

### 6-4. Helper 메서드 추가

```python
def _get_camera_topics_for_inference(self) -> list:
    """robot_config.yaml의 camera_topic_list에서 topic 경로만 추출."""
    return [entry.split(':')[1] for entry in self.camera_topic_list]

def _get_follower_joint_topics(self) -> list:
    """robot_config.yaml의 joint_topic_list에서 follower topic만 추출."""
    topics = []
    for entry in self.joint_topic_list:
        name, topic = entry.split(':')
        if 'follower' in name and 'mobile' not in name:
            topics.append(topic)
    return topics

def _get_flat_joint_names(self) -> list:
    """joint_order에서 follower 그룹의 joint name들을 flat list로."""
    names = []
    for group, joints in self.joint_order.items():
        if 'follower' in group and 'mobile' not in group:
            names.extend(joints)
    return names

def _get_image_resize_hw(self) -> list:
    """카메라별 resize 크기. config에 없으면 default [224, 224] per camera."""
    # robot_config.yaml에 inference_image_size 키가 있으면 사용, 없으면 기본값
    default_size = [224, 224]
    n_cameras = len(self.camera_topic_list)
    return default_size * n_cameras
```

### 6-5. STOP 핸들러에 GR00T cleanup 추가

기존 stop/finish 로직에서:
```python
if self.groot_manager:
    self.groot_manager.stop()
    self.groot_manager = None
```

---

## 변경 7: communication/__init__.py 업데이트

**파일**: `physical_ai_server/physical_ai_server/communication/__init__.py`
- `ZenohGR00TClient` export 추가

---

## 수정 대상 파일 요약

| 파일 | 변경 유형 | 내용 |
|------|----------|------|
| `physical_ai_interfaces/srv/GetActionChunk.srv` | **신규** | Action chunk 서비스 정의 |
| `physical_ai_interfaces/srv/StartInference.srv` | 수정 | multi-topic, resize, joint_names 필드 추가 |
| `physical_ai_interfaces/CMakeLists.txt` | 수정 | GetActionChunk.srv 등록 |
| `third_party/groot/executor.py` | 수정 | multi-topic 구독, get_action_chunk 핸들러, continuous loop 제거 |
| `physical_ai_server/.../inference/groot_inference_manager.py` | **신규** | Action buffer, background chunk 요청, L2 alignment |
| `physical_ai_server/.../communication/zenoh_groot_client.py` | **신규** | GR00T Zenoh 서비스 클라이언트 |
| `physical_ai_server/.../communication/__init__.py` | 수정 | export 추가 |
| `physical_ai_server/.../physical_ai_server.py` | 수정 | inference callback, START_INFERENCE 핸들러, helper 메서드 |

## 변경하지 않는 것

- `zenoh_lerobot_client.py`: LeRobot 컨테이너 전용, GR00T과 무관
- `zenoh_inference_manager.py`: LeRobot inference용, 별도 유지
- `inference_manager.py`: 로컬 LeRobot inference용, 별도 유지
- `communicator.py`: `publish_action()` 인터페이스 변경 없음 (이미 Dict[str, msg] 형식)
- Docker 설정: GR00T 컨테이너는 이미 `network_mode: host`로 Zenoh 접근 가능

---

## 검증 방법

1. **빌드 테스트**: `colcon build` 후 physical_ai_interfaces에 GetActionChunk.srv 정상 빌드 확인
2. **GR00T executor 단독 테스트**: executor를 실행하고 `/groot/infer` + `/groot/get_action_chunk` 서비스가 등록되는지 확인
3. **E2E 테스트**: physical_ai_manager UI에서 START_INFERENCE → 로봇 팔이 움직이는지 확인
4. **Timing 확인**: `get_action_chunk` 응답 시간 (100-500ms), buffer underrun 빈도 모니터링
5. **Joint merge 확인**: 4개 joint topic이 정확한 joint_order로 merge되는지 로그 확인


-- 코멘트: 근데 중요한건 이 구조가 Lerobot도 동일하게 사용되어야 한다는거야. 나는 Opensource Action model들을 통합하는게 가장 큰 목표거든. 근데 Lerobot, Gr00t에서 사용하는 데이터를 가져오고, 출력하는 부분에 대해서는 동일하게 가져갔으면 좋겠는거야.
그리고 모델을 로드하거나 하는 API나, 모델에 Action을 요청하는거나. 명령은 동일한거지.
하지만 모델마다 로드하는 방식, action을 얻는 함수들은 다르겠지만, 그거 외에는 모두 비슷할거라고 생각하긴 하거든?
그래서 확장을 염두에두고 만들면 좋겠어.

---

## 코멘트 답변 (코드 분석 기반, 2차 업데이트)

> 아래 답변은 실제 소스 코드를 분석한 결과입니다:
> - `ffw_sg2_config.py` — GR00T modality config
> - `ffw_sg2_rev1_config.yaml` — physical_ai_server robot config
> - `zenoh_lerobot_client.py` — 기존 Zenoh client 패턴
> - `executor.py` — 현재 GR00T executor 구조

---

### 답변 1: Observation dict key와 ffw_sg2_config.py 매핑 (데이터흐름 diagram 코멘트)

맞습니다. **핵심 문제**: GR00T policy가 기대하는 observation dict의 key는 ROS topic 이름이 아니라 `ffw_sg2_config.py`의 `modality_keys` 입니다.

**실제 ffw_sg2_config.py 분석:**
```python
ffw_sg2_config = {
    "video": ModalityConfig(
        delta_indices=[0],
        modality_keys=["cam_left_head", "cam_left_wrist", "cam_right_wrist"],  # ← cam_right_head 없음!
    ),
    "state": ModalityConfig(
        delta_indices=[0],
        modality_keys=["arm_left", "arm_right"],  # ← head, lift, mobile 없음!
    ),
    "action": ModalityConfig(
        delta_indices=list(range(0, 16)),  # action horizon = 16 steps
        modality_keys=["arm_left", "arm_right"],  # ← action도 arm_left, arm_right만
        action_configs=[
            ActionConfig(rep=ABSOLUTE, type=NON_EEF, format=DEFAULT),  # arm_left (8 dims)
            ActionConfig(rep=ABSOLUTE, type=NON_EEF, format=DEFAULT),  # arm_right (8 dims)
        ],
    ),
    "language": ModalityConfig(
        delta_indices=[0],
        modality_keys=["annotation.human.task_description"],
    ),
}
```

**실제 ffw_sg2_rev1_config.yaml 분석:**
```yaml
camera_topic_list:                                              # yaml name → modality key 관계
  - cam_left_head:/robot/camera/cam_left_head/...compressed     # cam_left_head → cam_left_head  ✅ 일치
  - cam_right_head:/robot/camera/cam_right_head/...compressed   # cam_right_head → (config에 없음) ❌ 구독 불필요
  - cam_left_wrist:/robot/camera/cam_left_wrist/...compressed   # cam_left_wrist → cam_left_wrist  ✅ 일치
  - cam_right_wrist:/robot/camera/cam_right_wrist/...compressed # cam_right_wrist → cam_right_wrist ✅ 일치

joint_topic_list:                                                 # yaml name → modality key 관계
  - follower_arm_left:/robot/arm_left_follower/joint_states       # follower_arm_left → arm_left  (strip "follower_")
  - follower_arm_right:/robot/arm_right_follower/joint_states     # follower_arm_right → arm_right (strip "follower_")
  - follower_head:/robot/head_follower/joint_states               # follower_head → (config에 없음) ❌ 구독 불필요
  - follower_lift:/robot/lift_follower/joint_states               # follower_lift → (config에 없음) ❌ 구독 불필요
  - follower_mobile:/odom                                         # follower_mobile → (config에 없음) ❌ 구독 불필요
```

**따라서 GR00T policy에 넘겨야 하는 observation dict:**
```python
observation = {
    "video": {
        "cam_left_head":  np.ndarray(1,1,H,W,C),   # ← /robot/camera/cam_left_head/image_raw/compressed
        "cam_left_wrist": np.ndarray(1,1,H,W,C),   # ← /robot/camera/cam_left_wrist/image_raw/compressed
        "cam_right_wrist": np.ndarray(1,1,H,W,C),  # ← /robot/camera/cam_right_wrist/image_raw/compressed
        # cam_right_head: 구독하지 않음 (modality config에 없음)
    },
    "state": {
        "arm_left":  np.ndarray(1,1,8),   # ← /robot/arm_left_follower/joint_states  (8 joints)
        "arm_right": np.ndarray(1,1,8),   # ← /robot/arm_right_follower/joint_states (8 joints)
        # head, lift, mobile: 구독하지 않음 (modality config에 없음)
    },
    "language": {
        "annotation.human.task_description": [["Pick up the object"]]
    }
}
```

**그리고 action output도 arm_left, arm_right만 포함:**
- action chunk shape: `(16, 16)` = 16 timesteps × (8 arm_left + 8 arm_right)
- physical_ai_server는 leader_arm_left, leader_arm_right에만 publish
- head, lift, mobile에는 action publish하지 않음

**설계 결정 — "topic_map" 방식 채택:**

physical_ai_server가 `name:topic` 형태의 매핑을 StartInference 서비스로 전달하고,
executor가 모델 로드 후 modality_config의 `modality_keys`와 대조하여 **필요한 topic만 자동 구독**.

```
# physical_ai_server가 전달하는 topic_map:
camera_topic_map = ["cam_left_head:/robot/camera/cam_left_head/image_raw/compressed",
                    "cam_right_head:/robot/camera/cam_right_head/image_raw/compressed",  # 보내도 됨, executor가 무시
                    "cam_left_wrist:/robot/camera/cam_left_wrist/image_raw/compressed",
                    "cam_right_wrist:/robot/camera/cam_right_wrist/image_raw/compressed"]

joint_topic_map = ["arm_left:/robot/arm_left_follower/joint_states",
                   "arm_right:/robot/arm_right_follower/joint_states",
                   "head:/robot/head_follower/joint_states",       # 보내도 됨, executor가 무시
                   "lift:/robot/lift_follower/joint_states"]       # 보내도 됨, executor가 무시

# executor 내부 로직:
loaded_modality = load_modality_config(model_path)
video_keys = loaded_modality["video"].modality_keys  # ["cam_left_head", "cam_left_wrist", "cam_right_wrist"]
state_keys = loaded_modality["state"].modality_keys  # ["arm_left", "arm_right"]

# 매칭: topic_map에서 key가 modality_keys에 있는 것만 구독
for name, topic in camera_topic_map:
    if name in video_keys:
        subscribe(topic, callback_with_key=name)  # ← 이 name이 observation dict의 key가 됨
```

이 방식의 장점:
1. `ffw_sg2_rev1_config.yaml`의 `name:topic` 형식을 **그대로 활용** (이미 있는 구조)
2. joint_topic_list에서 `follower_` prefix만 strip하면 modality key와 일치
3. physical_ai_server는 모델 내부를 몰라도 됨 — 가용한 전체 topic을 보내면 됨
4. executor가 모델의 modality_config를 source of truth로 사용하여 자동 필터링

---

### 답변 2: Image resize는 모델에서 처리 (StartInference.srv, InferenceConfig 코멘트)

동의합니다. GR00T 내부 확인 결과:
- **Eagle3 VL Image Processor**: 기본 448x448 resize
- **Gr00tN1d6Processor**: `image_target_size`, `image_crop_size`, `shortest_image_edge=512` 등 자체 이미지 변환 파이프라인 보유
- `LetterBoxTransform` → `Resize` → `CenterCrop(eval시)` → `Resize` 순서로 처리

**결론:** `image_resize_hw`를 **모든 곳에서 제거**합니다:
- ~~StartInference.srv의 `int32[] image_resize_hw`~~ → 삭제
- ~~InferenceConfig의 `image_resize_hw`~~ → 삭제
- ~~`_setup_ros2_subscribers`의 resize 파라미터~~ → 삭제
- ~~`_on_image_received`의 target_h/target_w~~ → 삭제
- ~~physical_ai_server의 `_get_image_resize_hw()` helper~~ → 삭제

GR00T policy가 `get_action()` 호출 시 자체 processor로 이미지를 변환하므로, executor는 원본 이미지를 그대로 저장하고 policy에 넘기면 됩니다.

다만 메모리 효율을 위해, 원본이 1920x1080 같은 고해상도일 경우 executor 내부에서 적당히 (예: 640x480) pre-resize하는 것은 선택적으로 남겨둘 수 있습니다. 이건 모델 파라미터가 아니라 executor 내부 최적화 사항.

---

### 답변 3: ACTION_FREQ_HZ를 모델에서 가져올 수 있는지 (GR00TInferenceManager 코멘트)

GR00T modality config를 확인한 결과:
- `delta_indices=list(range(0, 16))` → **action horizon = 16 steps** (chunk 크기) — 모델에서 알 수 있음
- 하지만 **Hz 정보는 modality config에 없습니다**

Action frequency는 학습 데이터의 수집 주기에 따라 결정됩니다:
- 데이터가 10Hz로 수집되었다면 → 10Hz로 replay
- 데이터가 30Hz로 수집되었다면 → 30Hz로 replay

**제안:**
- `ACTION_FREQ_HZ`는 model config에서 자동으로 가져올 수 없으므로, robot_config.yaml에 `inference_freq: 10.0` 같은 항목 추가
- 또는 기본값(10Hz)을 사용하되, StartInference 시 override 가능하게
- `action_horizon`(chunk_size=16)은 모델 로드 후 `modality_config["action"].delta_indices`에서 자동으로 알 수 있음
- **현재 우리 FFW 로봇은 10Hz로 데이터 수집하므로 기본값 10Hz가 적절**

---

### 답변 4: ZenohGR00TClient는 ROS2+rmw_zenoh (ZenohGR00TClient 코멘트)

네, **ROS2 + rmw_zenoh**를 사용합니다. zenoh_ros2_sdk가 아닙니다.

실제 `zenoh_lerobot_client.py` 코드를 확인하면:
```python
# physical_ai_server 쪽 (ZenohLeRobotClient) — 표준 ROS2 API 사용
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from physical_ai_interfaces.srv import StartInference, StopTraining, ...

self._infer_client = self._node.create_client(
    StartInference,                           # 표준 ROS2 service client
    self.SERVICE_INFER,
    callback_group=self._callback_group
)

# service 호출도 표준 ROS2 패턴
future = client.call_async(request)
rclpy.spin_until_future_complete(self._node, future, timeout_sec=self.timeout_sec)
```

ZenohGR00TClient도 이와 **완전히 동일한 패턴**입니다:
- `physical_ai_server` 쪽 (ZenohGR00TClient): **표준 ROS2 service client** (`self._node.create_client(...)`)
  - rmw_zenoh 미들웨어가 ROS2 → Zenoh 프로토콜 변환 자동 수행
- `groot container` 쪽 (executor.py): **zenoh_ros2_sdk** (`ROS2ServiceServer`, `ROS2Subscriber`)
  - ROS2 설치 없이 Zenoh 네이티브로 동작, CDR 인코딩으로 rmw_zenoh와 호환

```
physical_ai_server (ROS2 + rmw_zenoh) ←→ Zenoh transport ←→ groot_container (zenoh_ros2_sdk)
physical_ai_server (ROS2 + rmw_zenoh) ←→ Zenoh transport ←→ lerobot_container (zenoh_ros2_sdk)
```

---

### 답변 5: LeRobot 통합 및 확장성 (최종 코멘트)

완전히 동의합니다. 이것이 가장 중요한 설계 원칙이 되어야 합니다.

**현재 코드 분석 결과 공통화할 수 있는 부분:**

| 구성요소 | GR00T | LeRobot | 공통화 가능? |
|---------|-------|---------|------------|
| 서비스 프로토콜 (.srv) | StartInference, GetActionChunk, StopTraining | StartInference, StopTraining | **동일한 .srv 사용** |
| Container 내 서비스 핸들링 | executor.py (_handle_infer, _handle_get_action_chunk) | executor.py (동일 패턴) | 서비스 이름만 다름 |
| Topic 구독 (observation) | zenoh_ros2_sdk ROS2Subscriber | zenoh_ros2_sdk ROS2Subscriber | **동일** |
| 모델 로드 | Gr00tPolicy(...) | LeRobotPolicy.from_pretrained(...) | 모델별 구현 |
| Inference (get_action) | policy.get_action(observation) | policy.select_action(observation) | 모델별 함수명 |
| Action buffer | physical_ai_server 쪽 deque | physical_ai_server 쪽 deque | **완전 동일** |
| Chunk alignment (L2) | _align_and_enqueue | _align_and_enqueue | **완전 동일** |
| Action → JointState 변환 | _action_to_joint_msgs | _action_to_joint_msgs | **완전 동일** |
| Zenoh client (ROS2 쪽) | ZenohGR00TClient | ZenohLeRobotClient | 패턴 동일, 서비스 이름만 다름 |

**공통 추상화 레이어 설계:**

#### A. Container 측 (Executor): 공통 서비스 인터페이스

서비스 이름을 모델별로 다르게 하되 (`/groot/*`, `/lerobot/*`), .srv 타입은 동일하게:
```
/<model>/infer              → 모델 로드 + 토픽 구독 시작 (setup)
/<model>/get_action_chunk   → 현재 observation으로 추론, action chunk 반환
/<model>/stop               → 추론 중지
/<model>/status             → 상태 확인
```

각 executor는 동일한 패턴으로 구현하되, 모델별 차이(load, get_action)만 override:
```python
# GR00T executor
def _load_policy(self, model_path, embodiment_tag):
    from gr00t.policy.gr00t_policy import Gr00tPolicy
    return Gr00tPolicy(embodiment_tag=emb_tag, model_path=model_path, device=device)

def _run_inference(self, policy, observation):
    action, info = policy.get_action(observation)
    return action

# LeRobot executor (미래)
def _load_policy(self, model_path, embodiment_tag):
    from lerobot.common.policies import get_policy_class
    return get_policy_class(policy_type).from_pretrained(model_path)

def _run_inference(self, policy, observation):
    return policy.select_action(observation)
```

#### B. physical_ai_server 측: 공통 InferenceManager

```python
class BaseActionChunkManager(ABC):
    """모든 action model에 공통인 action buffer + chunk 관리."""

    # 공통 로직 (base class에 구현):
    # - Action buffer (deque)
    # - pop_action() → joint_msg_datas 변환
    # - _request_chunk_async() → background thread
    # - _align_and_enqueue() → L2 chunk alignment
    # - _action_to_joint_msgs() → flat action → per-group ROS2 messages
    # - start() / stop() lifecycle

    @abstractmethod
    def _create_client(self) -> BaseModelClient:
        """모델별 Zenoh client 생성 (GR00T / LeRobot / ...)"""
        pass

class GR00TActionChunkManager(BaseActionChunkManager):
    def _create_client(self):
        return ZenohGR00TClient(node=self._node)

class LeRobotActionChunkManager(BaseActionChunkManager):
    def _create_client(self):
        return ZenohLeRobotClient(node=self._node)  # 기존 client 확장
```

#### C. Container Client: 공통 인터페이스

```python
class BaseModelClient(ABC):
    @abstractmethod
    def connect(self) -> bool: pass
    @abstractmethod
    def start_inference(self, model_path, camera_topic_map, joint_topic_map,
                        task_instruction, **kwargs) -> Response: pass
    @abstractmethod
    def get_action_chunk(self, task_instruction="") -> Response: pass
    @abstractmethod
    def stop_inference(self) -> Response: pass
    @abstractmethod
    def disconnect(self): pass
```

이렇게 하면:
1. **Action buffer, chunk alignment, joint publishing** → 완전히 공통 (base class)
2. **모델 로드, observation 전처리, inference 실행** → 모델별 구현 (executor 내부)
3. **서비스 프로토콜** → 동일한 .srv 파일 사용 (GetActionChunk.srv, StartInference.srv)
4. 새 모델 추가 시: executor만 새로 구현하면 나머지는 재사용
5. physical_ai_server는 모델 종류를 몰라도 됨 — policy_path로 어떤 모델인지 판별 후 적절한 manager 생성

**초기 구현 전략:**
- 이번 PR에서는 GR00T용으로 먼저 구현하되, base class 추출 가능한 구조로 작성
- 추후 LeRobot 통합 시 base class로 리팩토링
- 이유: 현재 LeRobot executor가 action chunk 방식이 아니므로, 실제 두 개를 만들어봐야 공통 인터페이스가 명확해짐

---

## 수정된 설계 (코멘트 반영)

> 위 코멘트 답변들을 반영하여, 원래 플랜의 변경 사항들을 수정합니다.
> 아래는 **원래 플랜과 달라진 부분**만 기술합니다.

### 수정 2' (변경 2 대체): StartInference.srv 확장

**변경 전 (원래 플랜):**
```
string model_path
string embodiment_tag
string[] image_topics
int32[] image_resize_hw        # ← 삭제
string[] joint_state_topics
string[] joint_names
string task_instruction
```

**변경 후 (코멘트 반영):**
```
string model_path
string embodiment_tag
string[] camera_topic_map      # ["cam_left_head:/robot/camera/cam_left_head/image_raw/compressed", ...]
string[] joint_topic_map       # ["arm_left:/robot/arm_left_follower/joint_states", ...]
string task_instruction
---
bool success
string message
```

주요 변경:
- `image_resize_hw` **삭제** (모델 내부 processor가 처리)
- `image_topics` → `camera_topic_map` (name:topic 쌍, executor가 modality_keys와 매칭)
- `joint_state_topics` + `joint_names` → `joint_topic_map` (name:topic 쌍으로 통합)
- executor가 모델 로드 후 modality_config에서 필요한 key만 필터링하여 구독

### 수정 3-1' (변경 3-1 대체): InferenceConfig

```python
@dataclass
class InferenceConfig:
    model_path: str = ""
    embodiment_tag: str = "new_embodiment"
    camera_topic_map: dict = field(default_factory=dict)   # {modality_key: topic_path}
    joint_topic_map: dict = field(default_factory=dict)    # {modality_key: topic_path}
    task_instruction: str = ""
    # image_resize_hw 삭제
    # inference_freq 삭제 (executor는 주기 불필요, on-demand 방식)
    # joint_names 삭제 (joint_topic_map에 통합)
```

### 수정 3-3' (변경 3-3 대체): _handle_infer 수정

```python
def _handle_infer(self, request):
    # 1. 모델 로드
    model_path = request.model_path
    embodiment_tag = request.embodiment_tag or "new_embodiment"
    self._loaded_policy = self._load_policy(model_path, embodiment_tag)

    # 2. 모델의 modality_config 읽기
    modality_config = self._get_modality_config()  # 모델에서 자동 추출
    video_keys = modality_config["video"].modality_keys   # ["cam_left_head", "cam_left_wrist", "cam_right_wrist"]
    state_keys = modality_config["state"].modality_keys   # ["arm_left", "arm_right"]
    action_keys = modality_config["action"].modality_keys  # ["arm_left", "arm_right"]

    # 3. request의 topic_map을 파싱하고, modality_keys로 필터링
    camera_topic_map = self._parse_topic_map(request.camera_topic_map)  # {"cam_left_head": "/robot/...", ...}
    joint_topic_map = self._parse_topic_map(request.joint_topic_map)    # {"arm_left": "/robot/...", ...}

    # 필요한 것만 필터
    active_cameras = {k: v for k, v in camera_topic_map.items() if k in video_keys}
    active_joints = {k: v for k, v in joint_topic_map.items() if k in state_keys}

    # 4. 필터된 topic만 구독
    self._setup_ros2_subscribers(active_cameras, active_joints)

    # 5. observation dict 초기화 (modality key 기반)
    self._latest_observations = {
        "video": {key: None for key in active_cameras},
        "state": {key: None for key in active_joints},
        "language": {},
        "timestamp": None,
    }

    # 6. state 전환 (continuous loop 시작하지 않음)
    self._inference_running = True
    self.state = ExecutorState.INFERENCE

    # 7. action_keys 저장 (응답 시 action chunk → modality key 매핑에 사용)
    self._action_keys = action_keys

    return self._create_response(self._infer_service, success=True, message="GR00T inference started")
```

### 수정 3-4' (변경 3-4 대체): _setup_ros2_subscribers (modality key 기반)

```python
def _setup_ros2_subscribers(self, active_cameras: dict, active_joints: dict):
    """modality key → topic 매핑 기반으로 필요한 topic만 구독.

    Args:
        active_cameras: {modality_key: topic_path}  e.g. {"cam_left_head": "/robot/camera/cam_left_head/..."}
        active_joints:  {modality_key: topic_path}  e.g. {"arm_left": "/robot/arm_left_follower/joint_states"}
    """
    # 카메라 구독 — key가 observation["video"]의 dict key가 됨
    for modality_key, topic_path in active_cameras.items():
        def make_callback(key):
            def callback(msg):
                self._on_image_received(key, msg)
            return callback

        sub = ROS2Subscriber(
            topic=topic_path,
            msg_type="sensor_msgs/msg/CompressedImage",
            callback=make_callback(modality_key)
        )
        self._ros2_subscribers.append(sub)
        logger.info(f"Camera subscribed: {modality_key} → {topic_path}")

    # Joint 구독 — key가 observation["state"]의 dict key가 됨
    for modality_key, topic_path in active_joints.items():
        def make_callback(key):
            def callback(msg):
                self._on_joint_state_received(key, msg)
            return callback

        sub = ROS2Subscriber(
            topic=topic_path,
            msg_type="sensor_msgs/msg/JointState",
            callback=make_callback(modality_key)
        )
        self._ros2_subscribers.append(sub)
        logger.info(f"Joint subscribed: {modality_key} → {topic_path}")
```

### 수정 3-5' (변경 3-5 대체): _on_image_received (resize 제거)

```python
def _on_image_received(self, modality_key: str, msg):
    """카메라 이미지를 modality key 기반으로 저장. Resize는 모델이 처리."""
    image_data = np.frombuffer(bytes(msg.data), dtype=np.uint8)
    image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
    if image is not None:
        # resize 하지 않음 — GR00T policy 내부 processor가 알아서 처리
        image = image[np.newaxis, np.newaxis, ...]  # (1,1,H,W,C)
        self._latest_observations["video"][modality_key] = image
        self._latest_observations["timestamp"] = time.time()
```

### 수정 3-6' (변경 3-6 대체): _on_joint_state_received (per-key 저장)

기존 `_on_multi_joint_state_received`는 merged_state 배열 기반이었지만,
modality key별로 **각각 독립적으로 (1,1,D) 저장**하는 것이 GR00T observation 형식에 맞음:

```python
def _on_joint_state_received(self, modality_key: str, msg):
    """Joint state를 modality key별로 독립 저장.

    각 key는 (1,1,D) numpy array로 저장되어 그대로 policy에 전달됨.
    e.g. observation["state"]["arm_left"] = np.array(1,1,8)
    """
    positions = np.array(msg.position, dtype=np.float32)
    self._latest_observations["state"][modality_key] = positions[np.newaxis, np.newaxis, :]
    self._latest_observations["timestamp"] = time.time()
```

### 수정 3-7' (변경 3-7 대체): _handle_get_action_chunk (action key 기반)

```python
def _handle_get_action_chunk(self, request):
    """Handle get_action_chunk service request."""
    if self.state != ExecutorState.INFERENCE or self._loaded_policy is None:
        return self._create_response(...)

    obs = self._latest_observations
    if obs["timestamp"] is None or time.time() - obs["timestamp"] > 2.0:
        return self._create_response(..., message="No recent observations")

    # task instruction
    task = getattr(request, "task_instruction", "") or self._inference_config.task_instruction
    if task:
        obs["language"]["annotation.human.task_description"] = [[task]]

    # observation dict 그대로 전달 — key가 이미 modality key
    observation = {
        "video": obs["video"],
        "state": obs["state"],
        "language": obs["language"]
    }
    action, info = self._loaded_policy.get_action(observation)

    # action: {"arm_left": (1,16,8), "arm_right": (1,16,8)} 형태
    # → concat하여 flat chunk로 반환: (16, 16) → flatten
    chunks = []
    for key in self._action_keys:  # ["arm_left", "arm_right"] 순서 보장
        if key in action:
            chunks.append(action[key][0])  # (T, D_per_key)
    if chunks:
        chunk = np.concatenate(chunks, axis=1)  # (T, D_total)
        T, D = chunk.shape
        return self._create_action_chunk_response(
            success=True,
            chunk=chunk.flatten().tolist(),
            chunk_size=T,
            action_dim=D
        )
    return self._create_response(..., message="No action output")
```

### 수정 4' (변경 4 대체): GR00TInferenceManager

주요 변경: `_action_to_joint_msgs`에서 modality key → leader topic 매핑 필요.

```python
class GR00TInferenceManager:
    def __init__(self, node, joint_topic_types: dict, joint_order: dict,
                 action_joint_map: dict):
        """
        Args:
            action_joint_map: modality key → leader group name 매핑
                e.g. {"arm_left": "leader_arm_left", "arm_right": "leader_arm_right"}
        """
        self._action_joint_map = action_joint_map
        # ... 나머지 동일

    def _action_to_joint_msgs(self, action) -> dict:
        """Flat action array → per-group ROS2 messages.

        action은 (D_total,) 1D array이고, action_keys 순서로 concat됨.
        e.g. action = [arm_l_j1..j7, grip_l, arm_r_j1..j7, grip_r]  (16 dims)

        action_joint_map으로 어떤 leader topic에 publish할지 결정:
        - "arm_left" → leader_arm_left topic
        - "arm_right" → leader_arm_right topic
        """
        joint_msg_datas = {}
        offset = 0
        for modality_key, leader_group in self._action_joint_map.items():
            joint_names = self._joint_order.get(leader_group, [])
            n_joints = len(joint_names)
            values = action[offset:offset + n_joints]
            offset += n_joints

            msg = JointState()
            msg.name = list(joint_names)
            msg.position = [float(v) for v in values]
            joint_msg_datas[leader_group] = msg

        return joint_msg_datas
```

### 수정 6' (변경 6 대체): physical_ai_server.py helper 메서드

```python
def _get_camera_topic_map(self) -> list:
    """robot_config.yaml의 camera_topic_list에서 'name:topic' 형태 리스트 반환.

    yaml: cam_left_head:/robot/camera/cam_left_head/image_raw/compressed
    → "cam_left_head:/robot/camera/cam_left_head/image_raw/compressed"

    executor가 modality_config와 매칭하여 필요한 것만 구독.
    """
    return list(self.params['camera_topic_list'])  # 이미 "name:topic" 형식

def _get_joint_topic_map(self) -> list:
    """robot_config.yaml의 joint_topic_list에서 follower topic의 'modality_key:topic' 형태 리스트 반환.

    yaml: follower_arm_left:/robot/arm_left_follower/joint_states
    → "arm_left:/robot/arm_left_follower/joint_states"  (strip "follower_" prefix)
    """
    result = []
    for entry in self.params['joint_topic_list']:
        name, topic = entry.split(':', 1)
        if 'follower' in name and 'mobile' not in name:
            # "follower_arm_left" → "arm_left"
            modality_key = name.replace('follower_', '')
            result.append(f"{modality_key}:{topic}")
    return result

def _get_action_joint_map(self) -> dict:
    """action modality key → leader group 매핑.

    modality config의 action_keys (e.g. ["arm_left", "arm_right"])와
    robot_config의 leader 그룹 (e.g. "leader_arm_left", "leader_arm_right")을 연결.
    """
    action_map = {}
    for group_name in self.joint_order:
        if 'leader' in group_name and 'mobile' not in group_name:
            # "leader_arm_left" → modality_key "arm_left"
            modality_key = group_name.replace('leader_', '')
            action_map[modality_key] = group_name
    return action_map
```

---

## 수정된 전체 데이터 흐름 (코멘트 반영)

```
Robot Topics (Zenoh)                         ffw_sg2_config.py (modality config)
  │                                          video.modality_keys = ["cam_left_head", "cam_left_wrist", "cam_right_wrist"]
  │                                          state.modality_keys = ["arm_left", "arm_right"]
  │                                          action.modality_keys = ["arm_left", "arm_right"]
  │
  │  physical_ai_server                      GR00T Container (executor.py)
  │  ┌────────────────────┐                  ┌──────────────────────────────────────┐
  │  │ START_INFERENCE:    │                  │                                      │
  │  │ camera_topic_map =  │ /groot/infer     │ 1. 모델 로드 → modality_config 읽기  │
  │  │  [cam_left_head:...,│───────────────>  │ 2. topic_map ∩ modality_keys 매칭    │
  │  │   cam_right_head:..,│                  │    → cam_right_head는 구독 안함!     │
  │  │   cam_left_wrist:., │                  │    → head/lift/mobile 구독 안함!     │
  │  │   cam_right_wrist:.]│                  │ 3. 필요한 topic만 Zenoh 구독:        │
  │  │ joint_topic_map =   │                  │    - cam_left_head → obs["video"]["cam_left_head"]
  │  │  [arm_left:...,     │                  │    - cam_left_wrist → obs["video"]["cam_left_wrist"]
  │  │   arm_right:...,    │                  │    - cam_right_wrist → obs["video"]["cam_right_wrist"]
  │  │   head:...,         │                  │    - arm_left → obs["state"]["arm_left"]
  │  │   lift:...]         │                  │    - arm_right → obs["state"]["arm_right"]
  │  └────────────────────┘                  │                                      │
  │                                          │ 4. get_action_chunk 서비스 대기      │
  │  ┌────────────────────┐                  │                                      │
  │  │ 10Hz Timer:         │ get_action_chunk │ 5. policy.get_action(observation)    │
  │  │ buffer < 6 →────────│───────────────>  │    → action: {"arm_left": (1,16,8),  │
  │  │                     │                  │              "arm_right": (1,16,8)}  │
  │  │ ┌──────────────┐   │  (16,16) chunk   │    → concat → (16,16) flatten 반환   │
  │  │ │Action Buffer │<───│<─────────────── │                                      │
  │  │ │ pop 1 action │   │                  └──────────────────────────────────────┘
  │  │ │              │   │
  │  │ └──────┬───────┘   │
  │  │        │            │
  │  │   action_to_joint   │   action_joint_map:
  │  │   _msgs()           │   "arm_left" → leader_arm_left
  │  │        │            │   "arm_right" → leader_arm_right
  │  │        v            │
  │  └────────────────────┘
  │       │           │
  │       v           v
  │  /robot/arm_left_leader/joint_states    (8 joints: arm_l_j1-7, gripper_l)
  │  /robot/arm_right_leader/joint_states   (8 joints: arm_r_j1-7, gripper_r)
  │  (head, lift, mobile에는 publish하지 않음 — action config에 없으므로)
```

---

## 수정된 수정 대상 파일 요약 (코멘트 반영)

| 파일 | 변경 유형 | 내용 | 코멘트 반영 변경 |
|------|----------|------|----------------|
| `physical_ai_interfaces/srv/GetActionChunk.srv` | **신규** | Action chunk 서비스 정의 | 변경 없음 |
| `physical_ai_interfaces/srv/StartInference.srv` | 수정 | ~~image_resize_hw~~, camera_topic_map, joint_topic_map | image_resize_hw 삭제, topic_map 방식으로 변경 |
| `physical_ai_interfaces/CMakeLists.txt` | 수정 | GetActionChunk.srv 등록 | 변경 없음 |
| `third_party/groot/executor.py` | 수정 | modality key 기반 구독, get_action_chunk, loop 제거 | per-key observation, modality_config 자동 읽기 |
| `physical_ai_server/.../inference/groot_inference_manager.py` | **신규** | Action buffer, background chunk 요청, L2 alignment | action_joint_map 기반 publish |
| `physical_ai_server/.../communication/zenoh_groot_client.py` | **신규** | GR00T ROS2+rmw_zenoh 서비스 클라이언트 | 확인: zenoh_sdk 아님 |
| `physical_ai_server/.../communication/__init__.py` | 수정 | export 추가 | 변경 없음 |
| `physical_ai_server/.../physical_ai_server.py` | 수정 | inference callback, helper 메서드 | topic_map helper, action_joint_map helper 추가 |

---

## 남은 결정 사항

1. **ffw_sg2_config.py의 위치**: 현재 `Isaac-GR00T/examples/ffw_sg2/`에 있는데, executor가 모델 로드 시 자동으로 이 config를 찾을 수 있는지? `register_modality_config()` 호출이 executor 시작 전에 되어야 함.
   - 방안 A: executor.py 시작 시 config 파일 경로를 환경변수로 전달
   - 방안 B: model_path 안에 config 파일을 함께 저장 (finetune 결과에 포함)
   - 방안 C: StartInference 시 config_path 파라미터 추가

2. **ACTION_FREQ_HZ**: robot_config.yaml에 `inference_freq` 필드 추가할지, 기본값 10Hz로 고정할지

3. **mobile base action**: 현재 ffw_sg2_config에 mobile이 없지만, 향후 추가될 경우 Twist 메시지 변환 로직이 필요