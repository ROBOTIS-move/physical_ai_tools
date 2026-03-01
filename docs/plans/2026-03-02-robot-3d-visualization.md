# Robot 3D Visualization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Inference/Record 페이지에서 URDF 기반 3D 로봇 모델을 렌더링하고, joint_trajectory 토픽 데이터에 따라 실시간으로 관절이 움직이는 시각화를 구현한다.

**Architecture:** React Three Fiber + urdf-loader로 3D 씬을 구성하고, rosbridge(roslibjs)를 통해 joint_states/joint_trajectory 토픽을 구독하여 `robot.setJointValue()`로 관절을 실시간 업데이트한다.

**Tech Stack:** React Three Fiber, @react-three/drei, urdf-loader, three.js (STLLoader), roslibjs

---

## 1. 기술 스택 조사 및 선택

### 1.1 후보 도구 비교

| 도구 | 설명 | 장점 | 단점 |
|------|------|------|------|
| **urdf-loader + React Three Fiber** | Three.js 기반 URDF 파서. React Three Fiber로 선언적 3D 렌더링 | 경량 (npm 패키지), React 생태계 통합, `setJointValue()` API 내장, STL/DAE/GLTF 지원, 커스텀 mesh loader 콜백 | React Three Fiber 통합에 약간의 커스텀 코드 필요, useLoader 직접 사용 불가 |
| **ros3djs** | ROS 공식 웹 시각화 라이브러리 | ROS 생태계 네이티브, URDF 지원 | 오래된 프로젝트 (유지보수 부족), React 통합 어려움, Three.js 구버전 의존 |
| **Foxglove Studio** | 웹 기반 로봇 데이터 시각화 플랫폼 | 풍부한 기능, URDF 지원, 팀 협업 | 별도 앱/iframe 임베딩 필요, 우리 UI에 자연스럽게 통합 어려움, 유료 플랜 |
| **Rerun** | 경량 시각화 도구 | 빠른 렌더링, 오픈소스 | 데스크톱 앱 중심, 웹 임베딩 제한적, React 통합 불가 |
| **RViz (iframe)** | RViz 웹 버전을 iframe으로 임베딩 | 완전한 ROS 시각화 | 별도 서버 필요, 무거움, UI 통합 어려움 |

### 1.2 선택: urdf-loader + React Three Fiber

**선택 이유:**
1. 이미 React 기반 SPA (physical_ai_manager)에 자연스럽게 통합 가능
2. 경량 — npm 패키지 2-3개 추가만으로 구현 가능
3. `robot.setJointValue(jointName, angle)` API로 관절 제어가 간단
4. STL mesh를 직접 로드하는 `loadMeshCb` 콜백 제공
5. 별도 서버/프로세스 불필요 — 기존 React 앱 안에서 동작
6. Three.js 생태계의 OrbitControls, 조명 등을 그대로 활용

---

## 2. URDF 및 Mesh 파일 분석

### 2.1 URDF 구조 (`ffw_sg2_follower.urdf`)

| 항목 | 수치 |
|------|------|
| 총 링크 | 58개 |
| 총 조인트 | 57개 |
| Fixed 조인트 | 28개 |
| **Revolute 조인트** | **26개** (가동) |
| **Prismatic 조인트** | **1개** (lift_joint) |
| **Continuous 조인트** | **3개** (바퀴) |
| 시각 메시가 있는 링크 | 44개 |
| 고유 STL 파일 | 31개 |

### 2.2 주요 가동 조인트 그룹

| 그룹 | 조인트 | 타입 |
|------|--------|------|
| Head | head_joint1, head_joint2 | revolute |
| Left Arm | arm_l_joint1~7 | revolute |
| Right Arm | arm_r_joint1~7 | revolute |
| Left Gripper | gripper_l_joint1~4 | revolute (joint2~4는 mimic) |
| Right Gripper | gripper_r_joint1~4 | revolute (joint2~4는 mimic) |
| Lift | lift_joint | prismatic |
| Wheels | left/right/rear_wheel_steer, left/right/rear_wheel_drive | revolute + continuous |

### 2.3 Mesh 파일 현황

