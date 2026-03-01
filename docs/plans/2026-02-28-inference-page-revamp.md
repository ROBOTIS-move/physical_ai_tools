# Inference Page Revamp Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Inference 페이지에 전용 컨트롤 패널(Start/Stop/Clear + Record 토글)을 만들고, 기존 ControlPanel을 RecordControlPanel로 리네임하여 Record/Inference 페이지를 완전히 분리한다.

**Architecture:** SendCommand.srv에 5개 커맨드를 추가하고, TaskStatus.msg에 PAUSED phase를 추가한다. InferenceManager에 pause/resume 기능을 넣고, physical_ai_server에서 새 커맨드들을 처리한다. 프론트엔드에서는 InferenceControlPanel 컴포넌트를 새로 만들고, 기존 ControlPanel을 RecordControlPanel로 리네임한다. 두 패널 모두 높이를 h-56에서 h-36으로 줄여 카메라 영상 영역을 확대한다.

**Tech Stack:** ROS2 interfaces (msg/srv), Python (physical_ai_server), React + Tailwind CSS + clsx (physical_ai_manager)

---

## State Machine

```
IDLE → [Start] → LOADING → INFERENCING ⇄ [Stop/Start] ⇄ PAUSED
                                ↕                           ↕
                          [Record ON/OFF]            [Record ON/OFF]

         ↑
         └──────── [Clear] ←── INFERENCING / PAUSED 어디서든
```

- Start: IDLE → START_INFERENCE, PAUSED → RESUME_INFERENCE (policy path 변경 시 자동 Clear + START_INFERENCE)
- Stop: INFERENCING → STOP_INFERENCE (모델 유지, 추론 루프만 멈춤)
- Clear: INFERENCING/PAUSED → FINISH (기존 커맨드 재활용, 전체 리소스 정리)
- Record ON: START_INFERENCE_RECORD (inference 상태와 독립, INFERENCING/PAUSED 모두 가능)
- Record Save: STOP_INFERENCE_RECORD (녹화 중지 + 저장)
- Record Discard: CANCEL_INFERENCE_RECORD (녹화 중지 + 버림)

## Button Enable Matrix

| Phase        | Start | Stop | Clear | Record |
|-------------|-------|------|-------|--------|
| IDLE/READY  | ON    | OFF  | OFF   | OFF    |
| LOADING     | OFF   | OFF  | OFF   | OFF    |
| INFERENCING | OFF   | ON   | ON    | ON     |
| PAUSED      | ON    | OFF  | ON    | ON     |

Recording 중에는 Record 버튼이 Save/Discard 버튼으로 변환됨.

---

### Task 1: ROS2 Interface 변경 (SendCommand.srv + TaskStatus.msg)

**Files:**
- Modify: `physical_ai_interfaces/srv/SendCommand.srv`
- Modify: `physical_ai_interfaces/msg/TaskStatus.msg`

**Step 1: SendCommand.srv에 5개 커맨드 추가**

```srv
########################################
# Constants
########################################
# command
uint8 IDLE = 0
uint8 START_RECORD = 1
uint8 START_INFERENCE = 2
uint8 STOP = 3
uint8 MOVE_TO_NEXT = 4
uint8 RERECORD = 5
uint8 FINISH = 6
uint8 SKIP_TASK = 7
uint8 CANCEL = 8
uint8 CONVERT_MP4 = 9
uint8 STOP_INFERENCE = 10
uint8 RESUME_INFERENCE = 11
uint8 START_INFERENCE_RECORD = 12
uint8 STOP_INFERENCE_RECORD = 13
uint8 CANCEL_INFERENCE_RECORD = 14

uint8 command
TaskInfo task_info
---
bool success
string message
```

**Step 2: TaskStatus.msg에 PAUSED 추가**

```msg
uint8 INFERENCING = 6
uint8 CONVERTING = 7
uint8 LOADING = 8
uint8 PAUSED = 9
```

