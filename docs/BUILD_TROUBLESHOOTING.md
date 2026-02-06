# Docker Build Troubleshooting Guide (ARM64/Jetson)

이 문서는 ARM64(Jetson Orin) 환경에서 Docker 빌드 시 발생한 문제와 해결 방법을 기록합니다.

## Build Environment

- **Platform**: NVIDIA Jetson Orin (ARM64, aarch64)
- **JetPack**: 6.x (L4T R36.4)
- **Storage**: NVMe SSD mounted at `/home/rc/workspace` (229GB)
- **Docker**: with compose v2

---

## Issue 1: Build Context Too Large → Disk Full

### 증상
```
ERROR: failed to copy files: userspace copy failed: write .../model-00001-of-00002.safetensors: no space left on device
```

`physical_ai_server` Dockerfile의 `COPY .` 명령이 전체 프로젝트 디렉토리를 Docker 빌드 컨텍스트로 전송. `docker/huggingface/` (20GB+ 모델 파일)과 `third_party/` 서브모듈까지 포함되어 빌드 컨텍스트가 26GB+로 폭증.

### 해결
`.dockerignore` 파일을 프로젝트 루트에 생성하여 불필요한 파일 제외:

```
docker/huggingface/     # 모델 파일 (런타임에 볼륨 마운트)
docker/workspace/       # 워크스페이스 데이터
third_party/lerobot/lerobot/   # 서브모듈 소스
third_party/groot/Isaac-GR00T/ # 서브모듈 소스
**/*.safetensors        # 대형 모델 파일
**/*.pt, **/*.pth       # PyTorch 체크포인트
```

### 추가 조치
Docker 빌드 캐시가 128.7GB를 차지하고 있었음. `docker builder prune -af`로 정리 필요.

---

## Issue 2: pip install matplotlib 실패 (physical_ai_server)

### 증상
```
ERROR: Could not find a version that satisfies the requirement matplotlib (from versions: none)
ERROR: No matching distribution found for matplotlib
```

베이스 이미지(`robotis/ros:jazzy-ros-base-torch2.7.0-cuda12.8.0`)의 pip가 Jetson 전용 인덱스(`pypi.jetson-ai-lab.dev`)만 참조하도록 설정되어 있어서, 해당 인덱스에 matplotlib가 없음.

### 해결
`physical_ai_server/Dockerfile.arm64`에서 PyPI를 추가 인덱스로 지정:

```dockerfile
# 변경 전
RUN pip install psutil matplotlib

# 변경 후
RUN pip install psutil matplotlib --extra-index-url https://pypi.org/simple
```

---

## Issue 3: decord==0.6.0 ARM64 wheel 없음 (groot)

### 증상
```
Because decord==0.6.0 has no wheels with a matching platform tag (e.g., manylinux_2_35_aarch64)
and you require decord==0.6.0, we can conclude that your requirements are unsatisfiable.

hint: Wheels are available for decord (v0.6.0) on the following platforms: manylinux2010_x86_64, win_amd64
```

`decord` 패키지는 x86_64와 Windows용 pre-built wheel만 제공. ARM64(Jetson)에서는 소스 빌드 필요.

### 해결
`third_party/groot/Dockerfile.arm64`에서 decord를 pip 목록에서 제거하고 소스 빌드로 대체:

```dockerfile
# decord를 pip install 목록에서 제거하고, 별도로 소스에서 빌드
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

**참고**: CUDA 가속 디코딩(`-DUSE_CUDA=ON`)은 추가 CUDA 헤더가 필요할 수 있음. CPU 모드로도 충분히 동작.

---

## Issue 4: uv가 PyPI에서 CPU 버전 PyTorch 설치 (groot, lerobot)

### 증상
```
PyTorch: 2.10.0+cpu
CUDA available: False
```

컨테이너에서 `torch.cuda.is_available()`이 `False` 반환.

### 원인
`--extra-index-url https://pypi.org/simple`가 지정되면 `uv`가 PyPI의 CPU wheel을 Jetson AI Lab 인덱스의 CUDA wheel보다 우선 선택.

추가로, lerobot의 `uv pip install ".[smolvla,xvla,hilserl,async,peft]"` 실행 시 의존성으로 torch가 PyPI CPU 버전으로 덮어쓰기됨.

### 해결
1. **torch 설치 시 Jetson 인덱스만 사용** (`--extra-index-url` 제거):
```dockerfile
RUN uv pip install torch torchvision \
    --index-url https://pypi.jetson-ai-lab.io/jp6/cu126/+simple
```

2. **lerobot: 의존성 설치 후 Jetson CUDA torch 재설치**:
```dockerfile
RUN uv pip install --no-cache ".[smolvla,xvla,hilserl,async,peft]"
# Reinstall Jetson CUDA PyTorch (lerobot deps may overwrite with CPU version from PyPI)
RUN uv pip install --reinstall torch torchvision \
    --index-url https://pypi.jetson-ai-lab.io/jp6/cu126/+simple
```

---

## Issue 5: libopenblas.so.0 누락 (groot, lerobot)

### 증상
```
ImportError: libopenblas.so.0: cannot open shared object file: No such file or directory
```

Jetson AI Lab의 PyTorch wheel이 OpenBLAS에 의존하지만, `l4t-jetpack:r36.4.0` 베이스 이미지에 포함되지 않음.

### 해결
두 Dockerfile의 시스템 의존성에 `libopenblas-dev` 추가:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    ...
    libopenblas-dev \
    ...
