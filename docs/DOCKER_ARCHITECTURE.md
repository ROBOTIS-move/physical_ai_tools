# Physical AI Tools - Docker Architecture (Revised)

## Overview

Physical AI Tools consists of 4 Docker containers:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Host Machine                                    │
│                                                                             │
│  ┌─────────────────┐                                                        │
│  │ physical_ai_    │                                                        │
│  │ manager (UI)    │◄────── HTTP (rosbridge) ──────┐                        │
│  │ React + Nginx   │                               │                        │
│  │ Port: 80        │                               │                        │
│  └─────────────────┘                               │                        │
│                                                    │                        │
│  ┌─────────────────┐      Zenoh P2P + SHM      ┌───┴───────────┐            │
│  │   lerobot       │◄─────────────────────────►│ physical_ai_  │            │
│  │   server        │      (zenoh_ros2_sdk)     │ server (ROS2) │            │
│  │  LeRobot +      │                           │               │            │
│  │  Zenoh SDK      │                           │ rmw_zenoh_cpp │            │
│  └─────────────────┘                           └───────────────┘            │
│                                                        ▲                    │
│  ┌─────────────────┐      Zenoh P2P + SHM             │                    │
│  │   groot         │◄─────────────────────────────────┘                    │
│  │   server        │      (zenoh_ros2_sdk)                                 │
│  │  GR00T +        │                                                       │
│  │  Zenoh SDK      │                                                       │
│  └─────────────────┘                                                       │
│                                                                             │
│  ※ lerobot and groot do not communicate directly (routed via physical_ai_server) │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Communication Architecture Description
- **physical_ai_manager ↔ physical_ai_server**: WebSocket/HTTP communication via rosbridge
- **physical_ai_server ↔ lerobot**: Zenoh P2P + zenoh_ros2_sdk
- **physical_ai_server ↔ groot**: Zenoh P2P + zenoh_ros2_sdk
- **lerobot ↔ groot**: No direct communication (routed via physical_ai_server if needed)

---

## Zenoh Communication Mode Description

### Peer Mode (Currently Used)
- All nodes communicate directly via P2P
- Automatic discovery via multicast scouting (224.0.0.224:7446)
- **Pros**: Direct communication without a router, low latency (70% lower compared to Client mode)
- **Cons**: Each node must maintain multiple sessions

### Client Mode
- Communicates by connecting to a single router
- Suitable for resource-constrained devices
- **Pros**: Simple structure, low memory usage
- **Cons**: Router dependency, relatively higher latency

### Router Mode
- Routes data between clients
- Used when connecting different networks

**Current Configuration**: Client Mode (connected to an external Router)

```
┌─────────────────┐
│  Externally      │
│  Managed         │
│  Zenoh Router   │◄──── ros2 run rmw_zenoh_cpp rmw_zenohd
│  (rmw_zenohd)   │      (runs in a different Docker container)
└────────┬────────┘
         │
    ┌────┴────┬─────────────┐
    ▼         ▼             ▼
┌───────┐ ┌───────┐ ┌───────────┐
│ ROS2  │ │lerobot│ │   groot   │
│Server │ │       │ │           │
│(Client)│ │(Client)│ │ (Client)  │
└───────┘ └───────┘ └───────────┘
```

- Zenoh Router is **managed externally** (not run in our containers)
- All containers connect to the Router as Clients
- Shared Memory enabled: `transport/shared_memory/enabled=true`