phase 주석도 업데이트:
```
uint8 phase  # (0: READY, 1: WARMING_UP, 2: RESETTING, 3: RECORDING, 4: SAVING, 5: STOPPED, 6: INFERENCING, 7: CONVERTING, 8: LOADING, 9: PAUSED)
```

**Step 3: colcon build로 인터페이스 재빌드**

Run: `cd /root/ros2_ws && colcon build --packages-select physical_ai_interfaces`

**Step 4: Commit**

```bash
git add physical_ai_interfaces/
git commit -m "feat: add inference control commands and PAUSED phase to ROS2 interfaces"
```

---

### Task 2: 프론트엔드 상수 업데이트

**Files:**
- Modify: `physical_ai_manager/src/constants/taskCommand.js`
- Modify: `physical_ai_manager/src/constants/taskPhases.js`

**Step 1: taskCommand.js에 새 커맨드 추가**

```javascript
const TaskCommand = {
  NONE: 0,
  START_RECORD: 1,
  START_INFERENCE: 2,
  STOP: 3,
  NEXT: 4,
  RERECORD: 5,
  FINISH: 6,
  SKIP_TASK: 7,
  CANCEL: 8,
  CONVERT_MP4: 9,
  STOP_INFERENCE: 10,
  RESUME_INFERENCE: 11,
  START_INFERENCE_RECORD: 12,
  STOP_INFERENCE_RECORD: 13,
  CANCEL_INFERENCE_RECORD: 14,
};
```

**Step 2: taskPhases.js에 LOADING, PAUSED 추가**

```javascript
const TaskPhase = {
  READY: 0,
  WARMING_UP: 1,
  RESETTING: 2,
  RECORDING: 3,
  SAVING: 4,
  STOPPED: 5,
  INFERENCING: 6,
  CONVERTING: 7,
  LOADING: 8,
  PAUSED: 9,
  IDLE: 0,
};
```

**Step 3: Commit**

```bash
git add physical_ai_manager/src/constants/
git commit -m "feat: add inference control constants to frontend"
```

---

### Task 3: useRosServiceCaller에 새 커맨드 추가

**Files:**
- Modify: `physical_ai_manager/src/hooks/useRosServiceCaller.js`

**Step 1: sendRecordCommand switch에 새 case 추가**

`useRosServiceCaller.js`의 `sendRecordCommand` 함수 내 switch문 (89-122행)에 다음 case들을 추가:

```javascript
          case 'stop_inference':
            command_enum = TaskCommand.STOP_INFERENCE;
            break;
          case 'resume_inference':
            command_enum = TaskCommand.RESUME_INFERENCE;
            break;
          case 'start_inference_record':
            command_enum = TaskCommand.START_INFERENCE_RECORD;
            break;
          case 'stop_inference_record':
            command_enum = TaskCommand.STOP_INFERENCE_RECORD;
            break;
          case 'cancel_inference_record':
            command_enum = TaskCommand.CANCEL_INFERENCE_RECORD;
            break;
```

**Step 2: Commit**

```bash
git add physical_ai_manager/src/hooks/useRosServiceCaller.js
git commit -m "feat: add inference control commands to service caller hook"
```

---

### Task 4: ControlPanel → RecordControlPanel 리네임

**Files:**
- Rename: `physical_ai_manager/src/components/ControlPanel.js` → `RecordControlPanel.js`
- Modify: `physical_ai_manager/src/pages/RecordPage.js` (import 변경)

**Step 1: 파일 리네임**

```bash
cd physical_ai_manager/src/components
mv ControlPanel.js RecordControlPanel.js
```

**Step 2: RecordControlPanel.js 내부 수정**

