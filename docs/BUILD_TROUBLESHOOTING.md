# Docker Build Troubleshooting Guide (ARM64/Jetson)

This document records the issues encountered and their solutions when building Docker images on ARM64 (Jetson Orin) environments.

## Build Environment

- **Platform**: NVIDIA Jetson Orin (ARM64, aarch64)
- **JetPack**: 6.x (L4T R36.4)
- **Storage**: NVMe SSD mounted at `/home/rc/workspace` (229GB)
- **Docker**: with compose v2

---

## Issue 1: Build Context Too Large → Disk Full

### Symptoms
```
ERROR: failed to copy files: userspace copy failed: write .../model-00001-of-00002.safetensors: no space left on device
```

The `COPY .` command in the `physical_ai_server` Dockerfile sent the entire project directory as the Docker build context. This included `docker/huggingface/` (20GB+ model files) and `third_party/` submodules, causing the build context to balloon to 26GB+.

### Solution
Created a `.dockerignore` file at the project root to exclude unnecessary files:

```
docker/huggingface/     # Model files (volume-mounted at runtime)
docker/workspace/       # Workspace data
third_party/lerobot/lerobot/   # Submodule source
third_party/groot/Isaac-GR00T/ # Submodule source
**/*.safetensors        # Large model files
**/*.pt, **/*.pth       # PyTorch checkpoints
```

### Additional Actions
Docker build cache was occupying 128.7GB. Cleanup was needed with `docker builder prune -af`.

---

## Issue 2: pip install matplotlib Failure (physical_ai_server)

### Symptoms
```
ERROR: Could not find a version that satisfies the requirement matplotlib (from versions: none)
ERROR: No matching distribution found for matplotlib
```

The pip in the base image (`robotis/ros:jazzy-ros-base-torch2.7.0-cuda12.8.0`) was configured to only reference the Jetson-specific index (`pypi.jetson-ai-lab.dev`), which did not have matplotlib available.

### Solution
Specified PyPI as an additional index in `physical_ai_server/Dockerfile.arm64`:

```dockerfile
# Before
RUN pip install psutil matplotlib

# After
RUN pip install psutil matplotlib --extra-index-url https://pypi.org/simple
```

---

## Issue 3: No decord==0.6.0 ARM64 Wheel (groot)

### Symptoms
```
Because decord==0.6.0 has no wheels with a matching platform tag (e.g., manylinux_2_35_aarch64)
and you require decord==0.6.0, we can conclude that your requirements are unsatisfiable.

hint: Wheels are available for decord (v0.6.0) on the following platforms: manylinux2010_x86_64, win_amd64
```

The `decord` package only provides pre-built wheels for x86_64 and Windows. Building from source is required on ARM64 (Jetson).

### Solution
Removed decord from the pip install list in `third_party/groot/Dockerfile.arm64` and replaced it with a source build:

```dockerfile
# Remove decord from pip install list and build separately from source
RUN apt-get update && apt-get install -y --no-install-recommends \
    libavcodec-dev libavfilter-dev libavformat-dev libavutil-dev \
    && rm -rf /var/lib/apt/lists/* \
    && git clone --recursive https://github.com/dmlc/decord /tmp/decord \
    && cd /tmp/decord && mkdir build && cd build \
    && cmake .. -DUSE_CUDA=OFF -DCMAKE_BUILD_TYPE=Release \
    && make -j$(nproc) \
    && cd ../python && pip install . \
    && rm -rf /tmp/decord
```

**Note**: CUDA-accelerated decoding (`-DUSE_CUDA=ON`) may require additional CUDA headers. CPU mode works sufficiently well.

---

## Issue 4: uv Installs CPU Version of PyTorch from PyPI (groot, lerobot)

### Symptoms
```
PyTorch: 2.10.0+cpu
CUDA available: False
```

`torch.cuda.is_available()` returned `False` inside the container.

### Cause
When `--extra-index-url https://pypi.org/simple` is specified, `uv` preferentially selects the CPU wheel from PyPI over the CUDA wheel from the Jetson AI Lab index.

Additionally, when running lerobot's `uv pip install ".[smolvla,xvla,hilserl,async,peft]"`, torch was overwritten with the PyPI CPU version as a dependency.

### Solution
1. **Use only the Jetson index when installing torch** (remove `--extra-index-url`):
```dockerfile
RUN uv pip install torch torchvision \
    --index-url https://pypi.jetson-ai-lab.io/jp6/cu126/+simple
```

2. **lerobot: Reinstall Jetson CUDA torch after installing dependencies**:
```dockerfile
RUN uv pip install --no-cache ".[smolvla,xvla,hilserl,async,peft]"
# Reinstall Jetson CUDA PyTorch (lerobot deps may overwrite with CPU version from PyPI)
RUN uv pip install --reinstall torch torchvision \
    --index-url https://pypi.jetson-ai-lab.io/jp6/cu126/+simple
```

---

## Issue 5: Missing libopenblas.so.0 (groot, lerobot)

### Symptoms
```
ImportError: libopenblas.so.0: cannot open shared object file: No such file or directory
```