Sources:
- [Zenoh Deployment Guide](https://zenoh.io/docs/getting-started/deployment/)
- [Zenoh Peer-to-Peer Performance](https://zenoh.io/blog/2025-07-11-zenoh-pico-peer-to-peer-unicast/)

---

## 1. physical_ai_manager (React UI)

### Role
- Web-based user interface
- Sends data collection, training, and inference commands
- Communicates with physical_ai_server via rosbridge

### Base Image
| Architecture | Base Image |
|--------------|------------|
| All | `node:22` (build) → `nginx:1.27.5-alpine` (runtime) |

### Features
- Lightweight via multi-stage build
- **Port: 80** (standard HTTP port)
- Architecture-independent

### TODO
- [ ] Change port from 8080 to 80

---

## 2. physical_ai_server (ROS2 + Zenoh)

### Role
- ROS2-based robot control
- Communication with lerobot/groot via Zenoh (rmw_zenoh_cpp)
- Data collection (rosbag recording)
- Hardware interface

### Base Image
| Architecture | Base Image |
|--------------|------------|
| AMD64 | `robotis/ros:jazzy-ros-base-torch2.7.0-cuda12.8.0` |
| ARM64 (Jetson) | `robotis/ros:jazzy-ros-base-torch2.7.0-cuda12.8.0` |

### Issues with the Current Build Approach

The current Dockerfile clones from GitHub:
```dockerfile
RUN git clone -b feature-1.0.0 https://github.com/ROBOTIS-GIT/physical_ai_tools.git --recursive
```

**Issues**:
1. Local changes are not reflected
2. Full clone required every time
3. Network dependency

### Improvement: Volume Mount Approach

Volume mounts are already configured in docker-compose.yml:
```yaml
volumes:
  - ../:/root/ros2_ws/src/physical_ai_tools/
```

**Proposal**: Remove clone from Dockerfile and use volume-mounted code
- During development, use volume mounts for real-time reflection of changes
- For deployment, use COPY or image builds

### LeRobot Removal

LeRobot is currently installed in physical_ai_server, but since a separate lerobot container exists, it should be removed:
```dockerfile
# To be removed
RUN cd ${COLCON_WS}/src/physical_ai_tools/third_party/lerobot/lerobot && pip install -e .
RUN pip install -e ".[smolvla]"
```

### Key Components (After Cleanup)
- **ROS2 Jazzy**: Robot middleware
- **rmw_zenoh_cpp**: Zenoh-based ROS2 communication
- **PyTorch + CUDA**: GPU acceleration (if needed)

---

## 3. lerobot (LeRobot Server)

### Role
- Runs the HuggingFace LeRobot framework
- Training (ACT, Diffusion Policy, SmolVLA, etc.)
- Inference (policy execution)
- Communicates with physical_ai_server via Zenoh SDK

### Base Image

| Architecture | Base Image | Verification Status |
|--------------|------------|---------------------|
| AMD64 | `nvcr.io/nvidia/pytorch:24.12-py3` | ✅ Available |
| ARM64 (Jetson) | `nvcr.io/nvidia/l4t-jetpack:r36.4.0` | ✅ Available (JetPack 6.x) |

### Jetson PyTorch Installation
```dockerfile
# CUDA-enabled PyTorch provided by Jetson AI Lab
RUN uv pip install torch torchvision \
    --index-url https://pypi.jetson-ai-lab.io/jp6/cu126/+simple
```
- Compatible with JetPack 6.x + CUDA 12.6
- Supports Jetson Orin series

### LeRobot Optional Dependencies Analysis

Currently installed:
```
.[dynamixel,gamepad,hopejr,lekiwi,reachy2,kinematics]  # Robot/Hardware
.[smolvla,xvla,hilserl,async,dev,test]                  # Policy/Development
.[video_benchmark,aloha,pusht,phone,libero,metaworld,sarm,peft]  # Simulation/Other
```

| Extra | Purpose | Required for Training/Inference? |
|-------|---------|----------------------------------|
| `dynamixel` | Dynamixel motor control | ❌ (Controlled by server) |
| `gamepad` | Gamepad input | ❌ |
| `hopejr` | HopeJr robot | ❌ |
| `lekiwi` | LeKiwi robot | ❌ |
| `reachy2` | Reachy2 robot | ❌ |
| `kinematics` | Inverse kinematics | ❌ |
| `smolvla` | SmolVLA policy | ✅ |
| `xvla` | X-VLA policy | ✅ |
| `hilserl` | HIL-SERL policy | ✅ |
| `async` | Asynchronous inference | ✅ |
| `dev` | Development tools | ❌ |
| `test` | Testing | ❌ |
| `aloha` | ALOHA simulation | ❌ |
| `pusht` | PushT simulation | ❌ |
| `libero` | Libero simulation | ❌ |
| `metaworld` | MetaWorld simulation | ❌ |
| `peft` | Parameter-efficient fine-tuning | ✅ |

**Recommended Installation**:
```dockerfile
# Only what is needed for training/inference
RUN uv pip install ".[smolvla,xvla,hilserl,async,peft]"
```

### entrypoint.sh Functionality

```bash
case "${1:-server}" in
    server)     # Zenoh server mode (default) - runs executor.py
    train)      # Training mode - python -m lerobot.scripts.train (for direct execution)
    infer)      # Inference mode - python -m lerobot.scripts.eval (for direct execution)
    shell)      # Interactive shell
esac
```

- **server** (default): Runs `executor.py`
  - Receives ROS2 service requests via Zenoh
  - **Directly imports** LeRobot code to execute (not subprocess)
  ```python
  # Inside executor.py
  from lerobot.scripts.lerobot_train import train as lerobot_train
  lerobot_train(cfg)  # Direct function call
  ```
- **train/infer**: For direct testing outside Docker (bypasses executor.py)

---

## 4. groot (GR00T N1.6 Server)

### Role
- Runs NVIDIA Isaac GR00T models
- VLA (Vision-Language-Action) inference
- Fine-tuning
- Communicates with physical_ai_server via Zenoh SDK

### Base Image

| Architecture | Base Image | Verification Status |
|--------------|------------|---------------------|
| AMD64 | `nvcr.io/nvidia/pytorch:25.04-py3` | ✅ (Same as official Dockerfile) |
| ARM64 (Jetson) | `nvcr.io/nvidia/l4t-jetpack:r36.4.0` | ✅ (JetPack 6.x) |

### Jetson Orin Support (Based on Isaac-GR00T Official Documentation)

**Performance Benchmarks (Orin, CUDA 12.6, PyTorch 2.8)**:
| Mode | E2E Time | Frequency |
|------|----------|-----------|
| PyTorch Eager | 300 ms | 3.3 Hz |
| torch.compile | 199 ms | 5.0 Hz |
| TensorRT | 173 ms | 5.8 Hz |

**Jetson PyTorch Installation**:
```dockerfile
# For Orin
ENV PIP_INDEX_URL=https://pypi.jetson-ai-lab.io/jp6/cu126/+simple

# For Thor (future)
# ENV PIP_INDEX_URL=https://pypi.jetson-ai-lab.io/sbsa/cu130
```

### Differences from the Official Dockerfile

Official (`Isaac-GR00T/docker/Dockerfile`):
```dockerfile
FROM nvcr.io/nvidia/pytorch:25.04-py3
RUN pip install imageio h5py boto3 transformers[torch] deepspeed timm peft diffusers ...
RUN cd /opt && git clone pytorch3d && pip install .  # Takes 20+ minutes
```

**pytorch3d Analysis Results**:
```
gr00t/ (core code)     → No imports ❌
scripts/               → No imports ❌
pyproject.toml         → Not a dependency ❌
external_dependencies/ → URL references only (no imports)
```
**Conclusion: pytorch3d can be removed for both AMD64/ARM64** (saves 20+ minutes of build time)

**Improvement Suggestions**:
- Remove pytorch3d (not actually used)
- On ARM64, limit flash-attn and deepspeed installation (inference only)

### ARM64 Limitations
| Package | Status | Alternative |
|---------|--------|-------------|
| `flash-attn` | Requires CUDA compilation (memory constraints) | Use default attention |
| `deepspeed` | Limited ARM64 support | Single GPU training |
| `torchcodec` | Not supported on ARM64 | Use decord or av |

---

## Docker Compose Structure

### Automatic Architecture Detection

Auto-detected in `container.sh`:
```bash
MACHINE_ARCH=$(uname -m)
if [ "$MACHINE_ARCH" = "aarch64" ] || [ "$MACHINE_ARCH" = "arm64" ]; then
    export ARCH="arm64"
else
    export ARCH="amd64"  # Default
fi
```
→ ✅ Auto-detection works (detected as `aarch64` on Jetson)

### Service Dependencies

`depends_on` in docker-compose.yml:
```yaml
lerobot:
  depends_on:
    - physical_ai_server

groot:
  depends_on:
    - physical_ai_server
```

This defines the **startup order** (to ensure Zenoh connectivity)
- physical_ai_manager can start independently (rosbridge connects later)

### Volume Mount Structure

| Container | Host Path | Container Path | Shared |
|-----------|-----------|----------------|--------|
| physical_ai_server | `./docker/workspace` | `/workspace` | - |
| physical_ai_server | `./docker/huggingface` | `/root/.cache/huggingface` | ✅ Shared |
| lerobot | `./third_party/lerobot/workspace` | `/workspace` | Separate |
| lerobot | `./docker/huggingface` | `/root/.cache/huggingface` | ✅ Shared |
| groot | `./third_party/groot/workspace` | `/workspace` | Separate |
| groot | `./docker/huggingface` | `/root/.cache/huggingface` | ✅ Shared |

**Note**: Each container's `/workspace` is a **separate** directory
- Only the HuggingFace cache is shared (to prevent duplicate model downloads)

---

## Current Issues and Solutions

### Issue 1: Git Clone Approach in physical_ai_server
**Current**: Clones from GitHub
**Solution**: Use volume mounts (already configured)

Dockerfile modification:
```dockerfile
# Remove
RUN git clone -b feature-1.0.0 https://github.com/ROBOTIS-GIT/physical_ai_tools.git --recursive

# Use volume-mounted path
# In docker-compose.yml: ../:/root/ros2_ws/src/physical_ai_tools/
```

### Issue 2: rosdep OpenCV Key Error
**Symptom**: `Cannot locate rosdep definition for [OpenCV]`
**Cause**: `OpenCV` is not a valid rosdep key on Jetson/Ubuntu
**Solution**: Modify `rosbag_recorder/package.xml`
```xml
<!-- Before -->
<depend>OpenCV</depend>
<!-- After -->
<depend>libopencv-dev</depend>
```

### Issue 3: Duplicate LeRobot Installation
**Current**: LeRobot is installed in physical_ai_server
**Solution**: Remove LeRobot-related entries from the physical_ai_server Dockerfile

---

## TODO Summary

### physical_ai_manager
- [ ] Change port from 8080 to 80

### physical_ai_server
- [ ] Remove Git clone, switch to volume mount approach
- [ ] Remove LeRobot installation section
- [ ] Fix `rosbag_recorder/package.xml`: change `OpenCV` to `libopencv-dev`
- [ ] Remove `zenohd` execution from docker-compose.yml (use external Router)

### lerobot
- [ ] Clean up optional dependencies (keep only what is needed for training/inference)
  - Keep: `smolvla`, `xvla`, `hilserl`, `async`, `peft`
  - Remove: `dynamixel`, `gamepad`, `hopejr`, `lekiwi`, `reachy2`, `kinematics`, `dev`, `test`, simulation-related

### groot
- [ ] Remove pytorch3d installation (both AMD64/ARM64 - not actually used, saves 20+ minutes)
- [ ] ARM64: Remove flash-attn, deepspeed (unnecessary for inference-only use)
