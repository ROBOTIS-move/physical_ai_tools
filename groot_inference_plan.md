# Zenoh-based GR00T Inference Architecture Implementation Plan

## Context

Currently `_inference_timer_callback()` is disabled ("rosbag2-only mode"), the GR00T executor only supports a single joint topic, and runs a continuous inference loop (30Hz) structure.

**Problems:**
1. physical_ai_server proxies data -> unnecessary latency
2. GR00T can directly receive topics via Zenoh but this is not utilized
3. Continuous loop does not fit with action chunk-based asynchronous inference
4. Multi-joint topics of the FFW robot (arm_left, arm_right, head, lift, mobile) are not supported

**New Design:**
- GR00T container directly subscribes to robot topics via Zenoh (image + joint state)
- physical_ai_server requests action chunks through the `/groot/get_action_chunk` service
- Pops 1 action at 10Hz from the action buffer and publishes joint commands
- When the buffer drops below a threshold, a background thread requests the next chunk

---

## Overall Data Flow

```
Robot Topics (Zenoh)
  ├─ /robot/camera/*/compressed ──────────┐
  ├─ /robot/arm_left_follower/joint_states ┤
  ├─ /robot/arm_right_follower/joint_states┤
  ├─ /robot/head_follower/joint_states ────┤
  ├─ /robot/lift_follower/joint_states ────┘
  │                                     GR00T Container
  │                              ┌─────────────────────────┐
  │                              │ Directly receive topics  │
  │                              │ via Zenoh subscriber     │
  │                              │                         │
  │  /groot/infer (setup) ──────>│ Load model + start subs │
  │                              │                         │
  │  /groot/get_action_chunk ───>│ Run inference with      │  --Comment: When converting to observation here, I think we also need to consider the robot config part registered in gr00t. Currently we have our robot config at /home/hc/gr00t_ws/Isaac-GR00T/examples/ffw_sg2/ffw_sg2_config.py. But this config needs names in a different format than ROS topics. Ultimately the observation is a dictionary, and the keys for the data need to be the elements from ffw_sg2_config, while the values need to be the values from the topics. You know what I mean.
  │                              │ current observation      │
  │                              │ → Return (T,D) action   │
  │                              │   chunk                 │
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

## Change 1: Add GetActionChunk.srv

**File (new)**: `physical_ai_interfaces/srv/GetActionChunk.srv`

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

**File (modified)**: `physical_ai_interfaces/CMakeLists.txt`
- Add `"srv/GetActionChunk.srv"` entry (around line 41)

---

## Change 2: Extend StartInference.srv

**File**: `physical_ai_interfaces/srv/StartInference.srv`

Current:
```
string model_path
string[] image_topics
string joint_state_topic
---
bool success
string message
```

Changed:
```
string model_path
string embodiment_tag
string[] image_topics
int32[] image_resize_hw        # [H1, W1, H2, W2, ...] per-camera resize dimensions  --> But thinking about it, the camera resize dimensions could probably be found from the model input size or model config-related files. So it might not be necessary to send this resize information.
string[] joint_state_topics    # multi-topic support (singular -> plural)
string[] joint_names           # full joint_order (flat list)
string task_instruction        # for language-conditioned policy
---
bool success
string message
```

---

## Change 3: GR00T Executor Refactoring

**File**: `third_party/groot/executor.py`

### 3-1. Extend InferenceConfig (line 110-117)

```python
@dataclass
class InferenceConfig:
    model_path: str = ""
    embodiment_tag: str = "new_embodiment"
    inference_freq: float = 10.0      # Changed: 30→10 (action chunk-based)
    camera_topics: list = field(default_factory=list)
    joint_topics: list = field(default_factory=list)   # Changed: joint_topic (singular) → joint_topics (plural)
    joint_names: list = field(default_factory=list)     # Added: joint_order flat list
    image_resize_hw: list = field(default_factory=list) # Added: per-camera resize [H,W,...]  --Comment: Same here, resize should be retrieved from the model.
    task_instruction: str = ""                          # Added
```

### 3-2. Add get_action_chunk_service to ExecutorConfig (line 120-142)

```python
get_action_chunk_service: str = "/groot/get_action_chunk"
```

### 3-3. Modify _handle_infer (line 747-829)

Changes:
- Handle `joint_topic` (singular) → `joint_topics` (plural)
- Parse `image_resize_hw` to store per-camera resize dimensions
- Parse `joint_names` to store multi-topic merge order
- **Do not start a continuous inference loop** (remove thread creation)
- Only perform model loading + subscriber setup
- Transition state to INFERENCE to be ready to receive get_action_chunk requests
-- Comment: We need to use the topics from /home/hc/physical_ai_tools/physical_ai_server/config/ffw_sg2_rev1_config.yaml. Especially for joints, there are parts split across multiple topics, so those need to properly go into the observation section.

```python
# Before change: start inference_thread
self._inference_thread = threading.Thread(target=self._inference_loop, ...)
self._inference_thread.start()

