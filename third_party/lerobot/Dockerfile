# LeRobot Docker Container with Zenoh Communication Support
# This container provides isolated LeRobot environment with Zenoh-based communication
# for training and inference commands from physical_ai_server (ROS2)
#
# Build context: physical_ai_tools/third_party/lerobot/
# Usage: docker build -t robotis/lerobot-zenoh:latest .

FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Set up locale
RUN apt-get update && apt-get install -y locales \
    && locale-gen en_US en_US.UTF-8 \
    && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
    && rm -rf /var/lib/apt/lists/*
ENV LANG=en_US.UTF-8

# Install system dependencies (cmake, ninja-build, pkg-config required for egl-probe)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    wget \
    ca-certificates \
    cmake \
    pkg-config \
    ninja-build \
    libglib2.0-0 \
    libegl1-mesa \
    libegl1-mesa-dev \
    libgl1-mesa-glx \
    libgles2-mesa \
    ffmpeg \
    libusb-1.0-0-dev \
    speech-dispatcher \
    libgeos-dev \
    portaudio19-dev \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Create working directory for LeRobot
WORKDIR /lerobot

# Create virtual environment
RUN uv venv /lerobot/.venv --python 3.11

# Set virtual environment as default
ENV VIRTUAL_ENV=/lerobot/.venv
ENV PATH="/lerobot/.venv/bin:$PATH"

# Copy LeRobot source and install dependencies
# Build context is third_party/lerobot/, so paths are relative to that
COPY lerobot/setup.py lerobot/pyproject.toml lerobot/README.md lerobot/MANIFEST.in ./
COPY lerobot/src/ ./src/

# Install LeRobot with all dependencies
RUN uv pip install --no-cache ".[all]"

# Copy the rest of LeRobot (configs, tests, etc.)
COPY lerobot/ ./

# Zenoh dependencies (zenoh_ros2_sdk mounted as volume at /zenoh_sdk)
# json5 required for zenoh_ros2_sdk
RUN uv pip install eclipse-zenoh>=1.0.0 rosbags>=0.11.0 GitPython>=3.1.18 json5>=0.9.14 \
    && mkdir -p /zenoh_sdk

# Create application directory for Zenoh server
WORKDIR /app

# Copy entrypoint and executor scripts from build context
COPY entrypoint.sh /entrypoint.sh
COPY executor.py /app/executor.py

# Make entrypoint executable
RUN chmod +x /entrypoint.sh

# Environment variables for HuggingFace cache (mapped via volume)
ENV HF_HOME=/root/.cache/huggingface
ENV HF_LEROBOT_HOME=/root/.cache/huggingface/lerobot
ENV TORCH_HOME=/root/.cache/torch

# Zenoh configuration
ENV ZENOH_ROUTER_IP=127.0.0.1
ENV ZENOH_ROUTER_PORT=7447
ENV ZENOH_SHM_ENABLED=true
ENV ZENOH_SDK_PATH=/zenoh_sdk

# Shared Memory configuration for Zenoh
ENV ZENOH_TRANSPORT_SHM_ENABLED=true

# Default working directory
WORKDIR /lerobot

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import zenoh; print('Zenoh OK')" || exit 1

# Entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Default command: start Zenoh server for receiving training/inference commands
CMD ["server"]