**위치:** `/home/rc/workspace/physical_ai_tools/rosbag_recorder/config/ffw_description/meshes/`

| 디렉토리 | 파일 수 | 주요 파일 | 크기 |
|----------|---------|-----------|------|
| `ffw_sg2_rev1_follower/` | 8개 | base_mobile_assy.stl (5.8MB), lift_link.stl (897KB) | ~7.9MB |
| `common/follower/` | 18개 | arm 링크들 (1.3~2.2MB each), body_arm_assy.stl (4.5MB) | ~22MB |
| `common/rh_p12_rn_a/` | 5개 | gripper 부품 (6~25KB each) | ~53KB |
| **합계** | **31개** | | **~32MB** |

### 2.4 Mesh 충분성 평가

- **충분함**: 31개 STL 파일이 44개 시각 링크 중 대부분을 커버 (일부 링크는 동일 mesh 재사용)
- **누락**: `zedm.stl`과 `d405.stl` (카메라 모델)은 `file://` 절대 경로로 참조 → 별도 복사 필요하거나 생략 가능 (시각화에 큰 영향 없음)
- **크기**: 총 32MB — 초기 로딩에 2-5초 소요 예상 (로컬 네트워크). 캐싱 후 즉시 로드

### 2.5 URDF의 `package://` 경로 매핑

URDF에서 mesh를 참조하는 방식:
```
package://ffw_description/meshes/ffw_sg2_rev1_follower/base_mobile_assy.stl
```

웹에서 서빙할 때 매핑:
```
package://ffw_description/ → /urdf/ffw_description/
```

---

## 3. 파일 배치 전략

### 3.1 문제: URDF/mesh 파일 위치

현재 URDF와 mesh는 `rosbag_recorder/config/`에 있지만, 3D 시각화는 `physical_ai_manager` (React 앱)에서 수행해야 한다.

### 3.2 해결 방안 비교

| 방안 | 설명 | 장점 | 단점 |
|------|------|------|------|
| **A. Docker 볼륨 공유** | `physical_ai_manager` 컨테이너에서 `rosbag_recorder/config/`를 마운트하고 nginx로 서빙 | 파일 중복 없음, 원본 유지 | Docker 설정 변경 필요, nginx 설정 |
| **B. 빌드 시 복사** | React 빌드 시 `public/urdf/`로 복사 | 간단, 정적 파일로 서빙 | 파일 중복 (~32MB), URDF 변경 시 재빌드 |
| **C. API 서빙** | `physical_ai_server`에서 URDF/mesh를 HTTP API로 제공 | 서버 중심, 유연 | 추가 API 개발 필요 |

### 3.3 확정: 방안 A (Docker 볼륨 + nginx)

`physical_ai_manager`의 Docker 컨테이너에서 `rosbag_recorder/config/`를 읽기 전용으로 마운트하고, nginx에서 `/urdf/` 경로로 서빙한다.

```yaml
# docker-compose.yml (physical_ai_manager 서비스)
volumes:
  - ../rosbag_recorder/config/urdf:/usr/share/nginx/html/urdf/urdf:ro
  - ../rosbag_recorder/config/ffw_description:/usr/share/nginx/html/urdf/ffw_description:ro
```

이렇게 하면:
- `http://localhost/urdf/urdf/ffw_sg2_follower.urdf` → URDF 파일
- `http://localhost/urdf/ffw_description/meshes/...` → mesh 파일
- `package://ffw_description/` → `/urdf/ffw_description/`로 매핑

---

## 4. 데이터 흐름 (상세)

### 4.1 전체 흐름도