# After change: only perform setup, do not start loop
self._inference_running = True
self.state = ExecutorState.INFERENCE
# _inference_loop removed, on-demand calls from get_action_chunk service
```

### 3-4. Modify _setup_ros2_subscribers (line 864-913)

- Single joint_topic → multi-topic subscription
- Each topic callback stores values at the correct index based on joint_names
- Maintain `_latest_observations["state"]["joint_positions"]` as a (1,1,D) array merged in joint_names order

```python
def _setup_ros2_subscribers(self, camera_topics, joint_topics, joint_names, image_resize_hw):
    # Camera subscription (same as before but with resize info)
    for i, cam_config in enumerate(camera_topics):
        topic = cam_config.get("topic") if isinstance(cam_config, dict) else cam_config
        name = cam_config.get("name", topic.split("/")[-2]) if isinstance(cam_config, dict) else topic.split("/")[-2]
        # resize dimensions: image_resize_hw[i*2], image_resize_hw[i*2+1]
        h = image_resize_hw[i*2] if i*2 < len(image_resize_hw) else 0
        w = image_resize_hw[i*2+1] if i*2+1 < len(image_resize_hw) else 0
        sub = ROS2Subscriber(topic=topic, msg_type="sensor_msgs/msg/CompressedImage",
                             callback=make_image_callback(name, h, w))
        self._ros2_subscribers.append(sub)

    # multi-joint subscription
    # joint_names_per_topic: mapping of which joint_names come from each topic
    self._merged_state = np.zeros(len(joint_names), dtype=np.float32)
    for joint_topic in joint_topics:
        sub = ROS2Subscriber(topic=joint_topic, msg_type="sensor_msgs/msg/JointState",
                             callback=make_joint_callback(joint_topic))
        self._ros2_subscribers.append(sub)
```

### 3-5. Add resize to _on_image_received (line 915-930)

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

### 3-6. Modify _on_multi_joint_state_received (multi-topic merge)

```python
def _on_multi_joint_state_received(self, topic_name, msg):
    """Merge multi-topic joint state in joint_names order."""
    positions = list(msg.position)
    names = list(msg.name)  # Using the JointState.name field
    for i, name in enumerate(names):
        if name in self._joint_name_to_index:
            idx = self._joint_name_to_index[name]
            self._merged_state[idx] = positions[i]
    # Save merged state as (1,1,D)
    self._latest_observations["state"]["joint_positions"] = \
        self._merged_state[np.newaxis, np.newaxis, :].copy()
    self._latest_observations["timestamp"] = time.time()
```

### 3-7. Add _handle_get_action_chunk (new service handler)

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

        # action shape: {key: (B, T, D)} - return entire chunk
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

### 3-8. Disable _inference_loop

- Remove or leave the existing continuous loop code as dead code
- Since `_handle_infer` does not start the thread, it will not be called

### 3-9. Register get_action_chunk service in start()

```python
self._get_action_chunk_service = ROS2ServiceServer(
    service_name=self.config.get_action_chunk_service,
    service_type="physical_ai_interfaces/srv/GetActionChunk",
    handler=self._handle_get_action_chunk,
    mode="queue"
)
```

---

## Change 4: GR00TInferenceManager (new)

**File (new)**: `physical_ai_server/physical_ai_server/inference/groot_inference_manager.py`

Handles action buffer management, background inference thread, and chunk alignment.

```python
class GR00TInferenceManager:
    """GR00T action chunk-based asynchronous inference manager."""

    BUFFER_REFILL_THRESHOLD = 6   # Request new chunk when buffer < this value
    ACTION_FREQ_HZ = 10.0         # Joint command publish frequency -- Comment: This might already exist in the model; what do you think?

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
        self._requesting = False  # Flag to prevent duplicate requests

        # Chunk alignment
        self._last_action = None  # Last action of previous chunk (for L2 alignment)

    def start(self, model_path, embodiment_tag, camera_topics,
              image_resize_hw, joint_state_topics, joint_names, task_instruction):
        """Setup GR00T inference: call /groot/infer + start buffer loop."""
        self._groot_client = ZenohGR00TClient(node=self._node)
        self._groot_client.connect()

        # Call /groot/infer service (setup only)
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
        # Request first chunk immediately
        self._request_chunk_async()

    def pop_action(self) -> Optional[dict]:
        """Called from 10Hz timer. Pop 1 action from buffer -> convert to joint_msg_datas."""
        with self._buffer_lock:
            if not self._action_buffer:
                return None
            action = self._action_buffer.popleft()
            remaining = len(self._action_buffer)

        # Request new chunk if buffer is below threshold and not already requesting
        if remaining < self.BUFFER_REFILL_THRESHOLD and not self._requesting:
            self._request_chunk_async()

        # action (1D np array) -> convert to joint_msg_datas dict
        return self._action_to_joint_msgs(action)

    def _request_chunk_async(self):
        """Call /groot/get_action_chunk in a background thread."""
        self._requesting = True
        self._inference_thread = threading.Thread(target=self._fetch_chunk, daemon=True)
        self._inference_thread.start()

    def _fetch_chunk(self):
        """Blocking service call -> add chunk to buffer."""
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
        """Chunk alignment via L2 distance, then add to buffer."""
        with self._buffer_lock:
            if self._last_action is not None and len(chunk) > 1:
                # Find the timestep in the new chunk closest to the last action of the previous chunk
                distances = np.linalg.norm(chunk - self._last_action, axis=1)
                start_idx = np.argmin(distances) + 1  # Start from the one after the closest
                if start_idx < len(chunk):
                    chunk = chunk[start_idx:]
            for action in chunk:
                self._action_buffer.append(action)
            if len(chunk) > 0:
                self._last_action = chunk[-1].copy()

    def _action_to_joint_msgs(self, action) -> dict:
        """Flat action array -> per-group ROS2 messages."""
        joint_msg_datas = {}
        offset = 0
        for group_name, joint_names in self._joint_order.items():
            n_joints = len(joint_names)
            values = action[offset:offset + n_joints]
            offset += n_joints

            msg_type = self._joint_topic_types.get(group_name)
            if msg_type is None:
                continue

            # Create JointState or Twist message
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
        """Stop inference and clean up."""
        self._running = False
        if self._groot_client:
            self._groot_client.stop_inference()
        with self._buffer_lock:
            self._action_buffer.clear()
        self._last_action = None