- `export default function ControlPanel()` → `export default function RecordControlPanel()`
- Record 전용이므로 `page` 분기 로직 제거 (항상 Record로 동작)
- `handleControlCommand`에서 Start 시 항상 `sendRecordCommand('start_record')` 호출
- `isRunning` 조건에서 `TaskPhase.INFERENCING` 제거 (Record 전용이므로 RECORDING만)
- 높이를 `h-56` → `h-36`으로 변경
- 버튼 아이콘 크기 축소: `w-20 h-20` → `w-12 h-12`, 아이콘 clamp 축소

**Step 3: RecordPage.js import 변경**

```javascript
// Before
import ControlPanel from '../components/ControlPanel';
// After
import RecordControlPanel from '../components/RecordControlPanel';
```

JSX에서도 `<ControlPanel />` → `<RecordControlPanel />`

**Step 4: Commit**

```bash
git add physical_ai_manager/src/components/RecordControlPanel.js
git add physical_ai_manager/src/pages/RecordPage.js
git rm physical_ai_manager/src/components/ControlPanel.js
git commit -m "refactor: rename ControlPanel to RecordControlPanel for record page"
```

---

### Task 5: InferenceControlPanel 컴포넌트 생성

**Files:**
- Create: `physical_ai_manager/src/components/InferenceControlPanel.js`
- Modify: `physical_ai_manager/src/pages/InferencePage.js` (import 변경)

**Step 1: InferenceControlPanel.js 생성**

핵심 구조:

```jsx
export default function InferenceControlPanel() {
  // Redux state
  const taskInfo = useSelector((state) => state.tasks.taskInfo);
  const taskStatus = useSelector((state) => state.tasks.taskStatus);
  const page = useSelector((state) => state.ui.currentPage);

  // Local state
  const [isRecording, setIsRecording] = useState(false);
  const [lastPolicyPath, setLastPolicyPath] = useState('');

  const { sendRecordCommand } = useRosServiceCaller();

  // Phase helpers
  const phase = taskStatus.phase;
  const isIdle = phase === TaskPhase.READY || phase === TaskPhase.IDLE;
  const isLoading = phase === TaskPhase.LOADING;
  const isInferencing = phase === TaskPhase.INFERENCING;
  const isPaused = phase === TaskPhase.PAUSED;
  const isModelLoaded = isInferencing || isPaused;

  // Button enable logic
  const startEnabled = isIdle || isPaused;
  const stopEnabled = isInferencing;
  const clearEnabled = isModelLoaded;
  const recordEnabled = isModelLoaded && !isRecording;

  // Start handler: IDLE → start_inference, PAUSED → resume_inference
  // If policy path changed while PAUSED, send start_inference (server will clear + reload)
  const handleStart = async () => {
    if (isPaused && taskInfo.policyPath === lastPolicyPath) {
      await sendRecordCommand('resume_inference');
    } else {
      setLastPolicyPath(taskInfo.policyPath);
      await sendRecordCommand('start_inference');
    }
  };

  // Stop handler
  const handleStop = () => sendRecordCommand('stop_inference');

  // Clear handler (uses existing FINISH command)
  const handleClear = () => sendRecordCommand('finish');

  // Record handlers
  const handleRecordStart = () => {
    sendRecordCommand('start_inference_record');
    setIsRecording(true);
  };
  const handleRecordSave = () => {
    sendRecordCommand('stop_inference_record');
    setIsRecording(false);
  };
  const handleRecordDiscard = () => {
    sendRecordCommand('cancel_inference_record');
    setIsRecording(false);
  };

  // Buttons config
  const controlButtons = [
    {
      label: 'Start',
      icon: MdPlayArrow,
      color: '#1976d2',
      enabled: startEnabled,
      handler: handleStart,
      shortcut: 'Space',
    },
    {
      label: 'Stop',
      icon: MdStop,
      color: '#f57c00',
      enabled: stopEnabled,
      handler: handleStop,
      shortcut: 'Ctrl+Shift+S',
    },
    {
      label: 'Clear',
      icon: MdDelete,
      color: '#d32f2f',
      enabled: clearEnabled,
      handler: handleClear,
      shortcut: 'Escape',
    },
  ];

  // ... render (compact h-36 layout)
}
```

