# Robot Client Design Document

## 1. Overview

### 1.1 Purpose

Currently, each opensource project's (GR00T, LeRobot, etc.) executor has over 1,400 lines of code,
of which ~800 lines (60%) are Zenoh/ROS2 communication infrastructure code.

The structure of having to copy this infrastructure code every time a new project is integrated is not scalable.

**Robot Client** is a **high-level abstraction layer** on top of zenoh_ros2_sdk,
providing a Python API that allows easy reading and writing of robot data without knowing Zenoh/ROS2.

### 1.2 Design Principles

- **Do not modify zenoh_ros2_sdk** (use as-is)
- Must be usable without knowledge of Zenoh/ROS2 message formats
- Data is always provided as Python basic types (numpy array, list, dict)
- Sensor data always maintains the latest value (background subscription)
- Topics are automatically configured by simply specifying the robot type

### 1.3 Custom Message Separation

Currently, there are many custom messages/services defined in `physical_ai_interfaces`: 8 msg + 26 srv.
These are interfaces dedicated to physical_ai_tools for training/inference/dataset management, etc.

Since zenoh_ros2_sdk is a general-purpose ROS2 communication library, these custom messages
are separated into the `messages/` directory within the robot_client package.

- **zenoh_ros2_sdk**: Handles only standard ROS2 messages (sensor_msgs, geometry_msgs, etc.)
- **robot_client/messages/**: Message definitions dedicated to physical_ai_tools
  - msg types such as TrainingProgress, ActionOutput, etc.
  - srv types such as StartInference, GetActionChunk, TrainModel, etc.

### 1.4 Location

```
zenoh_ros2_sdk/          # Existing (not modified)
  ├── publisher.py
  ├── subscriber.py
  ├── service_server.py
  └── ...

robot_client/            # New package
  ├── __init__.py
  ├── robot_client.py    # Sensor reading + action output
  ├── service_server.py  # Training/inference service framework
  ├── messages/          # Messages dedicated to physical_ai_tools
  │   ├── __init__.py
  │   ├── msg/           # TrainingProgress, ActionOutput, etc.
  │   └── srv/           # StartInference, GetActionChunk, etc.
  ├── config/            # Configuration per robot type
  │   ├── ffw_sg2_rev1.yaml
  │   ├── omx_f.yaml
  │   └── omy_f3m.yaml
  └── README.md
```

---

## 2. RobotClient - Sensor Data Reading / Action Output

### 2.1 Initialization

```python
from robot_client import RobotClient

robot = RobotClient("ffw_sg2_rev1")

# Timestamp synchronization check mode (optional)
robot = RobotClient("ffw_sg2_rev1", sync_check=True, sync_threshold_ms=33)
```

The constructor reads the YAML configuration for the given robot type
and automatically subscribes to all sensor topics.

Internally:
1. Load `config/ffw_sg2_rev1.yaml`
2. Create `ROS2Subscriber` for each camera topic (CompressedImage)
3. Create `ROS2Subscriber` for each joint topic (JointState)
4. Create `ROS2Subscriber` for each sensor topic (Odometry, Twist, TF, etc.)
5. Update latest values via callbacks in the background

### 2.2 Configuration File Structure

Based on the structure of the existing `physical_ai_server/config/ffw_sg2_rev1_config.yaml`.

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

# Additional sensors
sensors:
  odom:
    topic: "/odom"
    msg_type: "nav_msgs/msg/Odometry"

  cmd_vel:
    topic: "/cmd_vel"
    msg_type: "geometry_msgs/msg/Twist"

# Additional topics for rosbag recording
rosbag_extra_topics:
  - "/tf"
  - "/odom"
  - "/cmd_vel"
```

### 2.3 Image API

The default format is **BGR** (OpenCV default; GR00T also uses BGR input).
The default size is **original size** (no resizing). Resizing is performed only when the `resize` parameter is specified.

```python
# All camera images (dict) - original size, BGR
images = robot.get_images()
# {
#   "cam_left_head":  np.ndarray (H, W, 3) uint8 BGR,
#   "cam_right_head": np.ndarray (H, W, 3) uint8 BGR,
#   "cam_left_wrist": np.ndarray (H, W, 3) uint8 BGR,
#   "cam_right_wrist": np.ndarray (H, W, 3) uint8 BGR,
# }

# Receive in RGB format
images = robot.get_images(format="rgb")

# Specify resize (original size if not specified)
images = robot.get_images(resize=(256, 256))

# Specific camera only
img = robot.get_image("cam_left_head")
# np.ndarray (H, W, 3) uint8 BGR

# Specific camera + resize + RGB
img = robot.get_image("cam_left_head", resize=(256, 256), format="rgb")

# Query camera list
robot.camera_names  # ["cam_left_head", "cam_right_head", ...]

# Check data reception status
robot.is_image_ready("cam_left_head")  # True/False

# Check timestamp
robot.get_image_timestamp("cam_left_head")  # float (epoch seconds)
```

### 2.4 Joint API

The return type is **`np.ndarray`** (float32). This aligns with GR00T, which uses state data in `np.ndarray(dtype=np.float32)` format.
The leader/follower distinction is maintained, and **gripper is included in position** (the last element of joint_names).

> **Note: Leader Topic Distinction**
> Leaders are composed of motors, so they use different topics for **reading** (querying current angles) and **writing** (control commands).
> For now, they are unified under the same JointState topic (`read_topic`),
> but the design is extensible to allow specifying a separate `write_topic` in the configuration file.
> Followers are read-only, so they only use `read_topic`.

```python
# All joints (dict of np.ndarray)
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

# Specific group only
left_arm = robot.get_joint_positions("leader_arm_left")
# np.ndarray([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.0], dtype=float32)

# Joint velocity may also be needed
velocities = robot.get_joint_velocities()
# (same structure, extracted from JointState.velocity)

# Joint effort (torque)
efforts = robot.get_joint_efforts()

# Joint group information
robot.joint_group_names  # ["leader_arm_left", "leader_arm_right", ...]
robot.get_joint_names("leader_arm_left")  # ["arm_l_joint1", ..., "gripper_l_joint1"]
robot.get_dof("leader_arm_left")  # 8
robot.total_dof  # 22

# Data reception status
robot.is_joint_ready("leader_arm_left")  # True/False
```

### 2.5 Additional Sensor API

Provides additional sensor data such as odometry, velocity, etc., beyond cameras and joints.

```python
# Odometry (position + orientation + velocity)
odom = robot.get_odom()
# {
#   "position": np.ndarray([x, y, z], dtype=float32),
#   "orientation": np.ndarray([x, y, z, w], dtype=float32),  # quaternion
#   "linear_velocity": np.ndarray([vx, vy, vz], dtype=float32),
#   "angular_velocity": np.ndarray([wx, wy, wz], dtype=float32),
# }

# Sensor data reception status
robot.is_sensor_ready("odom")  # True/False
```

### 2.6 Action Output API

Action publishing supports **two methods**:
- **Direct publishing**: RobotClient directly publishes to the robot
- **Service method**: Returns as a `get_action_chunk` service response as before, and physical_ai_server publishes

**Follower groups are read-only**, so set commands sent to them will not work.

#### Action Chunk Handling

The model output is an action chunk (T x D, e.g., 16 timesteps x action_dim).
There are two methods to send this to the robot:

| Method | Message Type | Periodic Thread | Description |
|--------|-------------|-----------------|-------------|
| **Current implementation** | JointState | Required (10Hz) | Pop 1 at a time from buffer and publish |
| **Future transition** | JointTrajectory | Not required | Publish entire chunk as trajectory points at once |

Currently uses JointState-based approach (same as existing physical_ai_server); can transition to JointTrajectory in the future.

```python
# Method 1: Direct publishing - single action (RobotClient -> robot)
# Commands can only be sent to leader groups (followers are read-only)
robot.set_joint_positions("leader_arm_left", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.0])

# Simultaneous commands to multiple groups
robot.set_joint_positions({
    "leader_arm_left":  [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.0],
    "leader_arm_right": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.0],
})

# Method 1-2: Direct publishing - Action Chunk (sequential publishing via internal 10Hz timer)
# action_chunk: np.ndarray (T, D) - model output as-is
robot.execute_action_chunk(action_chunk, action_keys=["leader_arm_left", "leader_arm_right"],
                           frequency=10)
# Internally, a 10Hz timer pops 1 at a time from the chunk and publishes as JointState
# L2 distance-based chunk alignment (same logic as current physical_ai_server)

# Mobile base control (publish as Twist message)
robot.set_velocity(linear_x=0.5, linear_y=0.0, angular_z=0.1)

# Method 2: Service method (executor -> physical_ai_server -> robot)
# When the on_get_action handler returns an action chunk,
# physical_ai_server's InferenceManager pops 1 at a time via a 10Hz timer and publishes to the robot
@server.on_get_action
def handle_get_action(request):
    obs = robot.get_observation()
    action, info = policy.get_action(obs)
    return {"action_chunk": action, "chunk_size": 16}
```

For standalone scripts with direct control, use Method 1/1-2;
for async inference (via physical_ai_server), use Method 2.

### 2.7 Task Instruction

Use `set_task_instruction()` to set the current task instruction.
Used as part of the observation in language-conditioned models such as GR00T.

```python
# Set task instruction
robot.set_task_instruction("pick up the red cup")

# Check currently set instruction
robot.task_instruction  # "pick up the red cup"
```

Reasons for separating `set_task_instruction()` as a dedicated API:
- Task instruction does not change every frame like sensor data
- Once set at the start of inference, it persists until changed
- Automatically included in the observation (see 2.8 below)

### 2.8 Data Synchronization / Waiting

```python
# Wait until all sensors have been received at least once
robot.wait_for_ready(timeout=10.0)

# Wait for specific sensors only
robot.wait_for_image("cam_left_head", timeout=5.0)
robot.wait_for_joint("leader_arm_left", timeout=5.0)

# Get entire observation at once (for inference)
obs = robot.get_observation()
# {
#   "images": {"cam_left_head": np.ndarray, ...},
#   "joint_positions": {"leader_arm_left": np.ndarray, ...},
#   "task_instruction": "pick up the red cup",
# }
# Note: timestamp is not included in the observation (not typically used as model input)
#
# Both frameworks require images + state(joints) + language as the three core observation components:
#   - GR00T: video(uint8, B,T,H,W,C) + state(float32, B,T,D) + language(list[list[str]])
#   - LeRobot: observation.images(float32, B,C,H,W, [0,1]) + observation.state(float32, B,D) + language(tokens)
# There are no additional items; observation format conversion for each framework is handled in the executor.
```

#### Timestamp Synchronization Check (Optional Feature)

If `sync_check=True` is set during initialization, the timestamp difference between image and joint data
is checked to filter out invalid observations.

```python
# Enable sync_check mode (default: False)
robot = RobotClient("ffw_sg2_rev1", sync_check=True, sync_threshold_ms=33)

# When get_observation() is called:
# - Returns None if the timestamp difference between image and joint data is 33ms or more
# - The caller should skip inference for that frame when None is returned
obs = robot.get_observation()
if obs is None:
    # Sensor data synchronization failed -> skip inference
    continue
```

Reasons for making sync_check optional:
- Precise synchronization is not required in all situations
- It is more convenient to use without synchronization check during development/debugging
- Activate only during actual inference to ensure data quality
---

## 3. RobotServiceServer - Training/Inference Service Framework

### 3.1 Overview

Abstracts the repetitive service registration/handling/state management across each executor.
Used separately from RobotClient, with a structure where users compose them directly.

### 3.2 Basic Usage

```python
from robot_client import RobotClient, RobotServiceServer

# Create RobotClient and RobotServiceServer separately
robot = RobotClient("ffw_sg2_rev1")
server = RobotServiceServer(name="groot")   # Service prefix: /groot/train, /groot/infer, ...
```

### 3.3 Service Handler Registration

#### Training (on_train)

Training parameters differ per model (GR00T: `embodiment_tag`, `num_diffusion_steps`,
LeRobot: `eval_freq`, `num_workers`, OpenVLA: `lora_rank`, etc.).

Common fields are explicitly typed, and model-specific parameters are handled via `extra_params` (JSON -> dict).
The JSON string pattern is already in use in the project (`models_json`, `policies_json`, etc.).

```python
@server.on_train
def handle_train(request) -> dict:
    """
    request fields:
      - model_path: str           # Common (required for all models)
      - dataset_path: str         # Common
      - output_dir: str           # Common
      - extra_params: dict        # Model-specific parameters (automatically converted from JSON -> dict)
        e.g.) GR00T:  {"embodiment_tag": "gr1", "steps": 1000, "batch_size": 32, ...}
        e.g.) LeRobot: {"steps": 5000, "eval_freq": 500, "wandb_project": "my_project", ...}

    Returns: {"success": bool, "message": str}
    """
    extra = request.extra_params  # Access as dict
    config = build_finetune_config(
        model_path=request.model_path,
        dataset_path=request.dataset_path,
        steps=extra.get("steps", 1000),
        batch_size=extra.get("batch_size", 32),
        learning_rate=extra.get("learning_rate", 1e-4),
        # ... additional model-specific parameters
    )
    run_training(config)
    return {"success": True, "message": "Training complete"}
```

Service message definition:
```
# TrainModel.srv
string model_path
string dataset_path
string output_dir
string extra_params_json    # JSON string -> automatically converted to dict inside server
---
bool success
string message
string job_id
```

#### Model Loading (on_load_policy)

Since RobotClient automatically subscribes to robot topics, `camera_topic_map` and `joint_topic_map` are unnecessary.
`task_instruction` can be set as an initial value, and can also be changed during inference with each `get_action` call.

```python
@server.on_load_policy
def handle_load_policy(request) -> dict:
    """
    request fields:
      - model_path: str
      - embodiment_tag: str (optional)
      - task_instruction: str (optional, initial task)
      - extra_params: dict (optional, additional model-specific settings)

    Returns: {"success": bool, "message": str, "action_keys": list[str]}
    """
    policy = load_model(request.model_path)
    if request.task_instruction:
        robot.set_task_instruction(request.task_instruction)
    return {"success": True, "action_keys": policy.action_keys}
```

> **Note:** Each decorator handler (`on_load_policy`, `on_get_action`, etc.) is **implemented differently per project**.
> The `load_model()`, `policy.get_action()` above are placeholders; GR00T/LeRobot/OpenPI etc. implement them with their own APIs.
> When sharing variables like `policy` between handlers, use class instance variables or module-level variables.

#### Stop (on_stop)

```python
@server.on_stop
def handle_stop() -> dict:
    cleanup()
    return {"success": True}
```

#### Action Generation (on_get_action)

The `task_instruction` can be changed with each call, enabling multi-task execution with a single model.

```python
@server.on_get_action
def handle_get_action(request) -> dict:
    """
    request fields:
      - task_instruction: str (optional, only when changing)

    Returns: {"action_chunk": np.ndarray, "chunk_size": int}
    """
    # Update if task_instruction is included
    if request.task_instruction:
        robot.set_task_instruction(request.task_instruction)

    obs = robot.get_observation()
    action, info = policy.get_action(obs)
    return {"action_chunk": action, "chunk_size": 16}
```

Multi-task scenario example:
```
1. StartInference(model_path="...", task_instruction="pick up the apple")
2. GetActionChunk()                                          -> inference with "pick up the apple"
3. GetActionChunk()                                          -> same
4. GetActionChunk(task_instruction="place it on the plate")  -> task changed!
5. GetActionChunk()                                          -> inference with "place it on the plate"
```

### 3.4 Training Progress Reporting

**Direct access is recommended** for training progress. Log parsing is maintained only as a fallback.

#### GR00T (HuggingFace Trainer)

Using the HuggingFace `TrainerCallback` allows direct access to metrics without log parsing.

```python
# Inside gr00t/experiment/trainer.py:
# Gr00tTrainer.compute_loss() computes the loss,
# and the HF Trainer calls the on_log callback every logging_steps.

from transformers import TrainerCallback

class ProgressCallback(TrainerCallback):
    def __init__(self, server):
        self.server = server

    def on_log(self, args, state, control, logs=None, **kwargs):
        # logs: {"loss": 0.45, "learning_rate": 1.2e-4, "grad_norm": 0.8, ...}
        # state: global_step, max_steps, epoch, etc.
        self.server.report_progress(
            step=state.global_step,
            total_steps=state.max_steps,
            epoch=state.epoch,
            loss=logs.get("loss", 0),
            learning_rate=logs.get("learning_rate", 0),
            gradient_norm=logs.get("grad_norm", 0),
        )

# Usage in executor:
trainer = Gr00tTrainer(model=model, args=training_args, ...)
trainer.add_callback(ProgressCallback(server))
trainer.train()
```

#### LeRobot (Custom Training Loop + Accelerator)

Since it uses a custom loop, metrics are accessed directly from `MetricsTracker` after `update_policy()`.

```python
# Inside lerobot/scripts/lerobot_train.py:
# update_policy() performs forward + backward,
# and loss, grad_norm, lr, etc. are recorded in train_tracker (MetricsTracker).

for step in range(total_steps):
    train_tracker, output_dict = update_policy(
        train_tracker, policy, batch, optimizer, ...
    )

    # Direct access from MetricsTracker (no log parsing needed)
    server.report_progress(
        step=step,
        total_steps=total_steps,
        loss=train_tracker.loss,
        learning_rate=train_tracker.lr,
        gradient_norm=train_tracker.grad_norm,
        epoch=train_tracker.epochs,
    )
```

#### Available Metrics Comparison

| Metric | GR00T (TrainerCallback) | LeRobot (MetricsTracker) |
|--------|------------------------|--------------------------|
| loss | `logs["loss"]` | `tracker.loss` |
| learning_rate | `logs["learning_rate"]` | `tracker.lr` |
| gradient_norm | `logs["grad_norm"]` | `tracker.grad_norm` |
| step | `state.global_step` | loop counter |
| epoch | `state.epoch` | `tracker.epochs` |
| accuracy | `logs["train_accuracy"]` | - |
| update_time | - | `tracker.update_s` |

#### Fallback: Log Parsing

For projects where direct access is difficult (cases where the training loop cannot be modified),
`server.enable_log_interceptor()` is also provided as a fallback using the existing log parsing method.

### 3.5 State Management

```python
# Automatic management: TRAINING on on_train entry, IDLE on completion, ERROR on error
# Manual override is also possible
server.state  # "idle" | "training" | "inference" | "error"
```

### 3.6 Checkpoint/Model List

```python
@server.on_checkpoint_list
def handle_checkpoint_list() -> list[dict]:
    """
    Returns: [{"name": "checkpoint-100", "path": "/workspace/...", "step": 100}, ...]
    """
    return scan_checkpoints("/workspace/output")

# Default implementation is also provided (automatically scans workspace if not overridden)
```

### 3.7 Execution

`RobotClient` and `RobotServiceServer` are separate components.
Users directly manage the initialization order and main loop.

```python
from robot_client import RobotClient, RobotServiceServer

robot = RobotClient("ffw_sg2_rev1")
server = RobotServiceServer(name="groot")
policy = None

# Register handlers
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

# User directly manages the startup sequence
robot.wait_for_ready(timeout=10.0)   # Wait for sensor reception
server.start()                        # Register services + start progress publisher

# Main loop: keeps the process alive
# Zenoh services handle requests in background threads,
# so without this loop the process would terminate immediately.
# Actual inference/training processing is automatically performed in service callbacks.
try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    server.stop()
    robot.close()
```

Inside `server.start()`:
1. Zenoh connection
2. Register handlers as services
3. Start progress publisher

Inside `server.stop()`:
1. Stop progress publisher
2. Unregister services
3. Close Zenoh connection

This separation makes it **possible to use robot alone without server**:
```python
# Standalone script (direct use without services)
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

## 4. Full Executor Comparison (Before vs After)

### 4.1 GR00T Executor

**Before** (1,429 lines):
```
Zenoh connection/configuration       ~80 lines
ExecutorState, TrainingProgress      ~60 lines
Service registration/handling        ~150 lines
Image/joint subscription+callbacks   ~80 lines
Progress publishing                  ~90 lines
State management                     ~50 lines
Stop/Status handlers                 ~40 lines
Lifecycle (start/stop/main)          ~50 lines
─────────────────────────────────────────────
Infrastructure total                 ~600 lines (-> 0 lines)

Model loading (embodiment)           ~100 lines
Training setup + execution           ~160 lines
Inference setup + execution          ~200 lines
Checkpoint management                ~80 lines
Observation assembly                 ~60 lines
TensorRT application                 ~30 lines
─────────────────────────────────────────────
Project-specific logic total         ~630 lines

Other (dataclass, enum, import)      ~200 lines
```

**After** (~250 lines estimated):
```python
from robot_client import RobotClient, RobotServiceServer
from transformers import TrainerCallback

robot = RobotClient("ffw_sg2_rev1")
server = RobotServiceServer(name="groot")
policy = None

def load_groot_policy(model_path, embodiment_tag, trt_engine=None):
    """GR00T model loading + TensorRT optimization
    TensorRT replaces only the DiT (Diffusion Transformer, 1.09B params) part.
    The Eagle vision backbone and tokenizer, etc. remain as PyTorch.
    The NVIDIA official guide (standalone_inference_script.py) uses the same approach.
    """
    policy = Gr00tPolicy(...)
    if trt_engine:
        replace_dit_with_tensorrt(policy, trt_engine)
    return policy

def prepare_observation(robot, policy):
    """Convert RobotClient data -> GR00T observation format"""
    images = robot.get_images(resize=(256, 256), format="rgb")
    joints = robot.get_joint_positions()
    mc = policy.get_modality_config()
    # ... modality key mapping (~30 lines)
    return obs


# ProgressCallback is defined at module level (do not put a class inside a function)
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
    # ... config setup (~40 lines)
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

### 4.2 When Adding a New Project

```python
# Example: When integrating OpenPI
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

**New project: ~50 lines (when supporting inference only)**

> A **guide document + template** for adding new projects will be created in Migration Phase 5.
> A complete example including both train/inference will be provided,
> so that AI Agents or general developers can create new projects following the same structure.

---

## 5. Internal Implementation Details

### 5.1 RobotClient Internal Structure

```python
class RobotClient:
    def __init__(self, robot_type: str, zenoh_config: dict = None,
                 sync_check: bool = False, sync_threshold_ms: float = 33):
        self._config = load_robot_config(robot_type)
        self._zenoh_session = create_zenoh_session(zenoh_config)
        self._sync_check = sync_check
        self._sync_threshold_ms = sync_threshold_ms

        # Latest data storage (thread-safe)
        self._images: dict[str, np.ndarray] = {}           # BGR original
        self._image_timestamps: dict[str, float] = {}
        self._joint_positions: dict[str, np.ndarray] = {}  # float32
        self._joint_timestamps: dict[str, float] = {}
        self._sensors: dict[str, dict] = {}                # odom, etc.
        self._task_instruction: str = ""
        self._lock = threading.Lock()

        # Publishers for action output (leader groups only)
        self._publishers: dict[str, ROS2Publisher] = {}

        # Subscription/publishing initialization
        self._subscribers: list[ROS2Subscriber] = []
        self._init_subscriptions()
        self._init_publishers()

    def _init_subscriptions(self):
        """Automatically subscribe to all topics based on configuration file"""
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
        """Create publishers for leader groups (excluding followers)"""
        for group_name, group_config in self._config["joint_groups"].items():
            if group_config.get("role") == "leader":
                self._publishers[group_name] = ROS2Publisher(
                    topic=group_config["topic"],
                    msg_type="sensor_msgs/msg/JointState",
                )

    def _update_image(self, cam_name: str, msg):
        """Convert CompressedImage -> numpy array (BGR, original size) and store"""
        buf = np.frombuffer(msg.data, dtype=np.uint8)
        img = cv2.imdecode(buf, cv2.IMREAD_COLOR)  # BGR
        with self._lock:
            self._images[cam_name] = img
            self._image_timestamps[cam_name] = time.time()

    def _update_joint(self, group_name: str, msg):
        """Convert JointState -> np.ndarray(float32) and store"""
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
        """Publish JointState to leader groups. Warning for followers."""
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
        """Return full observation for inference"""
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

### 5.2 RobotServiceServer Internal Structure

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

    # --- Decorators: Handler Registration ---

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

    # --- Progress Reporting ---

    def report_progress(self, **kwargs):
        """Update + publish training progress (thread-safe)"""
        for k, v in kwargs.items():
            setattr(self._progress, k, v)
        if self._progress_publisher:
            self._publish_progress()

    def enable_log_interceptor(self, patterns=None):
        """Fallback: Extract progress via log parsing (when direct access is not possible)"""
        self._setup_logging_interceptor(patterns)

    # --- Service Request Handling (internal) ---

    def _handle_service_request(self, service_name, raw_request):
        """Convert service request to dict and call handler"""
        request = self._parse_request(raw_request)
        # extra_params_json -> dict automatic conversion
        if hasattr(request, "extra_params_json") and request.extra_params_json:
            request.extra_params = json.loads(request.extra_params_json)
        else:
            request.extra_params = {}

        handler = self._handlers.get(service_name)
        if handler:
            # Automatic state transition
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
        """Register services + start progress publisher"""
        self._zenoh_session = create_zenoh_session()
        self._register_services()
        self._start_progress_publisher()
        self._running = True

    def stop(self):
        """Unregister services + stop progress publisher"""
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

## 6. Considerations and Questions

### Resolved Items

| Item | Decision | Rationale |
|------|----------|-----------|
| Image format | BGR by default, selectable with `format="rgb"` parameter | GR00T uses BGR, consistent with OpenCV convention |
| Image resize | Original size by default, selectable with `resize=(W,H)` parameter | Default resizing would be unnatural |
| Joint return type | `np.ndarray` (float32) | GR00T uses np.ndarray(dtype=float32) |
| Leader/follower distinction | Maintained | Distinguished by `role` field in configuration file |
| Gripper | Included in position | Included as the last element of joint_names |
| Action publishing | Both direct publishing + service method supported | Supports both standalone use and async inference |
| Action message type | JointState (not JointTrajectory) | Confirmed from existing implementation |
| Follower set | Read-only, warning output | Setting follower does not work |
| Timestamp in obs | Excluded | Not used as model input |
| Task instruction | Separated as `set_task_instruction()` API, changeable per get_action call | Supports multi-task scenarios |
| Synchronization check | Optional (`sync_check=True`, 33ms threshold) | Development convenience vs actual inference quality |
| Custom messages | Separated to `robot_client/messages/` | Keep zenoh_ros2_sdk as a general-purpose library |
| Training parameters | Common fields + `extra_params_json` (JSON -> dict) | Parameters differ per model, leveraging existing JSON pattern |
| topic_map in infer | Removed | RobotClient automatically subscribes based on robot type |
| Progress reporting | Direct access recommended (TrainerCallback/MetricsTracker), log parsing as fallback only | Direct access is accurate and stable |
| run_forever() | Removed, separated into `start()`/`stop()` | User-composable structure is more flexible |
| RobotClient separation | Created separately from server | Allows using robot alone without server (standalone) |

### Additional Resolved Items (Comment 3)

| Item | Decision | Rationale |
|------|----------|-----------|
| Joint group key naming | RobotClient uses configuration file keys, modality key mapping is done in executor | Modality keys are GR00T-specific names and can be modified to fit our needs later |
| Package location | `third_party/robot_client/` (Option A) | Independent package, can be separated into a separate repo later |
| Configuration file | Shared with physical_ai_server config (Option B, symlink/mount) | Prevents configuration duplication |
| Dynamic topic mapping | Subscribe only via configuration file at initialization (Option A) | Topic additions are guided through config file modification |
| Multiple executors | Only one inference is used, sensor data is also subscribed once | Only the active executor has active subscriptions, others wait |
| Error handling | Return empty dict + warning log, process does not die, can wait with `wait_for_ready()` | Stability first |
| handle_infer naming | Changed to `on_load_policy` / `handle_load_policy` | Name matching the actual role |
| Internal method naming | `_init_subscriptions`, `_init_publishers`, `_update_image`, `_update_joint` | Clear names matching their roles |
| build_observation | Changed to `prepare_observation` | "prepare" is more appropriate than "build" |
| ProgressCB | Extracted to module level (do not define class inside a function) | Code readability |
| Leader read/write topics | Currently the same, structure allows separating `write_topic` in config file | Leaders may have different read/write topics |
| Action chunk publishing | Pop 1 at a time via internal 10Hz timer and publish as JointState (current), can transition to JointTrajectory in the future | Maintains existing structure |
| Observation items | Three items: images + joints + task_instruction (no additional items) | Same for both GR00T and LeRobot |

### Unresolved Questions

(All major design questions have been resolved. This section will be updated if additional questions arise during implementation.)

---

## 7. Migration Plan

### Phase 1: robot_client Package Implementation
1. Implement RobotClient (sensor reading)
2. Define configuration file format
3. Unit tests

### Phase 2: RobotServiceServer Implementation
1. Implement service framework
2. Implement decorator pattern
3. Progress publishing logic

### Phase 3: GR00T Executor Migration
1. Convert existing executor.py to new structure
2. Verify that existing functionality works identically

### Phase 4: LeRobot Executor Migration
1. Convert in the same manner

### Phase 5: Documentation + Template
1. Create a **template executor** for adding new projects (complete example with train + inference)
2. **Developer guide document**: Enable AI Agents and general developers to create new projects following the same structure

### Phase 6: physical_ai_server Refactoring (Final Phase)
1. After robot_client is complete, remove unnecessary parts from physical_ai_server
2. physical_ai_server currently directly subscribes to sensor topics,
   but after robot_client is introduced, each executor handles data directly, making this unnecessary
3. Reduce physical_ai_server's role to: rosbag recording, service routing, UI integration, etc.
4. Proceed only after all Phases 1-5 are complete and tests are verified