The PyTorch wheel from Jetson AI Lab depends on OpenBLAS, but it is not included in the `l4t-jetpack:r36.4.0` base image.

### Solution
Added `libopenblas-dev` to the system dependencies in both Dockerfiles:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    ...
    libopenblas-dev \
    ...
```

---

## Issue 6: Missing libcudss.so.0 (groot, lerobot)

### Symptoms
```
ImportError: libcudss.so.0: cannot open shared object file: No such file or directory
```

### Cause (Root Cause)
**Version mismatch between the base image (`l4t-jetpack:r36.4.0`) and the PyTorch wheel**:

- `l4t-jetpack:r36.4.0` is based on JetPack 6.0 and only includes the **basic** CUDA 12.6 libraries (cublas, cufft, etc.)
- Jetson AI Lab's `torch 2.9.1` is a recent build that requires `libcudss` (cuDSS - CUDA Direct Sparse Solver)
- `libcudss` is a separate NVIDIA package added in JetPack 6.1+, but it is not included in the base Docker image
- Although `apt install cudss` was installed separately on the host Jetson, Docker containers do not automatically inherit this
- This gap arises because NVIDIA's Jetson AI Lab pip index updates faster than the base Docker images

### Solution
Install the `nvidia-cudss-cu12` pip package and add it to `LD_LIBRARY_PATH`:

```dockerfile
# Install nvidia-cudss-cu12 (required by Jetson PyTorch, not included in l4t-jetpack base)
# --no-deps to avoid re-downloading cublas which is already in the base image
RUN uv pip install --no-deps nvidia-cudss-cu12
ENV LD_LIBRARY_PATH="/gr00t/.venv/lib/python3.10/site-packages/nvidia/cu12/lib:${LD_LIBRARY_PATH}"
```

**Note**: `--no-deps` is used to prevent redundant downloading of cublas (548MB) which already exists in the base image.

---

## Issue 7: Docker Hub Image Does Not Exist (Warning)

### Symptoms
```
Warning: pull access denied for robotis/groot-zenoh, repository does not exist or may require 'docker login'
Warning: pull access denied for robotis/lerobot-zenoh, repository does not exist or may require 'docker login'
```

The `groot` and `lerobot` images had not been pushed to Docker Hub yet, so the pull failed. It automatically fell back to a local build.

### Solution
Push to Docker Hub after a successful build:
```bash
docker push robotis/groot-zenoh:arm64
docker push robotis/lerobot-zenoh:arm64
```

---

## Build Warnings (Can Be Ignored)

### CMake Deprecation Warning
```
CMake Deprecation Warning at CMakeLists.txt:1 (cmake_minimum_required):
  Compatibility with CMake < 3.10 will be removed from a future version of CMake.
```
- Impact: None. Occurs in CMakeLists.txt for `test_utils` and `physical_ai_tools` packages.
- Recommendation: Update to `cmake_minimum_required(VERSION 3.14)` or higher.

### rclcpp Deprecated API Warning
```
warning: 'create_service' is deprecated: use rclcpp::QoS instead of rmw_qos_profile_t
```
- Impact: None. Build succeeds. Occurs in `rosbag_recorder/src/service_bag_recorder.cpp:51`.
- Recommendation: Migrate from `rmw_qos_profile_services_default` to using `rclcpp::QoS`.

### ESLint Warnings (physical_ai_manager)
```
src/components/ControlPanel.js Line 129:9: 'isReadyState' is assigned a value but never used
src/components/DatasetDownloadModal.js Line 17:27: 'useCallback' is defined but never used
src/components/PolicyDownloadModal.js Line 17:27: 'useCallback' is defined but never used
```
- Impact: None. React build succeeds.
- Recommendation: Clean up unused variables.

### ldconfig Empty File Warnings
```
/sbin/ldconfig.real: File /usr/lib/aarch64-linux-gnu/nvidia/libnvdla_runtime.so is empty, not checked.
```
- Impact: None. Known issue with the Jetson L4T base image. These are NVIDIA library stub files.

---

## Final Build Results

| Container | Image | PyTorch | CUDA | GPU | Status |
|-----------|-------|---------|------|-----|--------|
| physical_ai_server | robotis/physical-ai-server:arm64 | N/A (ROS2) | N/A | N/A | Built & Started |
| physical_ai_manager | robotis/physical-ai-manager:latest | N/A (React) | N/A | N/A | Built & Started |
| groot | robotis/groot-zenoh:arm64 | 2.9.1 | 12.6 | Orin 61.4GB | Built & Started |
| lerobot | robotis/lerobot-zenoh:arm64 | 2.9.1 | 12.6 | Orin 61.4GB | Built & Started |

---

## List of Modified Files

| File | Changes |
|------|---------|
| `.dockerignore` | Newly created - excludes large files from build context |
| `physical_ai_server/Dockerfile.arm64` | Added `--extra-index-url https://pypi.org/simple` (matplotlib) |
| `third_party/groot/Dockerfile.arm64` | Added decord source build, Jetson-only torch index, libopenblas, nvidia-cudss |
| `third_party/lerobot/Dockerfile.arm64` | Added Jetson-only torch index, torch reinstall step, libopenblas, nvidia-cudss |