버튼 레이아웃:
- 왼쪽: Start / Stop / Clear (3개 버튼, flex-[2])
- 중앙: Phase 상태 표시 + 경과 시간 (flex-[1])
- 오른쪽 하단 또는 중앙 아래: Record 토글 영역

Record 영역 UI:
- 녹화 OFF: `[● Record]` 버튼 (빨간 원 아이콘)
- 녹화 ON: `[✓ Save] [✕ Discard]` 두 버튼 + 깜빡이는 REC 표시

높이: `h-36` (기존 h-56에서 축소)

Phase 표시 메시지:
```javascript
const phaseGuideMessages = {
  [TaskPhase.READY]: 'Ready to start',
  [TaskPhase.LOADING]: 'Loading model...',
  [TaskPhase.INFERENCING]: 'Inferencing',
  [TaskPhase.PAUSED]: 'Paused',
};
```

키보드 단축키:
- Space: Start (startEnabled일 때)
- Ctrl+Shift+S: Stop (stopEnabled일 때)
- Escape: Clear (clearEnabled일 때)
- R: Record 토글 (recordEnabled일 때)

**Step 2: InferencePage.js 수정**

```javascript
// Before
import ControlPanel from '../components/ControlPanel';
// After
import InferenceControlPanel from '../components/InferenceControlPanel';
```

JSX: `<ControlPanel />` → `<InferenceControlPanel />`

**Step 3: Commit**

```bash
git add physical_ai_manager/src/components/InferenceControlPanel.js
git add physical_ai_manager/src/pages/InferencePage.js
git commit -m "feat: add InferenceControlPanel with Start/Stop/Clear and Record toggle"
```

---

### Task 6: InferenceManager에 pause/resume 추가

**Files:**
- Modify: `physical_ai_server/physical_ai_server/inference/inference_manager.py`

**Step 1: pause/resume 메서드 및 is_paused property 추가**

`__init__`에 `self._paused = False` 추가.

```python
@property
def is_paused(self) -> bool:
    return self._paused and self._running

def pause(self):
    """Pause inference loop. Model stays loaded, stops requesting chunks."""
    self._paused = True
    with self._buffer_lock:
        self._action_buffer.clear()
    self._last_action = None
    logger.info(f"InferenceManager paused ({self._service_prefix})")

def resume(self, task_instruction: str = ""):
    """Resume inference loop. Starts requesting chunks again."""
    if task_instruction:
        self._task_instruction = task_instruction
    self._paused = False
    self._request_chunk_async()
    logger.info(f"InferenceManager resumed ({self._service_prefix})")
```

**Step 2: pop_action에서 paused 체크**

`pop_action` 메서드 시작 부분에 추가:

```python
def pop_action(self) -> Optional[dict]:
    if self._paused:
        return None
    # ... (기존 로직)
```

**Step 3: _request_chunk_async에서 paused 체크**

```python
def _request_chunk_async(self):
    if not self._running or self._paused:
        return
    # ... (기존 로직)
```

**Step 4: stop에서 paused 리셋**

`stop()` 메서드에 `self._paused = False` 추가.

**Step 5: Commit**

```bash
git add physical_ai_server/physical_ai_server/inference/inference_manager.py
git commit -m "feat: add pause/resume to InferenceManager"
```

---

### Task 7: physical_ai_server에 새 커맨드 핸들러 추가

**Files:**
- Modify: `physical_ai_server/physical_ai_server/physical_ai_server.py`

**Step 1: _inference_timer_callback에 PAUSED 상태 발행 추가**

`_inference_timer_callback` (569행)에서 기존 INFERENCING 발행 부분 앞에 PAUSED 체크 추가:

```python
def _inference_timer_callback(self):
    if not self.on_inference or self.inference_manager is None:
        return

    current_status = TaskStatus()

    # Handle async load error
    load_error = self.inference_manager.load_error
    if load_error:
        self.get_logger().error(f'Inference load failed: {load_error}')
        current_status.phase = TaskStatus.READY
        current_status.error = load_error
        self.communicator.publish_status(status=current_status)
        self._stop_groot_inference()
        self.on_inference = False
        return

    # Still loading policy
    if self.inference_manager.is_loading:
        current_status.phase = TaskStatus.LOADING
        self.communicator.publish_status(status=current_status)
        return

    # Paused — model loaded but not inferencing
    if self.inference_manager.is_paused:
        current_status.phase = TaskStatus.PAUSED
        self.communicator.publish_status(status=current_status)
        return

    # Ready — pop action and publish
    joint_msg_datas = self.inference_manager.pop_action()
    if joint_msg_datas is not None:
        self.communicator.publish_action(joint_msg_datas)

    current_status.phase = TaskStatus.INFERENCING
    self.communicator.publish_status(status=current_status)
```

**Step 2: user_interaction_callback에 새 커맨드 핸들러 추가**

기존 `else:` 블록 (943행) 내부, `on_recording or on_inference` 분기 안에 새 커맨드 핸들러 추가:

```python
                    elif request.command == SendCommand.Request.STOP_INFERENCE:
                        if self.inference_manager is not None:
                            self.inference_manager.pause()
                            response.success = True
                            response.message = 'Inference paused'
                        else:
                            response.success = False
                            response.message = 'No inference session active'

                    elif request.command == SendCommand.Request.RESUME_INFERENCE:
                        if self.inference_manager is not None:
                            task_instruction = (
                                request.task_info.task_instruction[0]
                                if request.task_info.task_instruction
                                else ''
                            )
                            self.inference_manager.resume(task_instruction=task_instruction)
                            response.success = True
                            response.message = 'Inference resumed'
                        else:
                            response.success = False
                            response.message = 'No inference session active'

                    elif request.command == SendCommand.Request.START_INFERENCE_RECORD:
                        self.get_logger().info('Starting recording during inference')
                        if self.data_manager is not None:
                            self.data_manager.start_recording()
                            self.on_recording = True
                            self.communicator.publish_action_event('start')
                            response.success = True
                            response.message = 'Recording started during inference'
                        else:
                            response.success = False
                            response.message = 'Data manager not initialized'

                    elif request.command == SendCommand.Request.STOP_INFERENCE_RECORD:
                        self.get_logger().info('Stopping and saving recording during inference')
                        if self.data_manager and self.data_manager.is_recording():
                            self.stop_recording_and_save()
                            self.on_recording = False
                            self.communicator.publish_action_event('finish')
                            response.success = True
                            response.message = 'Recording saved'
                        else:
                            response.success = False
                            response.message = 'Not currently recording'

                    elif request.command == SendCommand.Request.CANCEL_INFERENCE_RECORD:
                        self.get_logger().info('Cancelling recording during inference')
                        if self.data_manager and self.data_manager.is_recording():
                            self.cancel_current_recording()
                            self.on_recording = False
                            self.communicator.publish_action_event('cancel')
                            response.success = True
                            response.message = 'Recording cancelled'
                        else:
                            response.success = False
                            response.message = 'Not currently recording'
```

**Step 3: START_INFERENCE 핸들러 수정 (PAUSED에서 policy path 변경 시 자동 Clear + 재로드)**

기존 `START_INFERENCE` 핸들러 (820행)에서, 이미 inference_manager가 존재하는 경우 먼저 정리:

```python
            elif request.command == SendCommand.Request.START_INFERENCE:
                self.operation_mode = 'inference'
                task_info = request.task_info

                # If already have an inference session, clean it up first
                if self.inference_manager is not None:
                    self._stop_groot_inference()

                self.init_robot_control_parameters_from_user_task(task_info)
                # ... (기존 로직 계속)
```