```

---

## Change 5: ZenohGR00TClient (new)

**File (new)**: `physical_ai_server/physical_ai_server/communication/zenoh_groot_client.py`

Follows the existing `ZenohLeRobotClient` pattern (ROS2 service client + rmw_zenoh).

```python
class ZenohGR00TClient:
    """Zenoh-based service communication with GR00T container."""

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
            timeout_sec=5.0)  # inference takes 100-500ms, 5 seconds for margin

    def stop_inference(self) -> LeRobotResponse:
        request = StopTraining.Request()  # Reuse existing stop service
        return self._call_service(self._stop_client, request, self.SERVICE_STOP)

    def _call_service(self, client, request, service_name, timeout_sec=10.0):
        """Same pattern as ZenohLeRobotClient._call_service."""
        # client.wait_for_service() → call_async() → spin_until_future_complete()
        ...
```
--Comment: This is not using the zenoh sdk, right? It's using ros2 + rmw_zenoh, right?

---

## Change 6: Modify physical_ai_server.py

**File**: `physical_ai_server/physical_ai_server/physical_ai_server.py`

### 6-1. Add import (line 1-60)

```python
from physical_ai_server.inference.groot_inference_manager import GR00TInferenceManager
```

### 6-2. Modify START_INFERENCE handler (line 808-829)

```python
elif request.command == SendCommand.Request.START_INFERENCE:
    self.joint_topic_types = self.communicator.get_publisher_msg_types()
    self.operation_mode = 'inference'
    task_info = request.task_info

    # Create GR00TInferenceManager
    self.groot_manager = GR00TInferenceManager(
        node=self,
        joint_topic_types=self.joint_topic_types,
        joint_order=self.joint_order  # from robot_config.yaml
    )

    # Extract topic info from robot_config.yaml
    camera_topics = self._get_camera_topics_for_inference()
    image_resize_hw = self._get_image_resize_hw()  # Read from config or use default
    joint_state_topics = self._get_follower_joint_topics()
    joint_names = self._get_flat_joint_names()  # Flatten joint_order to flat list

    # GR00T setup (model loading + subscriber start)
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

### 6-3. Rewrite _inference_timer_callback (line 573-593)

```python
def _inference_timer_callback(self):
    """10Hz timer: pop 1 action from action buffer -> publish joint command."""
    if not self.on_inference or self.groot_manager is None:
        return

    joint_msg_datas = self.groot_manager.pop_action()
    if joint_msg_datas is not None:
        self.communicator.publish_action(joint_msg_datas)
    else:
        # Buffer is empty - inference delay or still waiting for first chunk
        pass

    # Status publish
    current_status = TaskStatus()
    current_status.phase = TaskStatus.RUNNING
    self.communicator.publish_status(status=current_status)
```

### 6-4. Add helper methods

```python
def _get_camera_topics_for_inference(self) -> list:
    """Extract only topic paths from robot_config.yaml's camera_topic_list."""
    return [entry.split(':')[1] for entry in self.camera_topic_list]

def _get_follower_joint_topics(self) -> list:
    """Extract only follower topics from robot_config.yaml's joint_topic_list."""
    topics = []
    for entry in self.joint_topic_list:
        name, topic = entry.split(':')
        if 'follower' in name and 'mobile' not in name:
            topics.append(topic)
    return topics

def _get_flat_joint_names(self) -> list:
    """Flatten joint names from follower groups in joint_order into a flat list."""
    names = []
    for group, joints in self.joint_order.items():
        if 'follower' in group and 'mobile' not in group:
            names.extend(joints)
    return names

def _get_image_resize_hw(self) -> list:
    """Per-camera resize dimensions. Use default [224, 224] per camera if not in config."""
    # Use inference_image_size key from robot_config.yaml if available, otherwise use default
    default_size = [224, 224]
    n_cameras = len(self.camera_topic_list)
    return default_size * n_cameras
```

### 6-5. Add GR00T cleanup to STOP handler

In the existing stop/finish logic:
```python
if self.groot_manager:
    self.groot_manager.stop()
    self.groot_manager = None
```

---

## Change 7: Update communication/__init__.py

**File**: `physical_ai_server/physical_ai_server/communication/__init__.py`
- Add `ZenohGR00TClient` export

---

## Summary of Files to Modify

| File | Change Type | Description |
|------|------------|-------------|
| `physical_ai_interfaces/srv/GetActionChunk.srv` | **New** | Action chunk service definition |
| `physical_ai_interfaces/srv/StartInference.srv` | Modified | Add multi-topic, resize, joint_names fields |
| `physical_ai_interfaces/CMakeLists.txt` | Modified | Register GetActionChunk.srv |
| `third_party/groot/executor.py` | Modified | Multi-topic subscription, get_action_chunk handler, remove continuous loop |
| `physical_ai_server/.../inference/groot_inference_manager.py` | **New** | Action buffer, background chunk requests, L2 alignment |
| `physical_ai_server/.../communication/zenoh_groot_client.py` | **New** | GR00T Zenoh service client |
| `physical_ai_server/.../communication/__init__.py` | Modified | Add export |
| `physical_ai_server/.../physical_ai_server.py` | Modified | Inference callback, START_INFERENCE handler, helper methods |

## What Is Not Changed

- `zenoh_lerobot_client.py`: Dedicated to LeRobot container, unrelated to GR00T
- `zenoh_inference_manager.py`: For LeRobot inference, maintained separately
- `inference_manager.py`: For local LeRobot inference, maintained separately
- `communicator.py`: No change to the `publish_action()` interface (already in Dict[str, msg] format)
- Docker configuration: GR00T container already has `network_mode: host` for Zenoh access