```
┌─────────────────────────────────────────────────────────────────┐
│                    physical_ai_manager (React)                   │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │ urdf-loader  │    │ rosbridge    │    │ React Three      │   │
│  │              │    │ (roslibjs)   │    │ Fiber Canvas     │   │
│  │ 1. URDF 파싱  │    │              │    │                  │   │
│  │ 2. STL 로드   │    │ joint_states │    │ 3D Scene:        │   │
│  │ 3. Robot 객체 │───▶│ 토픽 구독     │───▶│ - Robot mesh     │   │
│  │    생성       │    │              │    │ - OrbitControls  │   │
│  │              │    │ 10~30Hz      │    │ - Lighting       │   │
│  └──────────────┘    └──────┬───────┘    └──────────────────┘   │
│                             │                                    │
└─────────────────────────────┼────────────────────────────────────┘
                              │ WebSocket
                              │
┌─────────────────────────────┼────────────────────────────────────┐
│              rosbridge_server (physical_ai_server 컨테이너)       │
│                             │                                    │
│  ┌──────────────────────────┴───────────────────────────────┐   │
│  │                    ROS2 Topic Network                     │   │
│  │                                                           │   │
│  │  /robot/arm_left_follower/joint_states  (JointState)     │   │
│  │  /robot/arm_right_follower/joint_states (JointState)     │   │
│  │  /robot/head_follower/joint_states      (JointState)     │   │
│  │  /robot/lift_follower/joint_states      (JointState)     │   │
│  │                                                           │   │
│  │  또는 Inference 모드:                                      │   │
│  │  /leader/joint_trajectory_command_broadcaster_left/        │   │
│  │    joint_trajectory (JointTrajectory)                     │   │
│  │  /leader/joint_trajectory_command_broadcaster_right/       │   │
│  │    joint_trajectory (JointTrajectory)                     │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 단계별 상세 흐름

#### Phase 1: 초기 로딩 (앱 시작 시)

```
1. React 컴포넌트 마운트
   └─▶ URDFLoader.load('/urdf/urdf/ffw_sg2_follower.urdf')
       ├─▶ URDF XML 파싱 → 링크/조인트 트리 구성
       ├─▶ loadMeshCb 콜백으로 각 STL 파일 로드
       │   ├─ package://ffw_description/meshes/... → /urdf/ffw_description/meshes/...
       │   ├─ STLLoader로 각 .stl 파일 로드 (Three.js BufferGeometry)
       │   └─ material 색상 적용 (URDF의 <material> rgba 값)
       └─▶ URDFRobot 객체 반환 (Three.js Object3D 상속)
           ├─ robot.joints: { 'arm_l_joint1': URDFJoint, ... }
           └─ robot.links: { 'arm_l_link1': URDFLink, ... }

2. Three.js Scene에 robot 추가
   └─▶ scene.add(robot)
       ├─ OrbitControls 설정 (마우스 회전/줌)
       ├─ AmbientLight + DirectionalLight 설정
       └─ GridHelper (바닥 격자)

로딩 시간 예상: ~2-5초 (32MB STL, 로컬 네트워크)
캐싱 후: <1초
```

#### Phase 2: 실시간 관절 업데이트 (Inference/Record 중)

```
1. rosbridge를 통해 joint_states 토픽 구독
   └─▶ new ROSLIB.Topic({
         ros, name: '/robot/arm_left_follower/joint_states',
         messageType: 'sensor_msgs/msg/JointState'
       })

2. 메시지 수신 (10~100Hz)
   └─▶ msg = {
         name: ['arm_l_joint1', 'arm_l_joint2', ..., 'arm_l_joint7', 'gripper_l_joint1'],
         position: [0.1, -0.5, 0.3, ..., 0.8],
         velocity: [...],
         effort: [...]
       }

3. 관절 값 적용
   └─▶ msg.name.forEach((jointName, i) => {
         robot.setJointValue(jointName, msg.position[i]);
       })
       ├─ URDFJoint 내부에서 Three.js Transform 업데이트
       │   ├─ revolute: rotation around axis
       │   ├─ prismatic: translation along axis
       │   └─ continuous: rotation (no limits)
       └─ mimic 조인트 자동 처리 (urdf-loader 내장)

4. React Three Fiber 렌더 루프
   └─▶ requestAnimationFrame에서 자동 리렌더
       └─ 변경된 Transform이 GPU에 반영
```

#### Phase 3: Inference 모드 특화 (JointTrajectory)

```
Inference 시 InferenceManager가 publish하는 토픽:
  /leader/joint_trajectory_command_broadcaster_left/joint_trajectory
  /leader/joint_trajectory_command_broadcaster_right/joint_trajectory