**Step 4: Commit**

```bash
git add physical_ai_server/physical_ai_server/physical_ai_server.py
git commit -m "feat: handle inference pause/resume and record toggle commands in server"
```

---

### Task 8: RecordControlPanel 높이 축소 + 정리

**Files:**
- Modify: `physical_ai_manager/src/components/RecordControlPanel.js`

**Step 1: 높이 및 버튼 크기 축소**

변경 사항:
- `h-56` → `h-36` (패널 높이)
- `mx-8` → `mx-4` (좌우 마진)
- `mb-4` → `mb-2` (하단 마진)
- 버튼 아이콘: `w-20 h-20` → `w-12 h-12`
- 아이콘 clamp: `clamp(1rem, 4vw, 4rem)` → `clamp(1rem, 3vw, 2.5rem)`
- 텍스트 clamp: `clamp(1rem, 1.5vw, 2.2rem)` → `clamp(0.8rem, 1.2vw, 1.5rem)`
- `text-4xl font-extrabold` → `text-2xl font-bold`
- 빈 상단 공간 `h-[30%]` → `h-[15%]`

**Step 2: Record 전용으로 정리**

- `page` prop/selector 관련 분기 제거
- `isRunning`에서 `TaskPhase.INFERENCING` 조건 제거
- `handleControlCommand`에서 inference 분기 제거
- `requiredFieldsForInferenceOnly` 제거
- `phaseGuideMessages`에서 `INFERENCING` 제거

**Step 3: Commit**

```bash
git add physical_ai_manager/src/components/RecordControlPanel.js
git commit -m "refactor: compact RecordControlPanel and remove inference logic"
```

---

### Task 9: E2E 테스트

**Step 1: 인터페이스 빌드 확인**

physical_ai_server 컨테이너에서:
```bash
cd /root/ros2_ws && colcon build --packages-select physical_ai_interfaces && source install/setup.bash
```

**Step 2: physical_ai_server 재시작**

```bash
ros2 run physical_ai_server physical_ai_server
```

**Step 3: 프론트엔드 빌드 확인**

```bash
cd physical_ai_manager && npm start
```

**Step 4: UI 동작 확인**

1. Inference 페이지 접속
2. Start 버튼 → LOADING → INFERENCING 전환 확인
3. Stop 버튼 → PAUSED 전환 확인
4. Start 버튼 (재개) → INFERENCING 전환 확인
5. Record ON → 녹화 시작 확인
6. Record Save / Discard 확인
7. Clear → READY 전환 확인
8. Record 페이지에서 RecordControlPanel 정상 동작 확인

**Step 5: Commit**

```bash
git add -A
git commit -m "test: verify inference page revamp E2E"
```

---

## Summary of All Files Changed

| File | Action |
|------|--------|
| `physical_ai_interfaces/srv/SendCommand.srv` | Modify |
| `physical_ai_interfaces/msg/TaskStatus.msg` | Modify |
| `physical_ai_manager/src/constants/taskCommand.js` | Modify |
| `physical_ai_manager/src/constants/taskPhases.js` | Modify |
| `physical_ai_manager/src/hooks/useRosServiceCaller.js` | Modify |
| `physical_ai_manager/src/components/ControlPanel.js` | Rename → RecordControlPanel.js |
| `physical_ai_manager/src/components/RecordControlPanel.js` | Modify (compact + record-only) |
| `physical_ai_manager/src/components/InferenceControlPanel.js` | Create |
| `physical_ai_manager/src/pages/RecordPage.js` | Modify (import) |
| `physical_ai_manager/src/pages/InferencePage.js` | Modify (import) |
| `physical_ai_server/physical_ai_server/inference/inference_manager.py` | Modify |
| `physical_ai_server/physical_ai_server/physical_ai_server.py` | Modify |