---

## Verification Method

1. **Build test**: After `colcon build`, verify GetActionChunk.srv builds correctly in physical_ai_interfaces
2. **GR00T executor standalone test**: Run executor and verify `/groot/infer` + `/groot/get_action_chunk` services are registered
3. **E2E test**: From physical_ai_manager UI, execute START_INFERENCE -> verify robot arms move
4. **Timing verification**: Monitor `get_action_chunk` response time (100-500ms) and buffer underrun frequency
5. **Joint merge verification**: Check logs to confirm 4 joint topics are merged in the correct joint_order


-- Comment: But the important thing is that this architecture should be used identically for LeRobot too. My biggest goal is to integrate open-source action models. I want the parts that fetch data and output data from LeRobot and GR00T to be handled identically.
And the API for loading models, or requesting actions from a model - the commands are the same.
However, the way each model loads and the functions to get actions will differ per model, but I think everything else should be pretty similar, right?
So it would be nice to build this with extensibility in mind.

---

## Comment Responses (Code Analysis-based, 2nd Update)

> The responses below are based on actual source code analysis:
> - `ffw_sg2_config.py` -- GR00T modality config
> - `ffw_sg2_rev1_config.yaml` -- physical_ai_server robot config
> - `zenoh_lerobot_client.py` -- existing Zenoh client pattern
> - `executor.py` -- current GR00T executor structure

---

### Response 1: Observation dict key and ffw_sg2_config.py Mapping (data flow diagram comment)

Correct. **Core issue**: The keys of the observation dict expected by the GR00T policy are not ROS topic names but the `modality_keys` from `ffw_sg2_config.py`.

**Actual ffw_sg2_config.py analysis:**
```python
ffw_sg2_config = {
    "video": ModalityConfig(
        delta_indices=[0],
        modality_keys=["cam_left_head", "cam_left_wrist", "cam_right_wrist"],  # <- no cam_right_head!
    ),
    "state": ModalityConfig(
        delta_indices=[0],
        modality_keys=["arm_left", "arm_right"],  # <- no head, lift, mobile!
    ),
    "action": ModalityConfig(
        delta_indices=list(range(0, 16)),  # action horizon = 16 steps
        modality_keys=["arm_left", "arm_right"],  # <- action is also arm_left, arm_right only
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

**Actual ffw_sg2_rev1_config.yaml analysis:**
```yaml
camera_topic_list:                                              # yaml name -> modality key relationship
  - cam_left_head:/robot/camera/cam_left_head/...compressed     # cam_left_head -> cam_left_head  ✅ match
  - cam_right_head:/robot/camera/cam_right_head/...compressed   # cam_right_head -> (not in config) ❌ no subscription needed
  - cam_left_wrist:/robot/camera/cam_left_wrist/...compressed   # cam_left_wrist -> cam_left_wrist  ✅ match
  - cam_right_wrist:/robot/camera/cam_right_wrist/...compressed # cam_right_wrist -> cam_right_wrist ✅ match

joint_topic_list:                                                 # yaml name -> modality key relationship
  - follower_arm_left:/robot/arm_left_follower/joint_states       # follower_arm_left -> arm_left  (strip "follower_")
  - follower_arm_right:/robot/arm_right_follower/joint_states     # follower_arm_right -> arm_right (strip "follower_")
  - follower_head:/robot/head_follower/joint_states               # follower_head -> (not in config) ❌ no subscription needed
  - follower_lift:/robot/lift_follower/joint_states               # follower_lift -> (not in config) ❌ no subscription needed
  - follower_mobile:/odom                                         # follower_mobile -> (not in config) ❌ no subscription needed
```

**Therefore, the observation dict to be passed to the GR00T policy:**
```python
observation = {
    "video": {
        "cam_left_head":  np.ndarray(1,1,H,W,C),   # <- /robot/camera/cam_left_head/image_raw/compressed
        "cam_left_wrist": np.ndarray(1,1,H,W,C),   # <- /robot/camera/cam_left_wrist/image_raw/compressed
        "cam_right_wrist": np.ndarray(1,1,H,W,C),  # <- /robot/camera/cam_right_wrist/image_raw/compressed
        # cam_right_head: not subscribed (not in modality config)
    },
    "state": {
        "arm_left":  np.ndarray(1,1,8),   # <- /robot/arm_left_follower/joint_states  (8 joints)
        "arm_right": np.ndarray(1,1,8),   # <- /robot/arm_right_follower/joint_states (8 joints)
        # head, lift, mobile: not subscribed (not in modality config)
    },
    "language": {
        "annotation.human.task_description": [["Pick up the object"]]
    }
}
```

**And the action output also only contains arm_left and arm_right:**
- action chunk shape: `(16, 16)` = 16 timesteps x (8 arm_left + 8 arm_right)
- physical_ai_server only publishes to leader_arm_left and leader_arm_right
- No action publishing to head, lift, or mobile

**Design Decision -- Adopt "topic_map" approach:**

physical_ai_server sends `name:topic` format mappings via the StartInference service,
and the executor compares them against the model's `modality_keys` from modality_config to **automatically subscribe only to the necessary topics**.

```
# topic_map sent by physical_ai_server:
camera_topic_map = ["cam_left_head:/robot/camera/cam_left_head/image_raw/compressed",
                    "cam_right_head:/robot/camera/cam_right_head/image_raw/compressed",  # OK to send, executor will ignore
                    "cam_left_wrist:/robot/camera/cam_left_wrist/image_raw/compressed",
                    "cam_right_wrist:/robot/camera/cam_right_wrist/image_raw/compressed"]