메시지 구조 (trajectory_msgs/msg/JointTrajectory):
  {
    joint_names: ['arm_l_joint1', ..., 'arm_l_joint7', 'gripper_l_joint1'],
    points: [{
      positions: [0.1, -0.5, 0.3, ..., 0.8],
      velocities: [],
      time_from_start: { sec: 0, nanosec: 0 }
    }]
  }

적용:
  msg.joint_names.forEach((name, i) => {
    robot.setJointValue(name, msg.points[0].positions[i]);
  })
```

### 4.3 토픽 매핑 (URDF joint name ↔ ROS topic)

| ROS Topic | 메시지 타입 | URDF Joint Names |
|-----------|------------|------------------|
| `/robot/arm_left_follower/joint_states` | JointState | arm_l_joint1~7, gripper_l_joint1 |
| `/robot/arm_right_follower/joint_states` | JointState | arm_r_joint1~7, gripper_r_joint1 |
| `/robot/head_follower/joint_states` | JointState | head_joint1, head_joint2 |
| `/robot/lift_follower/joint_states` | JointState | lift_joint |
| (inference) `/.../joint_trajectory` | JointTrajectory | arm_l/r_joint1~7, gripper_l/r_joint1 |

---

## 5. UI 배치

### 5.1 위치 옵션

| 옵션 | 설명 | 장점 | 단점 |
|------|------|------|------|
| **A. ImageGrid 옆 (좌측 하단)** | 카메라 뷰 그리드 안에 하나의 셀로 배치 | 카메라 뷰와 함께 한눈에 | 카메라 뷰 공간 줄어듦 |
| **B. 우측 패널 내** | InferencePanel/InfoPanel 아래에 배치 | 기존 레이아웃 유지 | 패널이 좁아서 3D 뷰가 작음 |
| **C. 토글 가능한 오버레이** | 버튼 클릭 시 메인 영역에 오버레이로 표시 | 필요할 때만 표시, 공간 효율적 | 카메라 뷰를 가림 |
| **D. ImageGrid의 한 셀 교체** | 카메라 뷰 중 하나를 3D 뷰로 교체 | 자연스러운 통합 | 카메라 뷰 하나 손실 |

### 5.2 확정: 옵션 D (ImageGrid 셀 교체)

ImageGrid에서 카메라 뷰 중 하나를 3D Visualization으로 교체하는 방식.
사용자가 토글로 3D 뷰 ON/OFF 가능.

---

## 6. 구현 태스크

### Task 1: 의존성 설치 및 환경 설정

**Files:**
- Modify: `physical_ai_tools/physical_ai_manager/package.json`
- Modify: `physical_ai_tools/docker/docker-compose.yml` (physical_ai_manager 볼륨)

**Step 1:** npm 패키지 설치
```bash
cd physical_ai_tools/physical_ai_manager
npm install three @react-three/fiber @react-three/drei urdf-loader
```

**Step 2:** Docker 볼륨 설정 — URDF/mesh 파일을 nginx에서 서빙
```yaml
# docker-compose.yml physical_ai_manager 서비스에 추가
volumes:
  - ../rosbag_recorder/config/urdf:/usr/share/nginx/html/urdf/urdf:ro
  - ../rosbag_recorder/config/ffw_description:/usr/share/nginx/html/urdf/ffw_description:ro
```

**Step 3:** nginx 설정에서 `/urdf/` 경로에 대한 CORS 및 MIME type 설정 확인

---

### Task 2: URDF 로더 커스텀 훅 구현

**Files:**
- Create: `physical_ai_tools/physical_ai_manager/src/hooks/useUrdfRobot.js`

기능:
- URDFLoader로 URDF 파일 로드
- `package://` 경로를 웹 경로로 매핑하는 `loadMeshCb` 구현
- STLLoader로 .stl 파일 로드
- 로딩 상태 (loading, loaded, error) 관리
- robot 객체 반환

---

### Task 3: 3D Viewer 컴포넌트 구현

**Files:**
- Create: `physical_ai_tools/physical_ai_manager/src/components/RobotViewer3D.js`

기능:
- React Three Fiber `<Canvas>` 기반 3D 씬
- OrbitControls (마우스 회전/줌/팬)
- 조명 (AmbientLight + DirectionalLight)
- GridHelper (바닥 격자)
- URDF Robot 모델 렌더링
- 로딩 인디케이터

