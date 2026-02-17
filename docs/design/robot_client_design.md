# Robot Client 설계 문서

## 1. 개요

### 1.1 목적

현재 각 opensource 프로젝트(GR00T, LeRobot 등)의 executor가 1,400줄 이상의 코드를 가지고 있으며,
그 중 ~800줄(60%)이 Zenoh/ROS2 통신 인프라 코드입니다.

새로운 프로젝트를 통합할 때마다 이 인프라 코드를 복사해야 하는 구조는 확장성이 없습니다.

**Robot Client**는 zenoh_ros2_sdk 위에 위치하는 **고수준 추상화 레이어**로,
Zenoh/ROS2를 몰라도 로봇 데이터를 쉽게 읽고 쓸 수 있는 Python API를 제공합니다.

### 1.2 설계 원칙

- **zenoh_ros2_sdk는 수정하지 않는다** (그대로 사용)
- Zenoh/ROS2 메시지 포맷을 몰라도 사용 가능해야 한다
- 데이터는 항상 Python 기본 타입(numpy array, list, dict)으로 제공한다
- 센서 데이터는 항상 최신값을 유지한다 (백그라운드 구독)
- 로봇 타입만 지정하면 토픽이 자동으로 설정된다

### 1.3 커스텀 메시지 분리

현재 `physical_ai_interfaces`에 정의된 커스텀 메시지/서비스가 8 msg + 26 srv로 많습니다.
이들은 학습/추론/데이터셋 관리 등 physical_ai_tools 전용 인터페이스입니다.

zenoh_ros2_sdk는 범용 ROS2 통신 라이브러리이므로, 이 커스텀 메시지들을
robot_client 패키지 내 `messages/` 디렉토리로 분리합니다.