joint_topic_map = ["arm_left:/robot/arm_left_follower/joint_states",
                   "arm_right:/robot/arm_right_follower/joint_states",
                   "head:/robot/head_follower/joint_states",       # OK to send, executor will ignore
                   "lift:/robot/lift_follower/joint_states"]       # OK to send, executor will ignore

# executor internal logic:
loaded_modality = load_modality_config(model_path)
video_keys = loaded_modality["video"].modality_keys  # ["cam_left_head", "cam_left_wrist", "cam_right_wrist"]
state_keys = loaded_modality["state"].modality_keys  # ["arm_left", "arm_right"]

# Matching: only subscribe to entries in topic_map whose key is in modality_keys
for name, topic in camera_topic_map:
    if name in video_keys:
        subscribe(topic, callback_with_key=name)  # <- this name becomes the key in the observation dict
```

Advantages of this approach:
1. **Directly uses** the `name:topic` format from `ffw_sg2_rev1_config.yaml` (already existing structure)
2. Simply stripping the `follower_` prefix from joint_topic_list matches the modality key
3. physical_ai_server does not need to know the model internals -- just sends all available topics
4. The executor uses the model's modality_config as the source of truth for automatic filtering

---

### Response 2: Image resize handled by the model (StartInference.srv, InferenceConfig comment)

Agreed. GR00T internal verification results:
- **Eagle3 VL Image Processor**: Default 448x448 resize
- **Gr00tN1d6Processor**: Has its own image transformation pipeline with `image_target_size`, `image_crop_size`, `shortest_image_edge=512`, etc.
- Processing order: `LetterBoxTransform` -> `Resize` -> `CenterCrop (at eval time)` -> `Resize`

**Conclusion:** **Remove `image_resize_hw` from everywhere**:
- ~~`int32[] image_resize_hw` in StartInference.srv~~ -> Deleted
- ~~`image_resize_hw` in InferenceConfig~~ -> Deleted
- ~~Resize parameters in `_setup_ros2_subscribers`~~ -> Deleted
- ~~`target_h/target_w` in `_on_image_received`~~ -> Deleted
- ~~`_get_image_resize_hw()` helper in physical_ai_server~~ -> Deleted

Since the GR00T policy transforms images using its own processor when `get_action()` is called, the executor should save raw images as-is and pass them to the policy.

However, for memory efficiency, if the original is high resolution like 1920x1080, optionally pre-resizing within the executor (e.g., to 640x480) can be kept. This is an executor internal optimization concern, not a model parameter.

---

### Response 3: Whether ACTION_FREQ_HZ can be retrieved from the model (GR00TInferenceManager comment)

After checking the GR00T modality config:
- `delta_indices=list(range(0, 16))` -> **action horizon = 16 steps** (chunk size) -- obtainable from the model
- However, **Hz information is not in the modality config**

Action frequency is determined by the collection rate of the training data:
- If data was collected at 10Hz -> replay at 10Hz
- If data was collected at 30Hz -> replay at 30Hz

**Suggestion:**
- `ACTION_FREQ_HZ` cannot be automatically retrieved from the model config, so add an `inference_freq: 10.0` entry to robot_config.yaml
- Or use the default (10Hz) but allow override during StartInference
- `action_horizon` (chunk_size=16) can be automatically determined from `modality_config["action"].delta_indices` after model loading
- **Our current FFW robot collects data at 10Hz, so the default of 10Hz is appropriate**

---

### Response 4: ZenohGR00TClient uses ROS2+rmw_zenoh (ZenohGR00TClient comment)

Yes, it uses **ROS2 + rmw_zenoh**. It is not zenoh_ros2_sdk.

Checking the actual `zenoh_lerobot_client.py` code:
```python
# physical_ai_server side (ZenohLeRobotClient) -- uses standard ROS2 API
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from physical_ai_interfaces.srv import StartInference, StopTraining, ...

self._infer_client = self._node.create_client(
    StartInference,                           # standard ROS2 service client
    self.SERVICE_INFER,
    callback_group=self._callback_group
)