---

### Task 4: Joint State 실시간 구독 훅

**Files:**
- Create: `physical_ai_tools/physical_ai_manager/src/hooks/useJointStateSubscription.js`

기능:
- rosbridge를 통해 follower joint_states 토픽 구독
- 여러 토픽 (arm_left, arm_right, head, lift) 동시 구독
- 수신된 joint position을 robot 객체에 적용
- throttle 처리 (30fps 제한)로 렌더링 부하 관리

---

### Task 5: ImageGrid 또는 페이지에 3D Viewer 통합

**Files:**
- Modify: `physical_ai_tools/physical_ai_manager/src/pages/InferencePage.js`
- Modify: `physical_ai_tools/physical_ai_manager/src/pages/RecordPage.js`
- (또는) Modify: `physical_ai_tools/physical_ai_manager/src/components/ImageGrid.js`

기능:
- 3D Viewer ON/OFF 토글 버튼
- 페이지 레이아웃에 3D Viewer 영역 배치
- Inference/Record 양쪽 페이지에서 사용 가능

---

### Task 6: 누락 mesh 처리 및 최적화

**Files:**
- 관련 파일들

기능:
- `file://` 경로의 zedm.stl, d405.stl 처리 (복사 또는 fallback geometry)
- mimic 조인트 동기화 확인
- mesh 로딩 실패 시 fallback (빈 박스 geometry)
- 성능 최적화 (LOD, mesh 캐싱)

---

## 7. 리스크 및 고려사항

| 리스크 | 영향 | 대응 |
|--------|------|------|
| STL 32MB 로딩 시간 | 초기 로딩 2-5초 | 로딩 인디케이터 표시, 브라우저 캐싱 활용 |
| ARM64 환경에서 WebGL 성능 | 3D 렌더링 느릴 수 있음 | LOD, mesh simplification, 렌더링 FPS 제한 |
| rosbridge를 통한 joint_states 대역폭 | 100Hz × 4토픽 = 높은 메시지 빈도 | 클라이언트 측 throttle (30fps) |
| 카메라 mesh 누락 (zedm.stl, d405.stl) | 카메라 부분 빈 공간 | fallback box geometry 또는 파일 복사 |
| mimic 조인트 | gripper 동기화 | urdf-loader가 mimic 지원하는지 확인, 미지원 시 수동 구현 |

---

## 8. 추가 기능 (v1에 포함)

### 8.1 Trajectory 미리보기

**현재 상태:** `joint_trajectory` 토픽을 구독하여 첫 번째 point의 positions를 실시간으로 3D 모델에 반영하는 기본 구조는 구현됨. `joint_states`와 동일한 방식으로 관절 값을 적용.

**미구현 (향후 작업):**
- `points` 배열의 여러 포인트를 `time_from_start` 기반으로 순차 재생하는 애니메이션
- ghost/투명 모델로 현재 위치와 목표 위치를 시각적으로 구분
- trajectory 경로를 라인으로 시각화

### 8.2 녹화 재생 (Replay 페이지)

Replay 페이지에서 rosbag 데이터를 3D 뷰로 재생.
- ReplayPage에 이미 `jointTimestamps`, `jointNames`, `jointPositions` 데이터가 Redux에 존재
- `currentTime` 슬라이더와 동기화하여 해당 시점의 관절 위치를 3D 모델에 적용
- 기존 비디오 재생/차트와 함께 3D 뷰를 추가 패널로 배치

### 8.3 Replay 페이지 3D Viewer 배치

Replay 페이지는 ImageGrid가 없으므로 별도 배치:
- 비디오 영역 옆 또는 아래에 3D Viewer 패널 추가
- 토글 가능하게 하여 필요할 때만 표시
- `currentTime` 변경 시 `robot.setJointValue()` 호출로 동기화

---

## 9. 향후 확장 가능성

- **충돌 감지 시각화**: 관절 한계 초과 시 빨간색 표시
- **다중 로봇 타입**: robot_type에 따라 다른 URDF 로드
- **IK 시각화**: 역기구학 결과를 3D로 미리보기