- **zenoh_ros2_sdk**: 표준 ROS2 메시지만 처리 (sensor_msgs, geometry_msgs 등)
- **robot_client/messages/**: physical_ai_tools 전용 메시지 정의
  - TrainingProgress, ActionOutput 등의 msg
  - StartInference, GetActionChunk, TrainModel 등의 srv

### 1.4 위치

```
zenoh_ros2_sdk/          # 기존 (수정 안함)
  ├── publisher.py
  ├── subscriber.py
  ├── service_server.py
  └── ...

robot_client/            # 신규 패키지
  ├── __init__.py
  ├── robot_client.py    # 센서 읽기 + 액션 출력
  ├── service_server.py  # 학습/추론 서비스 프레임워크
  ├── messages/          # physical_ai_tools 전용 메시지
  │   ├── __init__.py
  │   ├── msg/           # TrainingProgress, ActionOutput 등
  │   └── srv/           # StartInference, GetActionChunk 등
  ├── config/            # 로봇 타입별 설정
  │   ├── ffw_sg2_rev1.yaml
  │   ├── omx_f.yaml
  │   └── omy_f3m.yaml
  └── README.md
```

---

## 2. RobotClient - 센서 데이터 읽기 / 액션 출력

### 2.1 초기화

```python
from robot_client import RobotClient

robot = RobotClient("ffw_sg2_rev1")

# 타임스탬프 동기화 체크 모드 (선택)
robot = RobotClient("ffw_sg2_rev1", sync_check=True, sync_threshold_ms=33)
```

생성자에서 로봇 타입에 해당하는 YAML 설정을 읽고,
모든 센서 토픽을 자동으로 구독합니다.

내부적으로:
1. `config/ffw_sg2_rev1.yaml` 로드
2. 각 카메라 토픽에 대해 `ROS2Subscriber` 생성 (CompressedImage)
3. 각 조인트 토픽에 대해 `ROS2Subscriber` 생성 (JointState)
4. 각 센서 토픽에 대해 `ROS2Subscriber` 생성 (Odometry, Twist, TF 등)
5. 백그라운드에서 콜백으로 최신값 갱신

### 2.2 설정 파일 구조

기존 `physical_ai_server/config/ffw_sg2_rev1_config.yaml`의 구조를 기반으로 합니다.

```yaml
# config/ffw_sg2_rev1.yaml
robot_name: "FFW SG2 Rev1"
total_dof: 22

cameras:
  cam_left_head:
    topic: "/robot/camera/cam_left_head/image_raw/compressed"
    msg_type: "sensor_msgs/msg/CompressedImage"

  cam_right_head:
    topic: "/robot/camera/cam_right_head/image_raw/compressed"
    msg_type: "sensor_msgs/msg/CompressedImage"

  cam_left_wrist:
    topic: "/robot/camera/cam_left_wrist/image_raw/compressed"
    msg_type: "sensor_msgs/msg/CompressedImage"

  cam_right_wrist:
    topic: "/robot/camera/cam_right_wrist/image_raw/compressed"
    msg_type: "sensor_msgs/msg/CompressedImage"

joint_groups:
  leader_arm_left:
    topic: "/robot/arm_left_leader/joint_states"
    msg_type: "sensor_msgs/msg/JointState"
    role: "leader"
    joint_names: ["arm_l_joint1", "arm_l_joint2", "arm_l_joint3", "arm_l_joint4",
                   "arm_l_joint5", "arm_l_joint6", "arm_l_joint7", "gripper_l_joint1"]
    dof: 8

  leader_arm_right:
    topic: "/robot/arm_right_leader/joint_states"
    msg_type: "sensor_msgs/msg/JointState"
    role: "leader"
    joint_names: ["arm_r_joint1", "arm_r_joint2", "arm_r_joint3", "arm_r_joint4",
                   "arm_r_joint5", "arm_r_joint6", "arm_r_joint7", "gripper_r_joint1"]
    dof: 8

  follower_arm_left:
    topic: "/robot/arm_left_follower/joint_states"
    msg_type: "sensor_msgs/msg/JointState"
    role: "follower"
    joint_names: ["arm_l_joint1", "arm_l_joint2", "arm_l_joint3", "arm_l_joint4",
                   "arm_l_joint5", "arm_l_joint6", "arm_l_joint7", "gripper_l_joint1"]
    dof: 8

  follower_arm_right:
    topic: "/robot/arm_right_follower/joint_states"
    msg_type: "sensor_msgs/msg/JointState"
    role: "follower"
    joint_names: ["arm_r_joint1", "arm_r_joint2", "arm_r_joint3", "arm_r_joint4",
                   "arm_r_joint5", "arm_r_joint6", "arm_r_joint7", "gripper_r_joint1"]
    dof: 8

  leader_head:
    topic: "/robot/head_leader/joint_states"
    msg_type: "sensor_msgs/msg/JointState"
    role: "leader"
    joint_names: ["head_joint1", "head_joint2"]
    dof: 2

  follower_head:
    topic: "/robot/head_follower/joint_states"
    msg_type: "sensor_msgs/msg/JointState"
    role: "follower"
    joint_names: ["head_joint1", "head_joint2"]
    dof: 2

  leader_lift:
    topic: "/robot/lift_leader/joint_states"
    msg_type: "sensor_msgs/msg/JointState"
    role: "leader"
    joint_names: ["lift_joint"]
    dof: 1

  follower_lift:
    topic: "/robot/lift_follower/joint_states"
    msg_type: "sensor_msgs/msg/JointState"
    role: "follower"
    joint_names: ["lift_joint"]
    dof: 1

# 추가 센서
sensors:
  odom:
    topic: "/odom"
    msg_type: "nav_msgs/msg/Odometry"

  cmd_vel:
    topic: "/cmd_vel"
    msg_type: "geometry_msgs/msg/Twist"

# rosbag 녹화 시 추가 토픽
rosbag_extra_topics:
  - "/tf"
  - "/odom"
  - "/cmd_vel"
```

### 2.3 이미지 API

기본 포맷은 **BGR** (OpenCV 기본, GR00T도 BGR 입력 사용).
기본 크기는 **원본 사이즈** (리사이즈 없음). `resize` 파라미터를 지정한 경우에만 리사이즈 수행.

```python
# 전체 카메라 이미지 (dict) - 원본 사이즈, BGR
images = robot.get_images()
# {
#   "cam_left_head":  np.ndarray (H, W, 3) uint8 BGR,
#   "cam_right_head": np.ndarray (H, W, 3) uint8 BGR,
#   "cam_left_wrist": np.ndarray (H, W, 3) uint8 BGR,
#   "cam_right_wrist": np.ndarray (H, W, 3) uint8 BGR,
# }

# RGB 포맷으로 받기
images = robot.get_images(format="rgb")

# 리사이즈 지정 (지정하지 않으면 원본 사이즈)
images = robot.get_images(resize=(256, 256))

# 특정 카메라만
img = robot.get_image("cam_left_head")
# np.ndarray (H, W, 3) uint8 BGR

# 특정 카메라 + 리사이즈 + RGB
img = robot.get_image("cam_left_head", resize=(256, 256), format="rgb")

# 카메라 목록 조회
robot.camera_names  # ["cam_left_head", "cam_right_head", ...]

# 데이터 수신 여부 확인
robot.is_image_ready("cam_left_head")  # True/False

# 타임스탬프 확인
robot.get_image_timestamp("cam_left_head")  # float (epoch seconds)
```

### 2.4 조인트 API

반환 타입은 **`np.ndarray`** (float32). GR00T가 `np.ndarray(dtype=np.float32)` 형태로 state 데이터를 사용하므로 이에 맞춥니다.
leader/follower 구분을 유지하며, **gripper도 position에 포함**됩니다 (joint_names의 마지막 원소).

> **참고: Leader 토픽 구분**
> Leader는 모터로 구성되어 있어, **읽기**(현재 각도 조회)와 **쓰기**(제어 명령)에 다른 토픽을 사용합니다.
> 현재는 동일한 JointState 토픽(`read_topic`)으로 통일하되,
> 설정 파일에서 `write_topic`을 별도 지정할 수 있도록 확장 가능한 구조로 설계합니다.
> Follower는 읽기 전용이므로 `read_topic`만 사용합니다.

```python
# 전체 조인트 (dict of np.ndarray)
joints = robot.get_joint_positions()
# {
#   "leader_arm_left":    np.ndarray([0.1, 0.2, ..., 0.0], dtype=float32),  # 7 joints + 1 gripper
#   "leader_arm_right":   np.ndarray([0.1, 0.2, ..., 0.0], dtype=float32),
#   "follower_arm_left":  np.ndarray([0.1, 0.2, ..., 0.0], dtype=float32),
#   "follower_arm_right": np.ndarray([0.1, 0.2, ..., 0.0], dtype=float32),
#   "leader_head":        np.ndarray([0.0, 0.0], dtype=float32),
#   "follower_head":      np.ndarray([0.0, 0.0], dtype=float32),
#   "leader_lift":        np.ndarray([0.0], dtype=float32),
#   "follower_lift":      np.ndarray([0.0], dtype=float32),
# }

# 특정 그룹만
left_arm = robot.get_joint_positions("leader_arm_left")
# np.ndarray([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.0], dtype=float32)

# joint velocity도 필요할 수 있음
velocities = robot.get_joint_velocities()
# (동일 구조, JointState.velocity에서 추출)

# joint effort (torque)
efforts = robot.get_joint_efforts()

# 조인트 그룹 정보
robot.joint_group_names  # ["leader_arm_left", "leader_arm_right", ...]
robot.get_joint_names("leader_arm_left")  # ["arm_l_joint1", ..., "gripper_l_joint1"]
robot.get_dof("leader_arm_left")  # 8
robot.total_dof  # 22

# 데이터 수신 여부
robot.is_joint_ready("leader_arm_left")  # True/False
```

### 2.5 추가 센서 API

카메라와 조인트 외에 odometry, velocity 등 추가 센서 데이터를 제공합니다.

```python
# Odometry (위치 + 방향 + 속도)
odom = robot.get_odom()
# {
#   "position": np.ndarray([x, y, z], dtype=float32),
#   "orientation": np.ndarray([x, y, z, w], dtype=float32),  # quaternion
#   "linear_velocity": np.ndarray([vx, vy, vz], dtype=float32),
#   "angular_velocity": np.ndarray([wx, wy, wz], dtype=float32),
# }

# 센서 데이터 수신 여부
robot.is_sensor_ready("odom")  # True/False
```

### 2.6 액션 출력 API

액션 발행은 **두 가지 방식**을 모두 지원합니다:
- **직접 발행**: RobotClient가 직접 로봇에 publish
- **서비스 방식**: 기존처럼 `get_action_chunk` 서비스 응답으로 반환 → physical_ai_server가 publish

**follower 그룹은 읽기 전용**이므로, set 명령을 보내도 동작하지 않습니다.

#### Action Chunk 처리

모델 출력은 action chunk (T×D, 예: 16 timestep × action_dim)입니다.
이를 로봇에 보내는 방법은 두 가지입니다:

| 방식 | 메시지 타입 | 주기 스레드 | 설명 |
|------|-----------|-----------|------|
| **현재 구현** | JointState | 필요 (10Hz) | 버퍼에서 1개씩 pop하여 발행 |
| **향후 전환** | JointTrajectory | 불필요 | chunk 전체를 한번에 trajectory points로 발행 |

현재는 JointState 기반 (기존 physical_ai_server와 동일), 향후 JointTrajectory로 전환 가능합니다.

```python
# 방법 1: 직접 발행 - 단일 액션 (RobotClient → 로봇)
# leader 그룹에만 명령 가능 (follower는 읽기 전용)
robot.set_joint_positions("leader_arm_left", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.0])

# 여러 그룹 동시 명령
robot.set_joint_positions({
    "leader_arm_left":  [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.0],
    "leader_arm_right": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.0],
})

# 방법 1-2: 직접 발행 - Action Chunk (내부 10Hz 타이머로 순차 발행)
# action_chunk: np.ndarray (T, D) - 모델 출력 그대로
robot.execute_action_chunk(action_chunk, action_keys=["leader_arm_left", "leader_arm_right"],
                           frequency=10)
# 내부에서 10Hz 타이머가 chunk에서 1개씩 pop하여 JointState로 publish
# L2 distance 기반 chunk 정렬 (현재 physical_ai_server와 동일한 로직)

# 모바일 베이스 제어 (Twist 메시지로 publish)
robot.set_velocity(linear_x=0.5, linear_y=0.0, angular_z=0.1)

# 방법 2: 서비스 방식 (executor → physical_ai_server → 로봇)
# on_get_action 핸들러에서 action chunk를 반환하면,
# physical_ai_server의 InferenceManager가 10Hz 타이머로 1개씩 pop하여 로봇에 publish
@server.on_get_action
def handle_get_action(request):
    obs = robot.get_observation()
    action, info = policy.get_action(obs)
    return {"action_chunk": action, "chunk_size": 16}
```

standalone 스크립트에서 직접 제어할 때는 방법 1/1-2,
async inference (physical_ai_server 경유)에서는 방법 2를 사용합니다.

### 2.7 Task Instruction

`set_task_instruction()`으로 현재 작업 지시를 설정합니다.
GR00T 등 language-conditioned 모델에서 observation의 일부로 사용됩니다.

```python
# 작업 지시 설정
robot.set_task_instruction("pick up the red cup")

# 현재 설정된 지시 확인
robot.task_instruction  # "pick up the red cup"
```

`set_task_instruction()`을 별도 API로 분리하는 이유:
- task instruction은 센서 데이터처럼 매 프레임 변하지 않음
- inference 시작 시 한번 설정하면 변경 전까지 유지
- observation에 자동으로 포함됨 (아래 2.8 참고)

### 2.8 데이터 동기화 / 대기

```python
# 모든 센서가 최소 1번 이상 수신될 때까지 대기
robot.wait_for_ready(timeout=10.0)

# 특정 센서만 대기
robot.wait_for_image("cam_left_head", timeout=5.0)
robot.wait_for_joint("leader_arm_left", timeout=5.0)

# 전체 observation을 한번에 (inference용)
obs = robot.get_observation()
# {
#   "images": {"cam_left_head": np.ndarray, ...},
#   "joint_positions": {"leader_arm_left": np.ndarray, ...},
#   "task_instruction": "pick up the red cup",
# }
# 참고: timestamp는 observation에 포함하지 않음 (일반적으로 모델 입력에 사용되지 않음)
#
# 두 프레임워크 모두 observation은 images + state(joints) + language 3가지가 핵심:
#   - GR00T: video(uint8, B,T,H,W,C) + state(float32, B,T,D) + language(list[list[str]])
#   - LeRobot: observation.images(float32, B,C,H,W, [0,1]) + observation.state(float32, B,D) + language(tokens)
# 추가 항목은 없으며, 각 프레임워크의 observation 포맷 변환은 executor에서 처리합니다.
```

#### 타임스탬프 동기화 체크 (선택 기능)

초기화 시 `sync_check=True`로 설정하면, 이미지와 조인트 데이터의 타임스탬프 차이를
확인하여 유효하지 않은 observation을 걸러냅니다.

```python
# sync_check 모드 활성화 (기본값: False)
robot = RobotClient("ffw_sg2_rev1", sync_check=True, sync_threshold_ms=33)

# get_observation() 호출 시:
# - 이미지와 조인트 데이터의 타임스탬프 차이가 33ms 이상이면 None 반환
# - 호출하는 쪽에서 None인 경우 해당 프레임의 inference를 건너뛰도록 처리
obs = robot.get_observation()
if obs is None:
    # 센서 데이터 동기화 실패 → inference 스킵
    continue
```

sync_check를 선택적으로 만든 이유:
- 모든 상황에서 정밀한 동기화가 필요한 것은 아님
- 개발/디버깅 시에는 동기화 체크 없이 사용하는 것이 편함
- 실제 inference 시에만 활성화하여 데이터 품질 보장
---

## 3. RobotServiceServer - 학습/추론 서비스 프레임워크

### 3.1 개요

각 executor에서 반복되는 서비스 등록/핸들링/상태관리를 추상화합니다.
RobotClient와 별도로 사용하며, 사용자가 직접 조합하는 구조입니다.

### 3.2 기본 사용법

```python
from robot_client import RobotClient, RobotServiceServer

# RobotClient와 RobotServiceServer를 별도로 생성
robot = RobotClient("ffw_sg2_rev1")
server = RobotServiceServer(name="groot")   # 서비스 prefix: /groot/train, /groot/infer, ...
```

### 3.3 서비스 핸들러 등록

#### 학습 (on_train)

학습 파라미터는 모델마다 다릅니다 (GR00T: `embodiment_tag`, `num_diffusion_steps`,
LeRobot: `eval_freq`, `num_workers`, OpenVLA: `lora_rank` 등).

공통 필드는 타입으로 명시하고, 모델별 고유 파라미터는 `extra_params`(JSON → dict)로 처리합니다.
이미 프로젝트에서 JSON string 패턴을 사용 중입니다 (`models_json`, `policies_json` 등).

```python
@server.on_train
def handle_train(request) -> dict:
    """
    request 필드:
      - model_path: str           # 공통 (모든 모델에 필요)
      - dataset_path: str         # 공통
      - output_dir: str           # 공통
      - extra_params: dict        # 모델별 고유 파라미터 (JSON → dict 자동 변환)
        예) GR00T:  {"embodiment_tag": "gr1", "steps": 1000, "batch_size": 32, ...}
        예) LeRobot: {"steps": 5000, "eval_freq": 500, "wandb_project": "my_project", ...}

    반환: {"success": bool, "message": str}
    """
    extra = request.extra_params  # dict로 접근
    config = build_finetune_config(
        model_path=request.model_path,
        dataset_path=request.dataset_path,
        steps=extra.get("steps", 1000),
        batch_size=extra.get("batch_size", 32),
        learning_rate=extra.get("learning_rate", 1e-4),
        # ... 모델별 추가 파라미터
    )
    run_training(config)
    return {"success": True, "message": "Training complete"}
```

서비스 메시지 정의:
```
# TrainModel.srv
string model_path
string dataset_path
string output_dir
string extra_params_json    # JSON string → server 내부에서 dict로 변환
---
bool success
string message
string job_id
```

#### 모델 로드 (on_load_policy)

RobotClient가 로봇 토픽을 자동 구독하므로, `camera_topic_map`과 `joint_topic_map`은 불필요합니다.
`task_instruction`은 초기값으로 설정 가능하며, inference 중에도 `get_action` 호출 시 변경 가능합니다.

```python
@server.on_load_policy
def handle_load_policy(request) -> dict:
    """
    request 필드:
      - model_path: str
      - embodiment_tag: str (optional)
      - task_instruction: str (optional, 초기 task)
      - extra_params: dict (optional, 모델별 추가 설정)

    반환: {"success": bool, "message": str, "action_keys": list[str]}
    """
    policy = load_model(request.model_path)
    if request.task_instruction:
        robot.set_task_instruction(request.task_instruction)
    return {"success": True, "action_keys": policy.action_keys}
```

> **참고:** 각 데코레이터 핸들러(`on_load_policy`, `on_get_action` 등)는 **프로젝트별로 다르게 구현**합니다.
> 위의 `load_model()`, `policy.get_action()`은 placeholder이며, GR00T/LeRobot/OpenPI 등에서 각자의 API로 구현합니다.
> `policy` 같은 변수를 핸들러 간에 공유할 때는 클래스 인스턴스 변수나 모듈 레벨 변수를 사용합니다.

#### 정지 (on_stop)

```python
@server.on_stop
def handle_stop() -> dict:
    cleanup()
    return {"success": True}
```

#### 액션 생성 (on_get_action)

매 호출마다 `task_instruction`을 변경할 수 있어, 하나의 모델로 multi-task 수행이 가능합니다.

```python
@server.on_get_action
def handle_get_action(request) -> dict:
    """
    request 필드:
      - task_instruction: str (optional, 변경 시에만)

    반환: {"action_chunk": np.ndarray, "chunk_size": int}
    """
    # task_instruction이 포함되어 있으면 업데이트
    if request.task_instruction:
        robot.set_task_instruction(request.task_instruction)

    obs = robot.get_observation()
    action, info = policy.get_action(obs)
    return {"action_chunk": action, "chunk_size": 16}
```

multi-task 시나리오 예시:
```
1. StartInference(model_path="...", task_instruction="pick up the apple")
2. GetActionChunk()                                          → "pick up the apple"로 inference
3. GetActionChunk()                                          → 동일
4. GetActionChunk(task_instruction="place it on the plate")  → task 변경!
5. GetActionChunk()                                          → "place it on the plate"로 inference
```

### 3.4 학습 progress 보고

학습 progress는 **직접 접근 방식을 권장**합니다. 로그 파싱은 fallback으로만 유지합니다.

#### GR00T (HuggingFace Trainer)

HuggingFace `TrainerCallback`을 사용하면 로그 파싱 없이 metrics에 직접 접근 가능합니다.

```python
# gr00t/experiment/trainer.py 내부:
# Gr00tTrainer.compute_loss()에서 loss를 계산하고,
# HF Trainer가 logging_steps마다 on_log 콜백을 호출합니다.

from transformers import TrainerCallback

class ProgressCallback(TrainerCallback):
    def __init__(self, server):
        self.server = server

    def on_log(self, args, state, control, logs=None, **kwargs):
        # logs: {"loss": 0.45, "learning_rate": 1.2e-4, "grad_norm": 0.8, ...}
        # state: global_step, max_steps, epoch 등
        self.server.report_progress(
            step=state.global_step,
            total_steps=state.max_steps,
            epoch=state.epoch,
            loss=logs.get("loss", 0),
            learning_rate=logs.get("learning_rate", 0),
            gradient_norm=logs.get("grad_norm", 0),
        )

# executor에서 사용:
trainer = Gr00tTrainer(model=model, args=training_args, ...)
trainer.add_callback(ProgressCallback(server))
trainer.train()
```

#### LeRobot (커스텀 학습 루프 + Accelerator)

커스텀 루프이므로 `update_policy()` 후 `MetricsTracker`에서 직접 접근합니다.

```python
# lerobot/scripts/lerobot_train.py 내부:
# update_policy()가 forward + backward를 수행하고,
# train_tracker(MetricsTracker)에 loss, grad_norm, lr 등이 기록됩니다.

for step in range(total_steps):
    train_tracker, output_dict = update_policy(
        train_tracker, policy, batch, optimizer, ...
    )

    # MetricsTracker에서 직접 접근 (로그 파싱 불필요)
    server.report_progress(
        step=step,
        total_steps=total_steps,
        loss=train_tracker.loss,
        learning_rate=train_tracker.lr,
        gradient_norm=train_tracker.grad_norm,
        epoch=train_tracker.epochs,
    )
```

#### 사용 가능한 metrics 비교

| Metric | GR00T (TrainerCallback) | LeRobot (MetricsTracker) |
|--------|------------------------|--------------------------|
| loss | `logs["loss"]` | `tracker.loss` |
| learning_rate | `logs["learning_rate"]` | `tracker.lr` |
| gradient_norm | `logs["grad_norm"]` | `tracker.grad_norm` |
| step | `state.global_step` | loop counter |
| epoch | `state.epoch` | `tracker.epochs` |
| accuracy | `logs["train_accuracy"]` | - |
| update_time | - | `tracker.update_s` |

#### Fallback: 로그 파싱

직접 접근이 어려운 프로젝트 (학습 루프를 수정할 수 없는 경우)를 위해
`server.enable_log_interceptor()` 로 기존 로그 파싱 방식도 fallback으로 제공합니다.

### 3.5 상태 관리

```python
# 자동 관리: on_train 진입시 TRAINING, 완료시 IDLE, 에러시 ERROR
# 수동 오버라이드도 가능
server.state  # "idle" | "training" | "inference" | "error"
```

### 3.6 체크포인트/모델 목록

```python
@server.on_checkpoint_list
def handle_checkpoint_list() -> list[dict]:
    """
    반환: [{"name": "checkpoint-100", "path": "/workspace/...", "step": 100}, ...]
    """
    return scan_checkpoints("/workspace/output")

# 기본 구현도 제공 (오버라이드 안하면 자동으로 workspace 스캔)
```

### 3.7 실행

`RobotClient`와 `RobotServiceServer`는 분리된 컴포넌트입니다.
사용자가 직접 초기화 순서와 메인 루프를 관리합니다.

```python
from robot_client import RobotClient, RobotServiceServer

robot = RobotClient("ffw_sg2_rev1")
server = RobotServiceServer(name="groot")
policy = None

# 핸들러 등록
@server.on_load_policy
def handle_load_policy(request):
    global policy
    policy = load_model(request.model_path)
    if request.task_instruction:
        robot.set_task_instruction(request.task_instruction)
    return {"success": True}

@server.on_get_action
def handle_get_action(request):
    if request.task_instruction:
        robot.set_task_instruction(request.task_instruction)
    obs = robot.get_observation()
    action, info = policy.get_action(obs)
    return {"action_chunk": action, "chunk_size": 16}

@server.on_stop
def handle_stop():
    global policy
    policy = None
    return {"success": True}

# 사용자가 직접 시작 순서 관리
robot.wait_for_ready(timeout=10.0)   # 센서 수신 대기
server.start()                        # 서비스 등록 + progress publisher 시작

# 메인 루프: 프로세스를 살려두는 역할
# Zenoh 서비스는 백그라운드 스레드에서 요청을 처리하므로,
# 이 루프가 없으면 프로세스가 바로 종료됩니다.
# 실제 inference/training 처리는 서비스 콜백에서 자동으로 수행됩니다.
try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    server.stop()
    robot.close()
```

`server.start()` 내부:
1. Zenoh 연결
2. 등록된 핸들러들을 서비스로 등록
3. Progress publisher 시작

`server.stop()` 내부:
1. Progress publisher 중지
2. 서비스 해제
3. Zenoh 연결 해제

이렇게 분리하면 **server 없이 robot만 쓰는 것도 가능**합니다:
```python
# standalone 스크립트 (서비스 없이 직접 사용)
robot = RobotClient("ffw_sg2_rev1")
robot.wait_for_ready()

policy = load_model("my_model")
robot.set_task_instruction("pick up the cup")

while True:
    obs = robot.get_observation()
    action, info = policy.get_action(obs)
    robot.set_joint_positions("leader_arm_left", action["left_arm"])
```

---

## 4. 전체 executor 비교 (Before vs After)

### 4.1 GR00T Executor

**Before** (1,429줄):
```
Zenoh 연결/설정                 ~80줄
ExecutorState, TrainingProgress ~60줄
서비스 등록/핸들링               ~150줄
이미지/조인트 구독+콜백          ~80줄
Progress 발행                   ~90줄
상태 관리                        ~50줄
Stop/Status 핸들러              ~40줄
Lifecycle (start/stop/main)     ~50줄
────────────────────────────────────
인프라 합계                     ~600줄 (→ 0줄)

모델 로딩 (embodiment)          ~100줄
학습 설정 + 실행                ~160줄
추론 설정 + 실행                ~200줄
체크포인트 관리                  ~80줄
Observation 조립                ~60줄
TensorRT 적용                   ~30줄
────────────────────────────────────
고유 로직 합계                  ~630줄

기타 (dataclass, enum, import)  ~200줄
```

**After** (~250줄 예상):
```python
from robot_client import RobotClient, RobotServiceServer
from transformers import TrainerCallback

robot = RobotClient("ffw_sg2_rev1")
server = RobotServiceServer(name="groot")
policy = None

def load_groot_policy(model_path, embodiment_tag, trt_engine=None):
    """GR00T 모델 로딩 + TensorRT 최적화
    TensorRT는 DiT (Diffusion Transformer, 1.09B params) 부분만 대체합니다.
    Eagle vision backbone과 tokenizer 등은 PyTorch 그대로 사용.
    NVIDIA 공식 가이드(standalone_inference_script.py)도 동일한 방식입니다.
    """
    policy = Gr00tPolicy(...)
    if trt_engine:
        replace_dit_with_tensorrt(policy, trt_engine)
    return policy

def prepare_observation(robot, policy):
    """RobotClient 데이터 → GR00T observation 포맷 변환"""
    images = robot.get_images(resize=(256, 256), format="rgb")
    joints = robot.get_joint_positions()
    mc = policy.get_modality_config()
    # ... modality key 매핑 (~30줄)
    return obs


# ProgressCallback은 모듈 레벨에 정의 (함수 안에 클래스를 넣지 않음)
class GrootProgressCallback(TrainerCallback):
    def __init__(self, server):
        self.server = server

    def on_log(self, args, state, control, logs=None, **kwargs):
        self.server.report_progress(
            step=state.global_step, total_steps=state.max_steps,
            loss=logs.get("loss", 0), learning_rate=logs.get("learning_rate", 0),
        )


@server.on_train
def handle_train(request):
    extra = request.extra_params
    config = get_default_config(extra.get("embodiment_tag", "gr1"))
    # ... config 설정 (~40줄)

    trainer = Gr00tTrainer(model=model, args=args, ...)
    trainer.add_callback(GrootProgressCallback(server))
    trainer.train()
    return {"success": True}

@server.on_load_policy
def handle_load_policy(request):
    global policy
    extra = request.extra_params
    policy = load_groot_policy(
        request.model_path,
        extra.get("embodiment_tag", "gr1"),
        trt_engine=extra.get("trt_engine_path"),
    )
    if request.task_instruction:
        robot.set_task_instruction(request.task_instruction)
    return {"success": True, "action_keys": ...}

@server.on_get_action
def handle_get_action(request):
    if request.task_instruction:
        robot.set_task_instruction(request.task_instruction)
    obs = prepare_observation(robot, policy)
    action, info = policy.get_action(obs)
    return flatten_action(action)

@server.on_checkpoint_list
def handle_checkpoint_list():
    return scan_groot_checkpoints("/workspace/output")

robot.wait_for_ready(timeout=10.0)
server.start()

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    server.stop()
    robot.close()
```

### 4.2 새로운 프로젝트 추가 시

```python
# 예: OpenPI 통합 시
from robot_client import RobotClient, RobotServiceServer

robot = RobotClient("ffw_sg2_rev1")
server = RobotServiceServer(name="openpi")
policy = None

@server.on_load_policy
def handle_load_policy(request):
    global policy
    policy = load_openpi_model(request.model_path)
    if request.task_instruction:
        robot.set_task_instruction(request.task_instruction)
    return {"success": True}

@server.on_get_action
def handle_get_action(request):
    if request.task_instruction:
        robot.set_task_instruction(request.task_instruction)
    images = robot.get_images(resize=(224, 224), format="rgb")
    joints = robot.get_joint_positions()
    action = policy.predict(images, joints, robot.task_instruction)
    return {"action_chunk": action}

robot.wait_for_ready()
server.start()

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    server.stop()
    robot.close()
```

**새 프로젝트: ~50줄 (inference만 지원하는 경우)**

> 마이그레이션 Phase 5에서 새 프로젝트 추가용 **가이드 문서 + 템플릿**을 작성합니다.
> train/inference 모두 포함한 완전한 예시를 제공하여,
> AI Agent나 일반 개발자가 동일한 구조로 새 프로젝트를 생성할 수 있도록 합니다.

---

## 5. 내부 구현 상세

### 5.1 RobotClient 내부 구조

```python
class RobotClient:
    def __init__(self, robot_type: str, zenoh_config: dict = None,
                 sync_check: bool = False, sync_threshold_ms: float = 33):
        self._config = load_robot_config(robot_type)
        self._zenoh_session = create_zenoh_session(zenoh_config)
        self._sync_check = sync_check
        self._sync_threshold_ms = sync_threshold_ms

        # 최신 데이터 저장소 (thread-safe)
        self._images: dict[str, np.ndarray] = {}           # BGR 원본
        self._image_timestamps: dict[str, float] = {}
        self._joint_positions: dict[str, np.ndarray] = {}  # float32
        self._joint_timestamps: dict[str, float] = {}
        self._sensors: dict[str, dict] = {}                # odom 등
        self._task_instruction: str = ""
        self._lock = threading.Lock()

        # 액션 출력용 publisher (leader 그룹만)
        self._publishers: dict[str, ROS2Publisher] = {}

        # 구독/발행 초기화
        self._subscribers: list[ROS2Subscriber] = []
        self._init_subscriptions()
        self._init_publishers()

    def _init_subscriptions(self):
        """설정 파일 기반으로 모든 토픽 자동 구독"""
        for cam_name, cam_config in self._config["cameras"].items():
            sub = ROS2Subscriber(
                topic=cam_config["topic"],
                msg_type=cam_config["msg_type"],
                callback=lambda msg, name=cam_name: self._update_image(name, msg),
            )
            self._subscribers.append(sub)

        for group_name, group_config in self._config["joint_groups"].items():
            sub = ROS2Subscriber(
                topic=group_config["topic"],
                msg_type=group_config["msg_type"],
                callback=lambda msg, name=group_name: self._update_joint(name, msg),
            )
            self._subscribers.append(sub)

        for sensor_name, sensor_config in self._config.get("sensors", {}).items():
            sub = ROS2Subscriber(
                topic=sensor_config["topic"],
                msg_type=sensor_config["msg_type"],
                callback=lambda msg, name=sensor_name: self._update_sensor(name, msg),
            )
            self._subscribers.append(sub)

    def _init_publishers(self):
        """leader 그룹에 대해 publisher 생성 (follower 제외)"""
        for group_name, group_config in self._config["joint_groups"].items():
            if group_config.get("role") == "leader":
                self._publishers[group_name] = ROS2Publisher(
                    topic=group_config["topic"],
                    msg_type="sensor_msgs/msg/JointState",
                )

    def _update_image(self, cam_name: str, msg):
        """CompressedImage → numpy array (BGR, 원본 사이즈) 변환 후 저장"""
        buf = np.frombuffer(msg.data, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)  # BGR
        with self._lock:
            self._images[cam_name] = img
            self._image_timestamps[cam_name] = time.time()

    def _update_joint(self, group_name: str, msg):
        """JointState → np.ndarray(float32) 변환 후 저장"""
        with self._lock:
            self._joint_positions[group_name] = np.array(msg.position, dtype=np.float32)
            self._joint_timestamps[group_name] = time.time()

    def get_images(self, resize=None, format="bgr") -> dict[str, np.ndarray]:
        with self._lock:
            result = dict(self._images)
        if resize:
            result = {k: cv2.resize(v, tuple(resize)) for k, v in result.items()}
        if format == "rgb":
            result = {k: cv2.cvtColor(v, cv2.COLOR_BGR2RGB) for k, v in result.items()}
        return result

    def get_joint_positions(self, group: str = None):
        with self._lock:
            if group:
                return self._joint_positions.get(group, np.array([], dtype=np.float32)).copy()
            return {k: v.copy() for k, v in self._joint_positions.items()}

    def set_task_instruction(self, instruction: str):
        self._task_instruction = instruction

    @property
    def task_instruction(self) -> str:
        return self._task_instruction

    def set_joint_positions(self, group_or_dict, positions=None):
        """leader 그룹에 JointState 발행. follower는 warning."""
        if isinstance(group_or_dict, dict):
            for group, pos in group_or_dict.items():
                self.set_joint_positions(group, pos)
            return
        group = group_or_dict
        config = self._config["joint_groups"].get(group, {})
        if config.get("role") == "follower":
            logging.warning(f"Cannot set positions for follower group: {group}")
            return
        if group in self._publishers:
            self._publishers[group].publish(build_joint_state_msg(config, positions))

    def get_observation(self):
        """inference용 전체 observation 반환"""
        if self._sync_check:
            if not self._check_sync():
                return None
        return {
            "images": self.get_images(),
            "joint_positions": self.get_joint_positions(),
            "task_instruction": self._task_instruction,
        }

    def close(self):
        for sub in self._subscribers:
            sub.close()
        for pub in self._publishers.values():
            pub.close()
```

### 5.2 RobotServiceServer 내부 구조

```python
class RobotServiceServer:
    def __init__(self, name: str):
        self._name = name
        self._state = "idle"
        self._progress = TrainingProgress()
        self._handlers = {}
        self._zenoh_session = None
        self._services = {}
        self._progress_publisher = None
        self._running = False

    # --- 데코레이터: 핸들러 등록 ---

    def on_train(self, func):
        self._handlers["train"] = func
        return func

    def on_infer(self, func):
        self._handlers["infer"] = func
        return func

    def on_get_action(self, func):
        self._handlers["get_action"] = func
        return func

    def on_stop(self, func):
        self._handlers["stop"] = func
        return func

    def on_checkpoint_list(self, func):
        self._handlers["checkpoint_list"] = func
        return func

    # --- Progress 보고 ---

    def report_progress(self, **kwargs):
        """학습 progress 업데이트 + 발행 (thread-safe)"""
        for k, v in kwargs.items():
            setattr(self._progress, k, v)
        if self._progress_publisher:
            self._publish_progress()

    def enable_log_interceptor(self, patterns=None):
        """Fallback: 로그 파싱으로 progress 추출 (직접 접근이 안 되는 경우)"""
        self._setup_logging_interceptor(patterns)

    # --- 서비스 요청 처리 (내부) ---

    def _handle_service_request(self, service_name, raw_request):
        """서비스 요청을 dict로 변환 후 핸들러 호출"""
        request = self._parse_request(raw_request)
        # extra_params_json → dict 자동 변환
        if hasattr(request, "extra_params_json") and request.extra_params_json:
            request.extra_params = json.loads(request.extra_params_json)
        else:
            request.extra_params = {}

        handler = self._handlers.get(service_name)
        if handler:
            # 상태 자동 전환
            if service_name == "train":
                self._state = "training"
            elif service_name == "infer":
                self._state = "inference"

            try:
                result = handler(request)
            except Exception as e:
                self._state = "error"
                return {"success": False, "message": str(e)}

            if service_name in ("train",) and result.get("success"):
                self._state = "idle"
            return result

    # --- Lifecycle ---

    def start(self):
        """서비스 등록 + progress publisher 시작"""
        self._zenoh_session = create_zenoh_session()
        self._register_services()
        self._start_progress_publisher()
        self._running = True

    def stop(self):
        """서비스 해제 + progress publisher 중지"""
        self._running = False
        self._stop_progress_publisher()
        self._unregister_services()
        if self._zenoh_session:
            self._zenoh_session.close()

    @property
    def state(self):
        return self._state
```

---

## 6. 고려사항 및 질문

### 해결된 항목

| 항목 | 결정 | 근거 |
|------|------|------|
| 이미지 포맷 | BGR 기본, `format="rgb"` 파라미터로 선택 | GR00T가 BGR 사용, OpenCV 관례와 일치 |
| 이미지 리사이즈 | 기본 원본 사이즈, `resize=(W,H)` 파라미터로 선택 | 기본 리사이즈는 부자연스러움 |
| 조인트 반환 타입 | `np.ndarray` (float32) | GR00T가 np.ndarray(dtype=float32) 사용 |
| leader/follower 구분 | 유지 | 설정 파일에 `role` 필드로 구분 |
| gripper | position에 포함 | joint_names 마지막 원소로 포함 |
| 액션 발행 | 직접 발행 + 서비스 방식 모두 지원 | standalone 사용과 async inference 모두 대응 |
| 액션 메시지 타입 | JointState (JointTrajectory 아님) | 기존 구현 확인 결과 |
| follower set | 읽기 전용, warning 출력 | follower에 set해도 동작 안함 |
| timestamp in obs | 제외 | 모델 입력에 사용 안됨 |
| task_instruction | `set_task_instruction()` API로 분리, get_action마다 변경 가능 | multi-task 시나리오 지원 |
| 동기화 체크 | 선택적 (`sync_check=True`, 33ms threshold) | 개발 시 편의 vs 실제 inference 품질 |
| 커스텀 메시지 | `robot_client/messages/`로 분리 | zenoh_ros2_sdk는 범용 라이브러리로 유지 |
| 학습 파라미터 | 공통 필드 + `extra_params_json` (JSON → dict) | 모델마다 파라미터가 다름, 기존 JSON 패턴 활용 |
| topic_map in infer | 제거 | RobotClient가 로봇 타입 기반으로 자동 구독 |
| progress 보고 | 직접 접근 권장 (TrainerCallback/MetricsTracker), 로그 파싱은 fallback | 직접 접근이 정확하고 안정적 |
| run_forever() | 제거, `start()`/`stop()`으로 분리 | 사용자가 직접 조합하는 구조가 유연함 |
| RobotClient 분리 | server와 별도 생성 | server 없이 robot만 사용 가능 (standalone) |

### 추가 해결된 항목 (코멘트3)

| 항목 | 결정 | 근거 |
|------|------|------|
| 조인트 그룹 key 네이밍 | RobotClient는 설정 파일 key 사용, modality key 매핑은 executor에서 | modality key는 GR00T 고유 명칭이며 나중에 우리에 맞게 수정 가능 |
| 패키지 위치 | `third_party/robot_client/` (옵션 A) | 독립 패키지, 나중에 별도 repo로 분리 |
| 설정 파일 | physical_ai_server 설정 공유 (옵션 B, 심링크/마운트) | 설정 중복 방지 |
| 동적 토픽 매핑 | 초기화 시 설정 파일로만 구독 (옵션 A) | 토픽 추가는 config 파일 수정으로 유도 |
| 다중 executor | 하나의 inference만 사용, 센서 데이터도 단일 구독 | active executor만 구독 활성화, 나머지는 대기 |
| 에러 처리 | 빈 dict 반환 + warning 로그, 프로세스는 죽지 않음, `wait_for_ready()`로 대기 가능 | 안정성 우선 |
| handle_infer 네이밍 | `on_load_policy` / `handle_load_policy`로 변경 | 실제 역할에 맞는 이름 |
| 내부 메서드 네이밍 | `_init_subscriptions`, `_init_publishers`, `_update_image`, `_update_joint` | 역할에 맞는 명확한 이름 |
| build_observation | `prepare_observation`으로 변경 | "build"보다 "prepare"가 적절 |
| ProgressCB | 모듈 레벨로 추출 (함수 안에 클래스 정의하지 않음) | 코드 가독성 |
| Leader read/write 토픽 | 현재는 동일, 설정 파일에 `write_topic` 분리 가능한 구조 | leader는 읽기/쓰기 토픽이 다를 수 있음 |
| Action chunk 발행 | 내부 10Hz 타이머로 1개씩 pop하여 JointState 발행 (현재), 향후 JointTrajectory로 전환 가능 | 기존 구조 유지 |
| observation 항목 | images + joints + task_instruction 3가지 (추가 항목 없음) | GR00T, LeRobot 모두 동일 |

### 미해결 질문

(모든 주요 설계 질문이 해결되었습니다. 구현 과정에서 추가 질문이 발생하면 업데이트합니다.)

---

## 7. 마이그레이션 계획

### Phase 1: robot_client 패키지 구현
1. RobotClient (센서 읽기) 구현
2. 설정 파일 포맷 정의
3. 단위 테스트

### Phase 2: RobotServiceServer 구현
1. 서비스 프레임워크 구현
2. 데코레이터 패턴 구현
3. Progress 발행 로직

### Phase 3: GR00T executor 마이그레이션
1. 기존 executor.py → 신규 구조로 전환
2. 기존 기능 동일하게 동작하는지 검증

### Phase 4: LeRobot executor 마이그레이션
1. 동일하게 전환

### Phase 5: 문서화 + 템플릿
1. 새 프로젝트 추가용 **템플릿 executor** 작성 (train + inference 완전한 예시)
2. **개발자 가이드 문서**: AI Agent 및 일반 개발자가 동일한 구조로 새 프로젝트를 생성할 수 있도록

### Phase 6: physical_ai_server 리팩토링 (최종 단계)
1. robot_client 완성 후, physical_ai_server에서 불필요한 부분 제거
2. physical_ai_server는 현재 직접 센서 토픽을 Subscribe하고 있지만,
   robot_client 도입 후에는 각 executor가 직접 데이터를 처리하므로 불필요
3. physical_ai_server의 역할 축소: rosbag 녹화, 서비스 라우팅, UI 연동 등으로 한정
4. 모든 Phase 1-5가 완료되고 테스트가 검증된 후에 진행

---

## 8. 변경 사항 없는 것들

- **zenoh_ros2_sdk**: 수정 없음
- **physical_ai_interfaces**: 수정 없음 (메시지/서비스 정의 동일)
- **physical_ai_server**: Phase 1-5 동안은 수정 없음 (Phase 6에서 리팩토링)
- **Docker 구조**: robot_client를 추가 마운트만 필요
  ```yaml
  # docker-compose.yml에 추가
  - ../third_party/robot_client:/robot_client:ro
  ```

---

## 9. 구현 및 테스트 기록

### 9.1 Phase 1 구현: robot_client 패키지

#### 9.1.1 패키지 구조

```
third_party/robot_client/
├── robot_client/
│   ├── __init__.py              # RobotClient, RobotServiceServer export
│   ├── robot_client.py          # 센서 읽기 + 액션 출력 (약 430줄)
│   ├── service_server.py        # 서비스 프레임워크 (약 400줄)
│   ├── config/
│   │   └── ffw_sg2_rev1.yaml    # 실제 rosbag 토픽 기반 설정
│   └── messages/
│       ├── __init__.py
│       ├── msg/
│       └── srv/
└── tests/
    └── test_rosbag_subscriber.py
```

#### 9.1.2 구현된 API

**RobotClient:**
- `__init__(robot_type, sync_check, sync_threshold_ms, router_ip, router_port, domain_id)` - domain_id 추가됨 (아래 디버깅 기록 참고)
- `get_images(resize, format)` - BGR/RGB, 원본/리사이즈
- `get_image(camera_name, resize, format)` - 단일 카메라
- `get_joint_positions(group)` - 전체/개별 그룹
- `get_joint_velocities(group)`, `get_joint_efforts(group)`
- `get_odom()` - Odometry 센서
- `set_task_instruction(text)`, `task_instruction` property
- `set_joint_positions(group_or_dict, positions)` - leader 그룹만
- `set_velocity(linear_x, linear_y, angular_z)` - cmd_vel
- `execute_action_chunk(chunk, action_keys, frequency)` - 10Hz 타이머
- `get_observation(resize, format)` - inference용 전체 observation
- `wait_for_ready(timeout)`, `wait_for_image()`, `wait_for_joint()`
- `get_status()` - 전체 구독 상태 확인
- `close()` - 정리

**RobotServiceServer:**
- `on_train`, `on_load_policy`, `on_get_action`, `on_stop`, `on_checkpoint_list` 데코레이터
- `report_progress(**kwargs)` - 학습 progress 발행
- `start()` / `stop()` - 서비스 등록/해제
- `state` property - idle/training/inference/error
- `enable_log_interceptor()` - fallback 로그 파싱

**구현 중 설계 변경:**
1. `domain_id` 파라미터 추가 - ROS_DOMAIN_ID 환경변수와 별도로 명시적 지정 가능 (디버깅 중 필요성 확인됨)
2. `set_joint_positions` publish 방식 - zenoh_ros2_sdk의 `publish(**kwargs)` API 사용
3. `_update_image`에서 `msg.data`가 list일 수 있어 `bytes()` 변환 추가

#### 9.1.3 설정 파일 (ffw_sg2_rev1.yaml)

실제 rosbag (`/workspace/test_dataset/metadata.yaml`)에서 확인한 토픽으로 생성:
- **카메라 4개**: cam_left_head (720×1280), cam_right_head (720×1280), cam_left_wrist (480×640), cam_right_wrist (480×640)
- **조인트 그룹 8개**: leader/follower × arm_left(8DOF), arm_right(8DOF), head(2DOF), lift(1DOF)
- **센서 2개**: odom (/odom, Odometry), cmd_vel (/cmd_vel, Twist)
- **rosbag 추가 토픽**: /tf, CameraInfo 4개

#### 9.1.4 의존성 및 환경 요구사항

**Python 패키지 (groot/lerobot 컨테이너 모두에 이미 설치됨):**
- `numpy` (2.2.6) - 배열 처리
- `opencv-python` (`cv2` 4.11.0) - 이미지 디코딩/변환
- `pyyaml` (6.0.3) - YAML 설정 파일
- `zenoh_ros2_sdk` (0.1.5) - Zenoh/ROS2 통신 (이미 `/zenoh_sdk`에 마운트)

**Docker 변경 사항 (향후 docker-compose.yml 추가):**
```yaml
# groot, lerobot 서비스에 추가:
volumes:
  - ../third_party/robot_client:/robot_client:ro

# 환경변수에 추가:
environment:
  - PYTHONPATH=/robot_client:${PYTHONPATH}
  # 또는 robot_client 내부에서 ZENOH_SDK_PATH 환경변수 사용
```

**현재 테스트에서는 `docker cp`로 `/workspace/robot_client`에 복사 후 테스트함.**

### 9.2 테스트 결과

#### 9.2.1 테스트 환경

```
Host: Jetson AGX Orin (Linux 5.15.148-tegra, aarch64)
Docker: 4 containers (host network, ipc: host)

physical_ai_server (ROS2 Jazzy + rmw_zenoh_cpp)
  └─ ros2 bag play /workspace/test_dataset --rate 1.0 --loop
      └─ 19 topics, 98,720 messages, 75초 rosbag

groot_server (zenoh_ros2_sdk, peer mode)
  └─ robot_client test subscriber

lerobot_server (zenoh_ros2_sdk, peer mode)
  └─ robot_client test subscriber
```

#### 9.2.2 데이터 수신 결과

| 센서 | groot_server | lerobot_server | 예상 | 비고 |
|------|-------------|----------------|------|------|
| cam_left_head (720×1280) | 15.0 Hz ✅ | 15.0 Hz ✅ | 15 Hz | |
| cam_right_head (720×1280) | 15.0 Hz ✅ | 15.0 Hz ✅ | 15 Hz | |
| cam_left_wrist (480×640) | 15.0 Hz ✅ | 15.0 Hz ✅ | 15 Hz | |
| cam_right_wrist (480×640) | 15.0 Hz ✅ | 15.0 Hz ✅ | 15 Hz | |
| leader_arm_left (8DOF) | 100.0 Hz ✅ | 99.8 Hz ✅ | 100 Hz | |
| leader_arm_right (8DOF) | 100.0 Hz ✅ | 100.0 Hz ✅ | 100 Hz | |
| follower_arm_left (8DOF) | 100.0 Hz ✅ | 100.0 Hz ✅ | 100 Hz | |
| follower_arm_right (8DOF) | 100.0 Hz ✅ | 100.0 Hz ✅ | 100 Hz | |
| leader_head (2DOF) | 100.0 Hz ✅ | 100.0 Hz ✅ | 100 Hz | 값은 NaN (로봇에서 미구현) |
| follower_head (2DOF) | 100.0 Hz ✅ | 100.0 Hz ✅ | 100 Hz | |
| leader_lift (1DOF) | 100.0 Hz ✅ | 100.0 Hz ✅ | 100 Hz | 값은 NaN (로봇에서 미구현) |
| follower_lift (1DOF) | 100.0 Hz ✅ | 100.0 Hz ✅ | 100 Hz | |
| odom | ❌ | ❌ | 100 Hz | type hash 불일치 (아래 참고) |
| cmd_vel | ✅ | ✅ | 100 Hz | |

#### 9.2.3 레이턴시 측정 결과

| API | groot_server | lerobot_server | 비고 |
|-----|-------------|----------------|------|
| `get_observation()` | 2.79ms avg (P95: 4.4ms) | 2.42ms avg (P95: 3.7ms) | lock + copy |
| `get_images(256,rgb)` | 8.20ms avg (P95: 9.5ms) | 8.16ms avg (P95: 9.4ms) | resize + cvtColor 포함 |
| `get_joint_positions()` | 0.005ms avg | 0.004ms avg | 매우 빠름 (copy만) |

**데이터 신선도 (Data Freshness):**
- 카메라: 7~14ms (마지막 수신 시점과 현재 시점 차이)
- 조인트: 5~6ms

**평가:**
- `get_observation()`: 2~3ms이므로 inference 루프에 무시할 수 있는 수준
- `get_images(resize=256, rgb)`: 8ms - 4개 이미지의 리사이즈+BGR→RGB 변환. GR00T inference (171ms)에 비하면 ~5%
- 조인트 읽기: 0.005ms - 사실상 zero overhead

### 9.3 디버깅 기록

#### 9.3.1 데이터 미수신 문제 (Critical)

**증상:** 첫 테스트에서 모든 센서 데이터 미수신 (0 messages)

**디버깅 과정:**

1. **Raw zenoh 테스트**: zenoh Python SDK로 직접 `0/**`에 subscribe → **6,580 messages/5s 수신 성공**
   - zenoh 연결 자체는 정상

2. **Liveliness 토큰 확인**: `@ros2_lv/**` 쿼리 → **81개 토큰 발견**
   - rosbag player의 publisher 토큰 모두 확인

3. **Key expression 비교**:
   - rmw_zenoh 실제 데이터: `0/robot/arm_left_follower/joint_states/sensor_msgs::msg::dds_::JointState_/RIHS01_...`
   - zenoh_ros2_sdk 생성: `0/robot/arm_left_follower/joint_states/sensor_msgs::msg::dds_::JointState_/RIHS01_...`
   - **type hash 일치 확인!**

4. **Domain ID 확인**: ← **근본 원인 발견**
   - groot 컨테이너: `ROS_DOMAIN_ID=30`
   - physical_ai_server: `ROS_DOMAIN_ID=` (기본값 0)
   - zenoh_ros2_sdk는 `resolve_domain_id()`로 환경변수에서 domain_id를 읽음
   - groot의 subscriber가 `30/robot/...`으로 구독하지만 데이터는 `0/robot/...`에 존재

**해결:**
- RobotClient에 `domain_id` 파라미터 추가
- `domain_id=0` 명시 지정으로 해결
- `domain_id`를 subscriber/publisher 생성 시 전달

**향후 조치:**
- groot, lerobot 컨테이너의 `ROS_DOMAIN_ID`를 physical_ai_server와 동일하게 맞춰야 함
- 또는 robot_client config에 domain_id를 포함하여 명시적 관리

#### 9.3.2 ZENOH_CONFIG_OVERRIDE에 connect/endpoints=[] 포함 문제

**발견:** groot 컨테이너의 실제 `ZENOH_CONFIG_OVERRIDE`에 `connect/endpoints=[]`가 포함되어 있었음.
이것은 ZenohSession이 기본 설정하는 `tcp/127.0.0.1:7447` 엔드포인트를 덮어씌움.

**결과:** peer 모드에서 multicast scouting에만 의존하게 됨.
현재 환경에서는 multicast로 rmw_zenoh router를 발견하고 있어 동작은 하고 있음.

**근본 원인:** `session.py`에서 `connect/endpoints`를 먼저 설정한 후 `mode="peer"` override를 적용하면
Zenoh 내부적으로 endpoints가 초기화됨 (ordering 문제).

**수정 완료:** `session.py`에서 override를 먼저 적용하고, override에 `connect/endpoints`가 명시되지 않은 경우에만
기본값 `["tcp/{router_ip}:{router_port}"]`을 설정하도록 변경함.

**Zenoh 네트워킹 모드 참고:**

| 모드 | 역할 | 독립 실행 | Scouting | Router 연결 |
|------|------|----------|----------|------------|
| **Router** | 중앙 허브, TCP 포트 열고 대기, 메시지 라우팅 | O | X | 본인이 router |
| **Client** | router에 명시적 연결, router 없으면 동작 불가 | X | X | 필수 |
| **Peer** | 다른 peer를 자동 발견(multicast), router에도 연결 가능 | O | O | 선택 |

- **Multicast scouting**: 같은 LAN에 UDP broadcast → 주변 노드 자동 발견. `network_mode: host`라 동작함.
- **Gossip scouting**: router를 통해 다른 peer의 존재를 간접 전파.
- **connect/endpoints**: 즉시 TCP 연결할 대상 주소. 빈 리스트면 직접 연결 안함.

**현재 최적 설정 (docker-compose.yml과 동일):**
```
ZENOH_CONFIG_OVERRIDE=mode="peer";scouting/multicast/enabled=true;scouting/gossip/enabled=true
```
→ connect/endpoints는 session.py 기본값 유지 = direct connect + multicast + gossip 삼중 보험

#### 9.3.3 nav_msgs/msg/Odometry type hash 불일치

**증상:** odom 토픽 구독 실패 (다른 모든 토픽은 정상)

**원인:** zenoh_ros2_sdk의 메시지 레지스트리에서 다운로드한 `nav_msgs/msg/Odometry` 정의와
physical_ai_server의 ROS2 Jazzy에 설치된 정의의 type hash가 다름.

```
SDK type_hash:  RIHS01_1d144a31ec3ed540ca6338af79976a3a...
실제 type_hash: RIHS01_3cc97dc7fb7502f8714462c526d369e35b...
```

**영향:** odom 토픽만 미수신. 카메라(CompressedImage), 조인트(JointState), cmd_vel(Twist)은 정상.

**향후 조치:** zenoh_ros2_sdk의 메시지 레지스트리가 사용하는 메시지 정의를
ROS2 Jazzy의 정의와 동기화 필요. 이것은 zenoh_ros2_sdk 이슈로 별도 추적.

#### 9.3.4 leader_head, leader_lift 값이 NaN

**증상:** `leader_head: dof=2, values=[nan, nan]`, `leader_lift: dof=1, values=[nan]`

**원인:** 로봇 하드웨어에서 leader head/lift이 아직 미구현 또는 미연결 상태.
follower_head, follower_lift은 정상 값 수신.

**영향:** 없음 (데이터 문제, robot_client 문제 아님)

### 9.4 Zenoh Shared Memory (SHM) 설정

#### 구성 요소 및 상태:

| 항목 | 상태 | 비고 |
|------|------|------|
| /dev/shm 마운트 | ✅ | 모든 컨테이너에 마운트됨 (31GB) |
| /tmp 마운트 | ✅ | 모든 컨테이너에 마운트됨 (SHM negotiation 필수) |
| ipc: host | ✅ | 같은 IPC namespace 공유 |
| ZENOH_SHM_ENABLED=true | ✅ | groot, lerobot의 zenoh_ros2_sdk에서 사용 |
| rmw_zenoh SHM config | ✅ | router/session 모두 `shared_memory.enabled: true` |
| transport_optimization | ✅ | threshold 3072 bytes (이상이면 SHM으로 전송) |
| session.py SHM 자동 활성화 | ✅ | `ZENOH_SHM_ENABLED=true` 환경변수로 zenoh config에 자동 적용 |

#### SHM 동작 원리:

Zenoh SHM은 같은 호스트 내 프로세스 간 zero-copy 데이터 전송을 지원합니다.

**SHM 데이터 흐름:**
```
physical_ai_server (rmw_zenoh_cpp) → Zenoh SHM (/dev/shm) → groot/lerobot (zenoh_ros2_sdk)
```

1. Publisher가 메시지를 `/dev/shm`의 공유 메모리 버퍼에 씀
2. Zenoh는 64바이트 SHM reference만 네트워크로 전송
3. Subscriber가 reference를 받아 `/dev/shm`에서 직접 데이터를 읽음 (zero-copy)
4. `transport_optimization` threshold (기본 3072 bytes) 이상인 메시지만 SHM 경로 사용

**필수 조건 (3가지 모두 충족해야 SHM 동작):**
1. `/dev/shm:/dev/shm` - 실제 공유 메모리 영역
2. `/tmp:/tmp` - SHM negotiation 파일 교환 (critical - 이것 없으면 대용량 메시지 전송 실패)
3. `ipc: host` - 동일 IPC namespace

#### 디버깅 기록: SHM 설정 과정에서의 문제와 해결

**문제 1: sed로 rmw_zenoh config 일괄 변경 사고**
- rmw_zenoh의 `DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5`에서 SHM을 활성화하려 했음
- `sed -i 's/enabled: false,/enabled: true,/'` 명령으로 파일 내 모든 `enabled: false,`가 변경됨
- multicast scouting, gossip scouting 등 관련 없는 설정까지 true로 변경
- 부분적으로 revert 후 최종적으로 SHM만 true인 상태 확인

**문제 2: /tmp 미공유로 CompressedImage, Odometry 수신 실패**
- SHM 활성화 후 JointState(~200B)만 수신되고, CompressedImage(~165KB)와 Odometry가 수신 안됨
- 원인: `/tmp`이 컨테이너 간 공유되지 않아 SHM negotiation 실패
- SHM threshold(3072B) 이상인 메시지는 SHM 경로로 전송되지만, subscriber가 SHM에 접근 불가
- JointState는 threshold 이하라 일반 네트워크로 전송되어 정상 수신
- **해결: `docker-compose.yml`에 `/tmp:/tmp` 볼륨 마운트 추가 (모든 3개 컨테이너)**

**문제 3: zenoh_ros2_sdk에서 SHM 자동 활성화 필요**
- lerobot/groot 컨테이너의 zenoh_ros2_sdk는 별도로 SHM을 활성화해야 함
- `session.py`에 `ZENOH_SHM_ENABLED` 환경변수 기반 자동 활성화 코드 추가:
  ```python
  shm_enabled = os.environ.get("ZENOH_SHM_ENABLED", "").lower() == "true"
  if shm_enabled and not override_has_shm:
      self.conf.insert_json5("transport/shared_memory/enabled", "true")
  ```

#### SHM 검증 테스트 결과 (2026-02-17):

**테스트 환경:**
- physical_ai_server (ROS2 rmw_zenoh_cpp) ↔ lerobot_server (zenoh_ros2_sdk)
- Domain ID: 30, SHM: enabled, `/tmp:/tmp`: shared
- 데이터: rosbag replay (`/workspace/test_dataset`, ~75s, loop mode)

| Topic | Rate | Jitter | Avg Size | SHM Zero-Copy |
|-------|------|--------|----------|----------------|
| JointState (100Hz) | 100.6 Hz | 1.04 ms | ~200B | No (below 3072B threshold) |
| CompressedImage (15Hz) | 15.0 Hz | 4.15 ms | 166.4 KB | **YES** (100% via SHM) |
| Odometry (100Hz) | 100.1 Hz | 0.72 ms | ~700B | No (below 3072B threshold) |
| CameraInfo (15Hz) | 15.0 Hz | 4.26 ms | ~300B | No (below threshold) |

**결론:**
- CompressedImage(166KB)는 100% SHM zero-copy로 전송됨
- 이미지 jitter 4.15ms는 매우 안정적 (15Hz 기준 66.7ms interval)
- JointState/Odometry는 threshold 이하이므로 일반 네트워크 전송 (jitter <1.1ms)
- 4/4 토픽 모두 정상 수신 확인

### 9.5 환경/의존성 변경사항 요약 (Dockerfile 반영 필요)

#### docker-compose.yml 변경사항:

```yaml
# groot, lerobot 서비스의 volumes에 추가:
- ../third_party/robot_client:/robot_client:ro

# groot, lerobot 서비스의 environment에 추가:
- PYTHONPATH=/robot_client:${PYTHONPATH:-}
```

#### 새 파일 (이미 존재하는 의존성으로 추가 설치 불필요):

| 의존성 | groot | lerobot | 설치 필요 |
|--------|-------|---------|-----------|
| numpy | ✅ 2.2.6 | ✅ | 아니오 |
| opencv (cv2) | ✅ 4.11.0 | ✅ | 아니오 |
| pyyaml | ✅ 6.0.3 | ✅ | 아니오 |
| zenoh_ros2_sdk | ✅ /zenoh_sdk | ✅ /zenoh_sdk | 아니오 (마운트) |

**결론: 추가 패키지 설치 불필요. Docker 마운트와 PYTHONPATH 설정만 추가하면 됨.**

### 9.6 L2 Distance 기반 Chunk 정렬 분석

#### 9.6.1 문제 상황

모델은 한 번의 추론에서 action chunk (예: 16 timestep × action_dim)를 출력합니다.
로봇은 10Hz로 하나씩 pop해서 실행하는데, 이전 chunk가 완전히 소진되기 전에
(혹은 직후에) 새 chunk가 도착할 수 있습니다.

새 chunk를 그대로 이어붙이면 불연속(discontinuity)이 발생합니다:
```
실행 순서: [..., a13, a14, a15, b0, b1, ...]
                                 ↑ 갑작스러운 점프 발생 가능
```

#### 9.6.2 정렬 알고리즘 (groot_inference_manager.py의 `_align_and_enqueue()`)

```python
distances = np.linalg.norm(chunk - self._last_action, axis=1)  # 각 timestep과의 유클리드 거리
start_idx = int(np.argmin(distances)) + 1                       # 가장 가까운 시점의 다음부터
chunk = chunk[start_idx:]                                       # 잘라서 사용
```

**동작 원리:**
1. 새 chunk의 모든 timestep에 대해 `last_action`과의 L2 (유클리드) 거리 계산
2. 거리가 최소인 timestep = "현재 로봇 상태와 가장 비슷한 시점"
3. 그 **다음** timestep부터 버퍼에 추가 (중복 실행 방지 + 부드러운 연결)

**예시:**
```
last_action: [0.5, 0.3, 0.7]
새 chunk B:
  b0: L2=0.72  (먼 과거)
  b1: L2=0.54
  b2: L2=0.31
  b3: L2=0.14
  b4: L2=0.01  ← 최소 (argmin=4)
  b5: ← start_idx=5, 여기부터 사용
  ...b15
결과: b5~b15만 버퍼에 추가 → a15 → b5 → b6 → ... (부드러운 전환)
```

#### 9.6.3 현재 RobotClient의 execute_action_chunk()에는 미구현

현재 구현은 새 chunk가 올 때 이전 chunk를 완전히 대체합니다 (`_stop_chunk_execution()` 호출 후 새 버퍼 설정).
실제 사용 시 L2 정렬 로직 추가가 필요합니다.

### 9.7 PyTorch 쓰레딩 제약 검토 (execute_action_chunk + 추론 동일 프로세스)

#### 9.7.1 검토 배경

`execute_action_chunk()`는 `threading.Timer`로 10Hz 타이머 쓰레드를 생성하여 액션을 발행합니다.
PyTorch 모델 추론이 같은 프로세스에서 실행될 때 쓰레딩 충돌이 발생하는지 검토했습니다.

#### 9.7.2 결론: **동작 가능 — PyTorch 쓰레딩 제약에 해당하지 않음**

**근거:**
1. **Timer 쓰레드는 CUDA를 전혀 사용하지 않음**: `_chunk_tick()`은 numpy pop + Zenoh publish만 수행
2. **GIL은 GPU 추론 중 해제됨**: PyTorch C++ 백엔드 진입 시 GIL 해제 → Timer 쓰레드 실행 가능
3. **CUDA context thread-safety**: Timer 쓰레드가 CUDA를 안 쓰므로 무관
4. **알려진 PyTorch 쓰레딩 버그 해당 없음**: cuDNN V8 버그, 동일 모델 멀티쓰레드 호출, torch.compile GIL 비해제 등 모두 해당 안됨

#### 9.7.3 실질적 우려사항

| 항목 | 영향 | 심각도 |
|------|------|--------|
| GIL contention (추론 전/후처리 중) | Timer tick 수 ms 지연 | 낮음 (10Hz = 100ms 간격) |
| threading.Timer 매 tick 새 쓰레드 생성 | 10Hz에서는 무시 가능 | 낮음 |
| torch.compile 사용 시 GIL 비해제 | Timer 블록 가능 | 현재 미사용 |

#### 9.7.4 방법 1-2 (직접 발행) vs 방법 2 (서비스 방식) 비교

| | 방법 2 (서비스 방식) | 방법 1-2 (직접 발행) |
|---|---|---|
| 추론 위치 | executor 서비스 핸들러 쓰레드 | 같은 프로세스 메인/추론 쓰레드 |
| 액션 발행 | physical_ai_server InferenceManager | RobotClient threading.Timer |
| L2 chunk 정렬 | InferenceManager가 수행 | **미구현 (추가 필요)** |
| PyTorch 충돌 | 없음 (프로세스 분리) | 없음 (Timer가 CUDA 미사용) |
| 장점 | 기존 인프라 그대로 사용 | 프로세스 간 통신 오버헤드 제거 |
| 단점 | 서비스 호출 레이턴시 | L2 정렬 추가 구현 필요 |

#### 9.7.5 결정사항 (코멘트5 반영)

- **비동기 추론**: 서비스 방식만 사용 (InferenceManager가 L2 정렬 + 10Hz pop 담당)
- **동기 제어**: `execute_action_chunk()` → 동기 blocking 호출로 변경 (threading.Timer 제거)
- L2 정렬(`_align_and_enqueue`)은 서비스 방식(InferenceManager)에서만 사용

**수정 완료:**
- `robot_client.py`의 `execute_action_chunk()`: threading.Timer 제거, 동기 for-loop + time.sleep으로 변경
- chunk_timer, chunk_lock, chunk_buffer 등 비동기 관련 상태 변수 모두 제거

### 9.8 코멘트5 반영 작업 결과

| 작업 | 상태 | 변경 파일 |
|------|------|----------|
| **ROS_DOMAIN_ID 30으로 통일** | ✅ 완료 | `docker-compose.yml` (server/lerobot/groot 모두 기본값 30), `robot_client.py` (기본값 30) |
| **connect/endpoints=[] 수정** | ✅ 완료 | `session.py` (override 먼저 적용 후 기본 endpoints 설정) |
| **odom type hash 수정** | ✅ 완료 | `utils.py` (`_parse_msg_definition()` fixed-size array `float64[36]` 파싱 버그 수정, `_field_type_to_type_id()`에 ARRAY vs UNBOUNDED_SEQUENCE 구분 추가) |
| **execute_action_chunk 동기화** | ✅ 완료 | `robot_client.py` (threading.Timer → 동기 for-loop) |
| **GR00T executor 모듈 분리** | ✅ 완료 | `executor.py` (공유 인프라 ~690줄), `training.py` (학습 ~280줄), `inference.py` (추론 ~370줄) |
| **docker-compose.yml 볼륨 업데이트** | ✅ 완료 | groot 컨테이너에 training.py, inference.py 마운트 추가 |

#### 9.8.1 odom type hash 수정 상세

**근본 원인:** `_parse_msg_definition()`이 `float64[36]` 구문을 파싱하지 못했음.

`PoseWithCovariance`와 `TwistWithCovariance`의 `float64[36] covariance` 필드가:
- `float64[36]`이 `endswith('[]')` 조건에 안 걸림 (끝이 `]`이 아니라 `[36]`)
- `len(parts) > 2` 조건에도 안 걸림 (parts가 2개)
- 결과: `float64[36]`을 nested type으로 잘못 처리 → 전혀 다른 type description → 다른 hash

**수정:**
1. `_parse_msg_definition()`: `float64[36]`, `float64[<=10]` 등 type string 내 배열 구문 파싱 추가
2. `_field_type_to_type_id()`: `array_size` 파라미터 추가하여 fixed array(`_ARRAY`)와 unbounded sequence(`_UNBOUNDED_SEQUENCE`) 구분

#### 9.8.2 GR00T executor 모듈 분리 상세

```
third_party/groot/
├── executor.py     # 공유 인프라: 상태 관리, 서비스 초기화, 라이프사이클, stop/status 핸들러
│                   # TrainingHandler와 InferenceHandler를 import하여 서비스에 연결
├── training.py     # TrainingHandler: handle_train, run_training, build_finetune_config,
│                   # execute_training, logging interceptor
└── inference.py    # InferenceHandler: handle_infer, load_policy, get_modality_config,
                    # setup_ros2_subscribers, handle_get_action_chunk
```

- Composition 패턴: Handler 클래스가 executor 참조를 받아 공유 상태에 접근
- 단일 프로세스 유지 (불필요한 프로세스 추가 없음)
- docker-compose.yml에 training.py, inference.py 볼륨 마운트 추가

#### 9.8.3 LeRobot executor 모듈 분리 상세

GR00T와 동일한 composition 패턴으로 LeRobot executor도 모듈 분리 완료:

```
third_party/lerobot/
├── executor.py     # 공유 인프라 (~790줄): 상태 관리, 서비스 초기화, 라이프사이클,
│                   # stop/status/policy_list/checkpoint_list/model_list 핸들러,
│                   # progress publishing, AVAILABLE_POLICIES 정의
│                   # TrainingHandler와 InferenceHandler를 import하여 서비스에 연결
├── training.py     # TrainingHandler (~260줄): handle_train, _run_training,
│                   # _build_training_args, _execute_training,
│                   # _setup_logging_interceptor (step/loss/grad/lr/epoch 파싱),
│                   # _restore_logging, cleanup
└── inference.py    # InferenceHandler (~330줄): handle_infer, _load_policy,
                    # _setup_ros2_subscribers, _on_image_received,
                    # _on_joint_state_received, _inference_loop (실시간 루프),
                    # _predict_from_observations, _preprocess_image,
                    # _predict_dummy_action, _publish_action, cleanup
```

**분리 전후 비교:**

| 항목 | 분리 전 | 분리 후 |
|------|---------|---------|
| executor.py | 1,353줄 (전체) | ~790줄 (공유 인프라) |
| training.py | - | ~260줄 (학습 전용) |
| inference.py | - | ~330줄 (추론 전용) |

**GR00T와 동일한 패턴:**
- Composition 패턴: Handler 클래스가 executor 참조를 받아 공유 상태에 접근
- 절대 import 사용 (`from training import TrainingHandler`) — Docker에서 개별 파일 마운트
- 단일 프로세스 유지 (불필요한 프로세스 추가 없음)
- docker-compose.yml에 training.py, inference.py 볼륨 마운트 추가

**변경 사항 요약:**
- `_handle_train` → `training.TrainingHandler.handle_train`에 위임
- `_handle_infer` → `inference.InferenceHandler.handle_infer`에 위임
- 인퍼런스 상태 (`_loaded_model`, `_inference_running`, `_ros2_subscribers`, `_latest_observations`) → InferenceHandler로 이동
- `_handle_stop`에서 `self._inference_handler.cleanup()` 호출로 인퍼런스 정리
- `stop()`에서 두 핸들러 모두 cleanup 호출
- `domain_id` 기본값 30으로 변경 (ExecutorConfig, main())

### 9.9 Cross-Container Communication 테스트 결과

#### 9.9.1 테스트 환경

- **호스트**: Jetson (arm64, Linux 5.15.148-tegra)
- **Publisher**: physical_ai_server (ROS2 Jazzy + rmw_zenoh_cpp)
- **Subscriber**: lerobot_server (zenoh_ros2_sdk, Python)
- **데이터**: `/workspace/test_dataset` (rosbag mcap, 595MB, ~75s, 15fps)
  - 로봇 타입: ffw_sg2_rev1
  - 토픽: 4 카메라, 8 관절 그룹, odom, cmd_vel, tf
- **Domain ID**: 30 (모든 컨테이너 통일)
- **Zenoh**: SHM enabled, `/tmp` shared, `ipc: host`

#### 9.9.2 기본 통신 테스트 (SHM OFF → SHM ON)

**Round 1: SHM 비활성화 상태, Domain ID 30**

| Topic | 수신 여부 | Rate | 메시지 수 (15s) |
|-------|----------|------|----------------|
| JointState | ✅ PASS | ~102 Hz | 1,537 |
| CompressedImage | ✅ PASS | ~15 Hz | 229 |
| Odometry | ✅ PASS | ~100 Hz | 1,501 |

- 모든 토픽 정상 수신
- odom type hash 수정(float64[36]) 실전 검증 완료

**Round 2: SHM 활성화, /tmp 미공유 상태**

| Topic | 수신 여부 | 원인 |
|-------|----------|------|
| JointState | ✅ PASS | ~200B → SHM threshold(3072B) 이하, 네트워크 전송 |
| CompressedImage | ❌ FAIL | ~165KB → SHM으로 전송되지만 /tmp 미공유로 negotiation 실패 |
| Odometry | ❌ FAIL | SHM negotiation 실패 영향 (실제로는 threshold 이하이지만 세션 레벨에서 영향) |

- `/tmp:/tmp` 마운트가 누락된 상태에서 SHM 활성화 → 대용량 메시지 전송 실패
- 이 경험으로 SHM의 필수 조건 3가지 확인

**Round 3: SHM 활성화 + /tmp 공유 (최종 성공)**

| Topic | 수신 여부 | Rate | Jitter | Avg Size | SHM |
|-------|----------|------|--------|----------|-----|
| JointState | ✅ PASS | 100.6 Hz | 1.04 ms | ~200B | No |
| CompressedImage | ✅ PASS | 15.0 Hz | 4.15 ms | 166.4 KB | **YES** |
| Odometry | ✅ PASS | 100.1 Hz | 0.72 ms | ~700B | No |
| CameraInfo | ✅ PASS | 15.0 Hz | 4.26 ms | ~300B | No |

- 4/4 토픽 모두 정상 수신
- CompressedImage는 100% SHM zero-copy로 전송 확인
- 모든 토픽에서 jitter < 5ms로 매우 안정적

#### 9.9.3 Docker 설정 변경사항

**docker-compose.yml 변경:**
```yaml
# 모든 컨테이너(physical_ai_server, lerobot, groot)에 추가:
volumes:
  - /dev/shm:/dev/shm          # Zenoh SHM 버퍼
  - /tmp:/tmp                    # Zenoh SHM negotiation (필수!)
ipc: host                       # IPC namespace 공유
```

**session.py 변경:**
```python
# ZENOH_SHM_ENABLED=true 환경변수로 SHM 자동 활성화
shm_enabled = os.environ.get("ZENOH_SHM_ENABLED", "").lower() == "true"
if shm_enabled and not override_has_shm:
    self.conf.insert_json5("transport/shared_memory/enabled", "true")
```

**rmw_zenoh config 변경 (physical_ai_server 내부):**
- `DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5`: `shared_memory.enabled: true`
- `DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5`: `shared_memory.enabled: true`
- `transport_optimization` threshold: 3072 bytes (기본값 유지)

#### 9.9.4 테스트 스크립트

두 개의 테스트 스크립트 작성:

1. **`test_subscriber.py`**: 기본 통신 검증 (JointState, CompressedImage, Odometry)
2. **`test_latency.py`**: 상세 지연/SHM 검증 (inter-arrival jitter, 메시지 크기 분석, SHM threshold 분석)

```bash
# lerobot 컨테이너에서 실행:
docker exec lerobot_server python3 /app/test_subscriber.py
docker exec lerobot_server python3 /app/test_latency.py
```

### 9.10 향후 작업

1. **Phase 2 진행**: RobotServiceServer 실제 서비스 등록 테스트
2. ~~odom hash 검증~~ → ✅ 완료 (Round 1에서 검증)
3. ~~domain ID 30 검증~~ → ✅ 완료 (모든 컨테이너 30으로 통일)
4. ~~통합 테스트~~ → ✅ 완료 (SHM zero-copy 포함 E2E 검증)
5. **GR00T 컨테이너 동일 테스트**: groot_server에서도 동일한 cross-container 테스트 수행
6. **SHM publisher 최적화**: robot_client의 action publish에 ShmProvider 적용 (현재 일반 put() 사용)
7. **실제 로봇 환경 검증**: rosbag이 아닌 실 로봇에서 동일한 통신 검증