```

---

## Issue 6: libcudss.so.0 누락 (groot, lerobot)

### 증상
```
ImportError: libcudss.so.0: cannot open shared object file: No such file or directory
```

### 원인 (근본 원인)
**베이스 이미지(`l4t-jetpack:r36.4.0`)와 PyTorch wheel의 버전 불일치**:

- `l4t-jetpack:r36.4.0`은 JetPack 6.0 기반으로 CUDA 12.6 **기본** 라이브러리(cublas, cufft 등)만 포함
- Jetson AI Lab의 `torch 2.9.1`은 최신 빌드로 `libcudss`(cuDSS - CUDA Direct Sparse Solver)를 필요로 함
- `libcudss`는 JetPack 6.1+ 에서 추가된 별도 NVIDIA 패키지이지만, 베이스 Docker 이미지에는 미포함
- 호스트 Jetson에는 `apt install cudss`로 별도 설치되어 있지만, Docker 컨테이너는 이를 자동 상속하지 않음
- NVIDIA의 Jetson AI Lab pip 인덱스가 베이스 Docker 이미지보다 더 빠르게 업데이트되면서 생기는 gap

### 해결
`nvidia-cudss-cu12` pip 패키지를 설치하고 `LD_LIBRARY_PATH`에 추가:

```dockerfile
# Install nvidia-cudss-cu12 (required by Jetson PyTorch, not included in l4t-jetpack base)
# --no-deps to avoid re-downloading cublas which is already in the base image
RUN uv pip install --no-deps nvidia-cudss-cu12
ENV LD_LIBRARY_PATH="/gr00t/.venv/lib/python3.10/site-packages/nvidia/cu12/lib:${LD_LIBRARY_PATH}"
```

**참고**: `--no-deps`를 사용하여 이미 베이스 이미지에 있는 cublas (548MB) 중복 다운로드를 방지.

---

## Issue 7: Docker Hub 이미지 미존재 (Warning)

### 증상
```
Warning: pull access denied for robotis/groot-zenoh, repository does not exist or may require 'docker login'
Warning: pull access denied for robotis/lerobot-zenoh, repository does not exist or may require 'docker login'
```

`groot`과 `lerobot` 이미지가 Docker Hub에 아직 push되지 않아서 pull 실패. 자동으로 로컬 빌드로 fallback됨.

### 해결
빌드 성공 후 Docker Hub에 push하면 해결:
```bash
docker push robotis/groot-zenoh:arm64
docker push robotis/lerobot-zenoh:arm64
```

---

## Build Warnings (무시 가능)

### CMake Deprecation Warning
```
CMake Deprecation Warning at CMakeLists.txt:1 (cmake_minimum_required):
  Compatibility with CMake < 3.10 will be removed from a future version of CMake.
```
- 영향: 없음. `test_utils`, `physical_ai_tools` 패키지의 CMakeLists.txt에서 발생.
- 권장: `cmake_minimum_required(VERSION 3.14)` 이상으로 업데이트.

### rclcpp Deprecated API Warning
```
warning: 'create_service' is deprecated: use rclcpp::QoS instead of rmw_qos_profile_t
```
- 영향: 없음. 빌드 성공. `rosbag_recorder/src/service_bag_recorder.cpp:51`에서 발생.
- 권장: `rmw_qos_profile_services_default` 대신 `rclcpp::QoS` 사용으로 마이그레이션.

### ESLint Warnings (physical_ai_manager)
```
src/components/ControlPanel.js Line 129:9: 'isReadyState' is assigned a value but never used
src/components/DatasetDownloadModal.js Line 17:27: 'useCallback' is defined but never used
src/components/PolicyDownloadModal.js Line 17:27: 'useCallback' is defined but never used
```
- 영향: 없음. React 빌드 성공.
- 권장: 미사용 변수 정리.

### ldconfig Empty File Warnings
```
/sbin/ldconfig.real: File /usr/lib/aarch64-linux-gnu/nvidia/libnvdla_runtime.so is empty, not checked.
```
- 영향: 없음. Jetson L4T 베이스 이미지의 알려진 이슈. NVIDIA 라이브러리 stub 파일.

---

## 최종 빌드 결과

| Container | Image | PyTorch | CUDA | GPU | Status |
|-----------|-------|---------|------|-----|--------|
| physical_ai_server | robotis/physical-ai-server:arm64 | N/A (ROS2) | N/A | N/A | Built & Started |
| physical_ai_manager | robotis/physical-ai-manager:latest | N/A (React) | N/A | N/A | Built & Started |
| groot | robotis/groot-zenoh:arm64 | 2.9.1 | 12.6 | Orin 61.4GB | Built & Started |
| lerobot | robotis/lerobot-zenoh:arm64 | 2.9.1 | 12.6 | Orin 61.4GB | Built & Started |

---

## 변경된 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `.dockerignore` | 신규 생성 - 빌드 컨텍스트에서 대형 파일 제외 |
| `physical_ai_server/Dockerfile.arm64` | `--extra-index-url https://pypi.org/simple` 추가 (matplotlib) |
| `third_party/groot/Dockerfile.arm64` | decord 소스 빌드, Jetson-only torch index, libopenblas, nvidia-cudss 추가 |
| `third_party/lerobot/Dockerfile.arm64` | Jetson-only torch index, torch 재설치 단계, libopenblas, nvidia-cudss 추가 |
