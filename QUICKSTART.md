# Quick Start — Jetson Orin GR00T 추론 환경

이 저장소를 받아 Jetson Orin 보드에서 GR00T 모델 추론을 Web UI 로 실행하는 최단 경로 가이드입니다. **Frontier OMY F3M (omy_f3m 베이스)** robot_type 을 default 로 사용하는 환경입니다.

## 1. 요구 사항

| 항목 | 값 |
|---|---|
| 보드 | NVIDIA Jetson AGX Orin (또는 Orin 시리즈, SM 8.7) |
| OS | JetPack 6.x (L4T R36.4 기준 검증) |
| 런타임 | Docker + Docker Compose v2 + NVIDIA Container Runtime |
| 디스크 | 약 60 GB 여유 (이미지 + HF 캐시 + 체크포인트) |
| 메모리 | 32 GB 이상 권장 (flash-attn 빌드 시 cicc 가 RAM 사용량 큼) |

NVIDIA Container Runtime 미설치 시:
```bash
sudo apt install nvidia-container-toolkit
sudo systemctl restart docker
```

---

## 2. 저장소 받기

```bash
git clone --recursive <THIS_REPO_URL> physical_ai_tools
cd physical_ai_tools
```

`--recursive` 가 필수입니다. `Isaac-GR00T`, `lerobot`, `zenoh_ros2_sdk` 서브모듈이 같이 받아져야 합니다.

이미 클론한 후 서브모듈을 안 받았다면:
```bash
git submodule update --init --recursive
```

---

## 3. 학습된 GR00T 체크포인트 배치

Frontier OMY F3M 환경의 체크포인트(예: 4000 step) 를 다음 위치에 배치하세요:

```
physical_ai_tools/third_party/groot/workspace/checkpoints/checkpoint-4000/
├── config.json
├── embodiment_id.json
├── model-00001-of-00002.safetensors
├── model-00002-of-00002.safetensors
├── experiment_cfg/
│   ├── conf.yaml
│   ├── dataset_statistics.json
│   ├── final_model_config.json
│   └── final_processor_config.json
└── ...
```

이 폴더는 컨테이너 안에서 `/workspace/checkpoints/checkpoint-4000` 으로 보입니다.

> 베이스 모델 (`nvidia/GR00T-N1.6-3B`) 은 첫 추론 시 HuggingFace 에서 자동 다운로드 됩니다 (`docker/huggingface/` 가 컨테이너 `~/.cache/huggingface` 로 마운트). 사전에 다운로드해 두려면 그 경로에 직접 풀어둬도 됩니다.

---

## 4. 컨테이너 기동

```bash
cd docker
./container.sh start
```

내부 동작:
- `docker compose up -d --build` 호출
- 4개 컨테이너 기동: `physical_ai_manager`, `physical_ai_server`, `groot_server`, `lerobot_server`
- **flash-attn 첫 빌드 시 ~100분 소요** (Orin 에서 cicc 컴파일이 무거움). 두 번째 부터는 캐시 사용
- `DEFAULT_ROBOT_TYPE=frontier_omy_f3m` 환경변수가 자동 주입되어 backend 가 시작 시 바로 robot_type 설정

빌드 진행 상태:
```bash
# 별도 터미널에서
docker compose logs -f physical_ai_server
docker stats
```

기동 완료 확인:
```bash
docker compose ps   # 4개 컨테이너 모두 Up (healthy)
```

---

## 5. Web UI 에서 추론 실행

브라우저에서:
- Jetson 보드 자체에서: `http://localhost`
- 같은 네트워크 다른 PC 에서: `http://<jetson_ip>` (포트 80)

### 5-1. robot_type 확인

상단 드롭다운에 `frontier_omy_f3m` 가 자동 선택되어 있어야 합니다 (DEFAULT_ROBOT_TYPE env 효과). 다른 로봇으로 바꾸고 싶으면 드롭다운에서 선택.

### 5-2. URDF 뷰어 확인