# service call also uses standard ROS2 pattern
future = client.call_async(request)
rclpy.spin_until_future_complete(self._node, future, timeout_sec=self.timeout_sec)
```

ZenohGR00TClient uses the **exact same pattern**:
- `physical_ai_server` side (ZenohGR00TClient): **standard ROS2 service client** (`self._node.create_client(...)`)
  - rmw_zenoh middleware automatically handles ROS2 -> Zenoh protocol conversion
- `groot container` side (executor.py): **zenoh_ros2_sdk** (`ROS2ServiceServer`, `ROS2Subscriber`)
  - Operates natively on Zenoh without ROS2 installation, compatible with rmw_zenoh via CDR encoding

```
physical_ai_server (ROS2 + rmw_zenoh) <-> Zenoh transport <-> groot_container (zenoh_ros2_sdk)
physical_ai_server (ROS2 + rmw_zenoh) <-> Zenoh transport <-> lerobot_container (zenoh_ros2_sdk)
```

---

### Response 5: LeRobot Integration and Extensibility (final comment)

Completely agree. This should be the most important design principle.

**Parts that can be unified based on current code analysis:**

| Component | GR00T | LeRobot | Can be unified? |
|---------|-------|---------|------------|
| Service protocol (.srv) | StartInference, GetActionChunk, StopTraining | StartInference, StopTraining | **Use the same .srv** |
| In-container service handling | executor.py (_handle_infer, _handle_get_action_chunk) | executor.py (same pattern) | Only service names differ |
| Topic subscription (observation) | zenoh_ros2_sdk ROS2Subscriber | zenoh_ros2_sdk ROS2Subscriber | **Identical** |
| Model loading | Gr00tPolicy(...) | LeRobotPolicy.from_pretrained(...) | Model-specific implementation |
| Inference (get_action) | policy.get_action(observation) | policy.select_action(observation) | Model-specific function names |
| Action buffer | physical_ai_server side deque | physical_ai_server side deque | **Completely identical** |
| Chunk alignment (L2) | _align_and_enqueue | _align_and_enqueue | **Completely identical** |
| Action -> JointState conversion | _action_to_joint_msgs | _action_to_joint_msgs | **Completely identical** |
| Zenoh client (ROS2 side) | ZenohGR00TClient | ZenohLeRobotClient | Same pattern, only service names differ |

**Common Abstraction Layer Design:**

#### A. Container Side (Executor): Common Service Interface

Use different service names per model (`/groot/*`, `/lerobot/*`), but keep the .srv types identical:
```
/<model>/infer              -> Load model + start topic subscription (setup)
/<model>/get_action_chunk   -> Run inference with current observation, return action chunk
/<model>/stop               -> Stop inference
/<model>/status             -> Check status
```

Each executor implements the same pattern, only overriding model-specific differences (load, get_action):
```python
# GR00T executor
def _load_policy(self, model_path, embodiment_tag):
    from gr00t.policy.gr00t_policy import Gr00tPolicy
    return Gr00tPolicy(embodiment_tag=emb_tag, model_path=model_path, device=device)

def _run_inference(self, policy, observation):
    action, info = policy.get_action(observation)
    return action

# LeRobot executor (future)
def _load_policy(self, model_path, embodiment_tag):
    from lerobot.common.policies import get_policy_class
    return get_policy_class(policy_type).from_pretrained(model_path)

def _run_inference(self, policy, observation):
    return policy.select_action(observation)
```

#### B. physical_ai_server Side: Common InferenceManager

```python
class BaseActionChunkManager(ABC):
    """Action buffer + chunk management common to all action models."""

    # Common logic (implemented in base class):
    # - Action buffer (deque)
    # - pop_action() -> joint_msg_datas conversion
    # - _request_chunk_async() -> background thread
    # - _align_and_enqueue() -> L2 chunk alignment
    # - _action_to_joint_msgs() -> flat action -> per-group ROS2 messages
    # - start() / stop() lifecycle

    @abstractmethod
    def _create_client(self) -> BaseModelClient:
        """Create model-specific Zenoh client (GR00T / LeRobot / ...)"""
        pass

class GR00TActionChunkManager(BaseActionChunkManager):
    def _create_client(self):
        return ZenohGR00TClient(node=self._node)

class LeRobotActionChunkManager(BaseActionChunkManager):
    def _create_client(self):
        return ZenohLeRobotClient(node=self._node)  # extend existing client
```

#### C. Container Client: Common Interface

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

With this approach:
1. **Action buffer, chunk alignment, joint publishing** -> completely common (base class)
2. **Model loading, observation preprocessing, inference execution** -> model-specific implementation (inside executor)
3. **Service protocol** -> use the same .srv files (GetActionChunk.srv, StartInference.srv)
4. When adding a new model: only implement the executor, everything else is reused
5. physical_ai_server does not need to know the model type -- determines which model from policy_path and creates the appropriate manager

**Initial Implementation Strategy:**
- In this PR, implement for GR00T first, but structure the code so base class extraction is possible
- Refactor to base class when integrating LeRobot later
- Reason: Since the current LeRobot executor does not use action chunk approach, the common interface will only become clear after building both

---

## Revised Design (reflecting comments)

> Incorporating the comment responses above, we revise the changes from the original plan.
> Below describes only the **parts that differ from the original plan**.

### Revision 2' (replaces Change 2): Extend StartInference.srv

**Before (original plan):**
```
string model_path
string embodiment_tag
string[] image_topics
int32[] image_resize_hw        # <- Deleted
string[] joint_state_topics
string[] joint_names
string task_instruction
```

**After (reflecting comments):**
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

Key changes:
- `image_resize_hw` **deleted** (model's internal processor handles it)
- `image_topics` -> `camera_topic_map` (name:topic pairs, executor matches against modality_keys)
- `joint_state_topics` + `joint_names` -> `joint_topic_map` (unified as name:topic pairs)
- Executor loads the model, then filters and subscribes only to necessary keys from modality_config

### Revision 3-1' (replaces Change 3-1): InferenceConfig

```python
@dataclass
class InferenceConfig:
    model_path: str = ""
    embodiment_tag: str = "new_embodiment"
    camera_topic_map: dict = field(default_factory=dict)   # {modality_key: topic_path}
    joint_topic_map: dict = field(default_factory=dict)    # {modality_key: topic_path}
    task_instruction: str = ""
    # image_resize_hw deleted
    # inference_freq deleted (executor does not need frequency, on-demand approach)
    # joint_names deleted (merged into joint_topic_map)
```

### Revision 3-3' (replaces Change 3-3): Modify _handle_infer

```python
def _handle_infer(self, request):
    # 1. Load model
    model_path = request.model_path
    embodiment_tag = request.embodiment_tag or "new_embodiment"
    self._loaded_policy = self._load_policy(model_path, embodiment_tag)

    # 2. Read model's modality_config
    modality_config = self._get_modality_config()  # Auto-extracted from model
    video_keys = modality_config["video"].modality_keys   # ["cam_left_head", "cam_left_wrist", "cam_right_wrist"]
    state_keys = modality_config["state"].modality_keys   # ["arm_left", "arm_right"]
    action_keys = modality_config["action"].modality_keys  # ["arm_left", "arm_right"]

    # 3. Parse request's topic_map and filter by modality_keys
    camera_topic_map = self._parse_topic_map(request.camera_topic_map)  # {"cam_left_head": "/robot/...", ...}
    joint_topic_map = self._parse_topic_map(request.joint_topic_map)    # {"arm_left": "/robot/...", ...}

    # Filter to only what's needed
    active_cameras = {k: v for k, v in camera_topic_map.items() if k in video_keys}
    active_joints = {k: v for k, v in joint_topic_map.items() if k in state_keys}

    # 4. Subscribe only to filtered topics
    self._setup_ros2_subscribers(active_cameras, active_joints)

    # 5. Initialize observation dict (based on modality keys)
    self._latest_observations = {
        "video": {key: None for key in active_cameras},
        "state": {key: None for key in active_joints},
        "language": {},
        "timestamp": None,
    }

    # 6. State transition (do not start continuous loop)
    self._inference_running = True
    self.state = ExecutorState.INFERENCE

    # 7. Save action_keys (used for action chunk -> modality key mapping in responses)
    self._action_keys = action_keys

    return self._create_response(self._infer_service, success=True, message="GR00T inference started")
```

### Revision 3-4' (replaces Change 3-4): _setup_ros2_subscribers (modality key-based)

```python
def _setup_ros2_subscribers(self, active_cameras: dict, active_joints: dict):
    """Subscribe only to necessary topics based on modality key -> topic mapping.

    Args:
        active_cameras: {modality_key: topic_path}  e.g. {"cam_left_head": "/robot/camera/cam_left_head/..."}
        active_joints:  {modality_key: topic_path}  e.g. {"arm_left": "/robot/arm_left_follower/joint_states"}
    """
    # Camera subscription -- key becomes the dict key for observation["video"]
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

    # Joint subscription -- key becomes the dict key for observation["state"]
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

### Revision 3-5' (replaces Change 3-5): _on_image_received (resize removed)

```python
def _on_image_received(self, modality_key: str, msg):
    """Store camera image based on modality key. Resize is handled by the model."""
    image_data = np.frombuffer(bytes(msg.data), dtype=np.uint8)
    image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
    if image is not None:
        # No resize -- GR00T policy's internal processor handles it
        image = image[np.newaxis, np.newaxis, ...]  # (1,1,H,W,C)
        self._latest_observations["video"][modality_key] = image
        self._latest_observations["timestamp"] = time.time()
```

### Revision 3-6' (replaces Change 3-6): _on_joint_state_received (per-key storage)

The original `_on_multi_joint_state_received` was based on a merged_state array,
but storing **each independently as (1,1,D) per modality key** matches the GR00T observation format:

```python
def _on_joint_state_received(self, modality_key: str, msg):
    """Store joint state independently per modality key.

    Each key is stored as a (1,1,D) numpy array and passed directly to the policy.
    e.g. observation["state"]["arm_left"] = np.array(1,1,8)
    """
    positions = np.array(msg.position, dtype=np.float32)
    self._latest_observations["state"][modality_key] = positions[np.newaxis, np.newaxis, :]
    self._latest_observations["timestamp"] = time.time()
```

### Revision 3-7' (replaces Change 3-7): _handle_get_action_chunk (action key-based)

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

    # Pass observation dict as-is -- keys are already modality keys
    observation = {
        "video": obs["video"],
        "state": obs["state"],
        "language": obs["language"]
    }
    action, info = self._loaded_policy.get_action(observation)

    # action: {"arm_left": (1,16,8), "arm_right": (1,16,8)} format
    # -> concat to flat chunk: (16, 16) -> flatten
    chunks = []
    for key in self._action_keys:  # ["arm_left", "arm_right"] order guaranteed
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

### Revision 4' (replaces Change 4): GR00TInferenceManager

Key change: `_action_to_joint_msgs` needs modality key -> leader topic mapping.

```python
class GR00TInferenceManager:
    def __init__(self, node, joint_topic_types: dict, joint_order: dict,
                 action_joint_map: dict):
        """
        Args:
            action_joint_map: modality key -> leader group name mapping
                e.g. {"arm_left": "leader_arm_left", "arm_right": "leader_arm_right"}
        """
        self._action_joint_map = action_joint_map
        # ... rest is the same

    def _action_to_joint_msgs(self, action) -> dict:
        """Flat action array -> per-group ROS2 messages.

        action is a (D_total,) 1D array, concatenated in action_keys order.
        e.g. action = [arm_l_j1..j7, grip_l, arm_r_j1..j7, grip_r]  (16 dims)

        action_joint_map determines which leader topic to publish to:
        - "arm_left" -> leader_arm_left topic
        - "arm_right" -> leader_arm_right topic
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

### Revision 6' (replaces Change 6): physical_ai_server.py helper methods

```python
def _get_camera_topic_map(self) -> list:
    """Return 'name:topic' format list from robot_config.yaml's camera_topic_list.

    yaml: cam_left_head:/robot/camera/cam_left_head/image_raw/compressed
    -> "cam_left_head:/robot/camera/cam_left_head/image_raw/compressed"

    Executor matches against modality_config and subscribes only to what's needed.
    """
    return list(self.params['camera_topic_list'])  # Already in "name:topic" format

def _get_joint_topic_map(self) -> list:
    """Return 'modality_key:topic' format list of follower topics from robot_config.yaml's joint_topic_list.

    yaml: follower_arm_left:/robot/arm_left_follower/joint_states
    -> "arm_left:/robot/arm_left_follower/joint_states"  (strip "follower_" prefix)
    """
    result = []
    for entry in self.params['joint_topic_list']:
        name, topic = entry.split(':', 1)
        if 'follower' in name and 'mobile' not in name:
            # "follower_arm_left" -> "arm_left"
            modality_key = name.replace('follower_', '')
            result.append(f"{modality_key}:{topic}")
    return result

def _get_action_joint_map(self) -> dict:
    """action modality key -> leader group mapping.

    Connects modality config's action_keys (e.g. ["arm_left", "arm_right"]) with
    robot_config's leader groups (e.g. "leader_arm_left", "leader_arm_right").
    """
    action_map = {}
    for group_name in self.joint_order:
        if 'leader' in group_name and 'mobile' not in group_name:
            # "leader_arm_left" -> modality_key "arm_left"
            modality_key = group_name.replace('leader_', '')
            action_map[modality_key] = group_name
    return action_map
```

---

## Revised Overall Data Flow (reflecting comments)

```
Robot Topics (Zenoh)                         ffw_sg2_config.py (modality config)
  │                                          video.modality_keys = ["cam_left_head", "cam_left_wrist", "cam_right_wrist"]
  │                                          state.modality_keys = ["arm_left", "arm_right"]
  │                                          action.modality_keys = ["arm_left", "arm_right"]
  │
  │  physical_ai_server                      GR00T Container (executor.py)
  │  ┌────────────────────┐                  ┌──────────────────────────────────────┐
  │  │ START_INFERENCE:    │                  │                                      │
  │  │ camera_topic_map =  │ /groot/infer     │ 1. Load model -> read modality_config│
  │  │  [cam_left_head:...,│───────────────>  │ 2. Match topic_map ∩ modality_keys   │
  │  │   cam_right_head:..,│                  │    -> cam_right_head not subscribed! │
  │  │   cam_left_wrist:., │                  │    -> head/lift/mobile not subscribed!│
  │  │   cam_right_wrist:.]│                  │ 3. Subscribe only to needed topics:  │
  │  │ joint_topic_map =   │                  │    - cam_left_head -> obs["video"]["cam_left_head"]
  │  │  [arm_left:...,     │                  │    - cam_left_wrist -> obs["video"]["cam_left_wrist"]
  │  │   arm_right:...,    │                  │    - cam_right_wrist -> obs["video"]["cam_right_wrist"]
  │  │   head:...,         │                  │    - arm_left -> obs["state"]["arm_left"]
  │  │   lift:...]         │                  │    - arm_right -> obs["state"]["arm_right"]
  │  └────────────────────┘                  │                                      │
  │                                          │ 4. Wait for get_action_chunk service │
  │  ┌────────────────────┐                  │                                      │
  │  │ 10Hz Timer:         │ get_action_chunk │ 5. policy.get_action(observation)    │
  │  │ buffer < 6 →────────│───────────────>  │    -> action: {"arm_left": (1,16,8), │
  │  │                     │                  │              "arm_right": (1,16,8)}  │
  │  │ ┌──────────────┐   │  (16,16) chunk   │    -> concat -> (16,16) flatten      │
  │  │ │Action Buffer │<───│<─────────────── │       and return                     │
  │  │ │ pop 1 action │   │                  └──────────────────────────────────────┘
  │  │ │              │   │
  │  │ └──────┬───────┘   │
  │  │        │            │
  │  │   action_to_joint   │   action_joint_map:
  │  │   _msgs()           │   "arm_left" -> leader_arm_left
  │  │        │            │   "arm_right" -> leader_arm_right
  │  │        v            │
  │  └────────────────────┘
  │       │           │
  │       v           v
  │  /robot/arm_left_leader/joint_states    (8 joints: arm_l_j1-7, gripper_l)
  │  /robot/arm_right_leader/joint_states   (8 joints: arm_r_j1-7, gripper_r)
  │  (no publishing to head, lift, mobile -- not in action config)
```

---

## Revised Summary of Files to Modify (reflecting comments)

| File | Change Type | Description | Changes from Comments |
|------|------------|-------------|----------------|
| `physical_ai_interfaces/srv/GetActionChunk.srv` | **New** | Action chunk service definition | No change |
| `physical_ai_interfaces/srv/StartInference.srv` | Modified | ~~image_resize_hw~~, camera_topic_map, joint_topic_map | image_resize_hw deleted, changed to topic_map approach |
| `physical_ai_interfaces/CMakeLists.txt` | Modified | Register GetActionChunk.srv | No change |
| `third_party/groot/executor.py` | Modified | Modality key-based subscription, get_action_chunk, loop removed | Per-key observation, auto-read modality_config |
| `physical_ai_server/.../inference/groot_inference_manager.py` | **New** | Action buffer, background chunk requests, L2 alignment | action_joint_map-based publishing |
| `physical_ai_server/.../communication/zenoh_groot_client.py` | **New** | GR00T ROS2+rmw_zenoh service client | Confirmed: not zenoh_sdk |
| `physical_ai_server/.../communication/__init__.py` | Modified | Add export | No change |
| `physical_ai_server/.../physical_ai_server.py` | Modified | Inference callback, helper methods | Added topic_map helper, action_joint_map helper |

---

## Remaining Decisions

1. **Location of ffw_sg2_config.py**: Currently at `Isaac-GR00T/examples/ffw_sg2/`, but can the executor automatically find this config when loading the model? `register_modality_config()` must be called before executor starts.
   - Option A: Pass config file path to executor.py via environment variable at startup
   - Option B: Store config file together with model_path (included in finetune results)
   - Option C: Add config_path parameter to StartInference

2. **ACTION_FREQ_HZ**: Whether to add an `inference_freq` field to robot_config.yaml or fix it at the default of 10Hz

3. **mobile base action**: Currently mobile is not in ffw_sg2_config, but Twist message conversion logic will be needed if it is added in the future