3D 뷰어에 omy_f3m 모형이 표시되어야 합니다. 표시 안 되면 [트러블슈팅 §URDF 안 나옴](#urdf-안-나옴) 참조.

### 5-3. Inference 페이지 진입

좌측 메뉴 → **Inference** 페이지.

### 5-4. Topic Monitor 확인

다음 토픽들이 OK 상태로 보여야 합니다:
- `cam_wrist`, `cam_top`, `cam_belly` (카메라 3개)
- `/joint_states` (follower state)
- `/leader/joint_states` (mirror — 추론 시작 후 활성)
- `/tf`

> 실 로봇 미연결 환경에서는 `mock_topic_publisher` 가 mock 데이터를 publish 하므로 위 토픽들이 정상 동작합니다.

### 5-5. 추론 트리거

| 입력 필드 | 값 |
|---|---|
| `model_path` | `/workspace/checkpoints/checkpoint-4000` |
| `embodiment_tag` | `new_embodiment` |
| `task_instruction` | 자연어 (예: `pick up the red cube`) |

**Start Inference** 버튼 클릭.

### 5-6. 동작 확인

- groot_server 가 `Action chunk: T=16, D=6` 로그 출력 (체크포인트가 6-DoF 학습본인 경우)
- `/leader/joint_trajectory` 토픽에 100Hz 로 액션 발행
- Web UI 의 trajectory preview 가 시각화

호스트 터미널 검증:
```bash
docker logs --tail 50 -f groot_server | grep "Action chunk"
docker exec physical_ai_server bash -c \
  "source /opt/ros/jazzy/setup.bash && \
   ros2 topic hz /leader/joint_trajectory"
```

---

## 6. 종료

```bash
cd docker
./container.sh stop     # 또는 docker compose down
```

호스트 디스크 절약을 위해 이미지까지 정리하려면:
```bash
docker compose down --rmi local
```

---

## 7. Default robot_type 변경

다른 로봇 환경으로 default 를 바꾸려면 `docker/docker-compose.yml` 의 `physical_ai_server.environment` 에서:

```yaml
- DEFAULT_ROBOT_TYPE=${DEFAULT_ROBOT_TYPE:-frontier_omy_f3m}
```

오른쪽 fallback 값을 원하는 robot_type 으로 변경하거나, 셸에서 환경변수로 override:
```bash
DEFAULT_ROBOT_TYPE=ffw_sg2_rev1 ./container.sh start
```

빈 문자열 (`DEFAULT_ROBOT_TYPE=`) 이면 자동 적용 비활성 — Web UI 에서 직접 선택해야 합니다.

---

## 8. 트러블슈팅

### Web UI 에 이미지/토픽이 안 보임

`physical_ai_server` 가 robot_type 을 못 받은 상태일 수 있습니다.
```bash
# 컨테이너 안에서 강제 적용
docker exec physical_ai_server bash -c \
  "source /opt/ros/jazzy/setup.bash && \
   source /root/ros2_ws/install/setup.bash && \
   ros2 service call /set_robot_type physical_ai_interfaces/srv/SetRobotType \
     \"{robot_type: 'frontier_omy_f3m'}\""
```
그 다음 브라우저 F5 새로고침. (DEFAULT_ROBOT_TYPE env 가 있으면 시작 시 자동 적용되므로 보통 발생 안 함)

### URDF 안 나옴

`physical_ai_manager/src/hooks/useUrdfRobot.js` 의 `URDF_ASSETS_BY_ROBOT_TYPE` 매핑에 사용 중인 robot_type 이 등록되어 있는지 확인. 새 robot_type 이면 항목 추가 후 manager 이미지 재빌드:
```bash
docker compose build physical_ai_manager
docker compose up -d physical_ai_manager
```

### `Cannot echo topic ... contains more than one type` 에러

Leader 토픽 type 충돌입니다. yaml 의 `joint_topic_list[leader_arm]` 토픽 이름과 `command_topic_list[leader_arm]` 토픽 이름이 **반드시 달라야** 합니다 (예: `/leader/joint_states` vs `/leader/joint_trajectory`). 같은 이름이면 mirror publisher (JointState) 와 command publisher (JointTrajectory) 가 충돌.

### flash-attn 빌드 실패

`groot_server` 이미지 빌드 시 `nvcc fatal : Unsupported gpu architecture 'compute_120'` 가 나오면 flash-attn 버전 문제입니다. `third_party/groot/Dockerfile.arm64` 의 다음 라인이 `v2.7.4.post1` tag 로 pin 되어 있는지 확인:
```dockerfile
&& git clone --depth 1 --branch v2.7.4.post1 https://github.com/Dao-AILab/flash-attention.git ...
```
Orin 의 CUDA 12.6 은 SM 120 미지원이라 main 브랜치를 쓰면 빌드 실패합니다.

### rosbridge 가 fastcdr 심볼 에러로 죽음

`physical_ai_server/Dockerfile.arm64` 가 `ros-${ROS_DISTRO}-fastcdr` (2.2.7) + `rosidl-typesupport-fastrtps-{c,cpp}` (3.6.3) 을 함께 설치하는지 확인. apt 기본 2.2.5 는 ABI 깨짐.

### Zenoh 디스커버리는 되는데 service call 이 silent 실패

`eclipse-zenoh` Python 패키지 버전이 `>=1.6.0,<1.7.0` 인지 확인. rmw_zenoh_cpp 가 번들로 가진 zenoh-c v1.6.x 와 일치해야 합니다.

---

## 9. 더 자세한 정보

- 시스템 아키텍처 / 4-컨테이너 토폴로지 / Zenoh 통신 구조: [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)
- Docker 빌드 함정 정리 (Jetson Orin 전용): [CLAUDE.md §7.1](CLAUDE.md)
- 새 robot_type 추가 자세한 가이드: [CLAUDE.md §5](CLAUDE.md) 참고
