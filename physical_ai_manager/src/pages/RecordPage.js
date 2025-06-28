// Copyright 2025 ROBOTIS CO., LTD.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// Author: Kiwoong Park

import React, { useState, useEffect } from 'react';
import clsx from 'clsx';
import { MdKeyboardDoubleArrowLeft, MdKeyboardDoubleArrowRight } from 'react-icons/md';
import toast, { useToasterStore } from 'react-hot-toast';
import ImageGrid from '../components/ImageGrid';
import ControlPanel from '../components/ControlPanel';
import InfoPanel from '../components/InfoPanel';
import TaskPhase from '../constants/taskPhases';
import { useSelector, useDispatch } from 'react-redux';
import { addTag, setTaskType } from '../features/tasks/taskSlice';

export default function RecordPage({ isActive = true }) {
  const dispatch = useDispatch();

  const taskInfo = useSelector((state) => state.tasks.taskInfo);
  const taskStatus = useSelector((state) => state.tasks.taskStatus);

  // Toast limit implementation using useToasterStore
  const { toasts } = useToasterStore();
  const TOAST_LIMIT = 3;

  const [isRightPanelCollapsed, setIsRightPanelCollapsed] = useState(false);
  const [isTaskStatusPaused, setIsTaskStatusPaused] = useState(false);
  const [lastTaskStatusUpdate, setLastTaskStatusUpdate] = useState(Date.now());

  useEffect(() => {
    toasts
      .filter((t) => t.visible) // Only consider visible toasts
      .filter((_, i) => i >= TOAST_LIMIT) // Is toast index over limit?
      .forEach((t) => toast.dismiss(t.id)); // Dismiss – Use toast.remove(t.id) for no exit animation
  }, [toasts]);

  useEffect(() => {
    if (taskStatus.robotType !== '' && taskInfo.tags.length === 0) {
      dispatch(addTag(taskStatus.robotType));
      dispatch(addTag('robotis'));
    }
  }, [taskInfo.tags, taskStatus.robotType, dispatch]);

  useEffect(() => {
    if (!taskStatus.running) {
      console.log('record');
      dispatch(setTaskType('record'));
    }
  }, [dispatch, taskStatus.running]);

  // track task status update
  useEffect(() => {
    if (taskStatus) {
      setLastTaskStatusUpdate(Date.now());
      setIsTaskStatusPaused(false);
    }
  }, [taskStatus]);

  // Check if task status updates are paused (considered paused if no updates for 1 second)
  useEffect(() => {
    const UPDATE_PAUSE_THRESHOLD = 1000;
    const timer = setInterval(() => {
      const timeSinceLastUpdate = Date.now() - lastTaskStatusUpdate;
      setIsTaskStatusPaused(timeSinceLastUpdate >= UPDATE_PAUSE_THRESHOLD);
    }, 1000);

    return () => clearInterval(timer);
  }, [lastTaskStatusUpdate]);

  const classMainContainer = 'h-full flex flex-col overflow-hidden';
  const classContentsArea = 'flex-1 flex min-h-0 pt-0 px-0 justify-center items-start';
  const classImageGridContainer = clsx(
    'transition-all',
    'duration-300',
    'ease-in-out',
    'flex',
    'items-center',
    'justify-center',
    'min-h-0',
    'h-full',
    'overflow-hidden',
    'm-2',
    {
      'flex-[12]': isRightPanelCollapsed,
      'flex-[10]': !isRightPanelCollapsed,
    }
  );

  const classRightPanelArea = clsx(
    'h-full',
    'w-full',
    'transition-all',
    'duration-300',
    'ease-in-out',
    'relative',
    'overflow-scroll',
    {
      'flex-[0_0_40px]': isRightPanelCollapsed,
      'flex-[1]': !isRightPanelCollapsed,
      'min-w-[60px]': isRightPanelCollapsed,
      'min-w-[400px]': !isRightPanelCollapsed,
      'max-w-[60px]': isRightPanelCollapsed,
      'max-w-[400px]': !isRightPanelCollapsed,
    }
  );

  const classHideButton = clsx(
    'absolute',
    'top-3',
    'bg-white',
    'border',
    'border-gray-300',
    'rounded-full',
    'w-12',
    'h-12',
    'flex',
    'items-center',
    'justify-center',
    'shadow-md',
    'hover:bg-gray-50',
    'transition-all',
    'duration-200',
    'z-10',
    {
      'left-2': isRightPanelCollapsed,
      'left-[10px]': !isRightPanelCollapsed,
    }
  );

  const classRightPanel = clsx(
    'h-full',
    'flex',
    'flex-col',
    'items-center',
    'overflow-hidden',
    'transition-opacity',
    'duration-300',
    'overflow-scroll',
    {
      'opacity-0': isRightPanelCollapsed,
      'opacity-100': !isRightPanelCollapsed,
      'pointer-events-none': isRightPanelCollapsed,
      'pointer-events-auto': !isRightPanelCollapsed,
    }
  );

  const classRobotTypeContainer = clsx(
    'absolute',
    'top-4',
    'left-4',
    'z-20',
    'flex',
    'flex-row',
    'items-center',
    'bg-white/90',
    'backdrop-blur-sm',
    'rounded-full',
    'px-3',
    'py-1',
    'shadow-md',
    'border',
    'border-gray-100'
  );
  const classRobotType = clsx('ml-2 mr-1 my-2 text-gray-600 text-lg');
  const classRobotTypeValue = clsx(
    'mx-1 my-2 px-2 text-lg text-blue-600 focus:outline-none bg-blue-100 rounded-full'
  );

  return (
    <div className={classMainContainer}>
      <div className={classContentsArea}>
        <div className="w-full h-full flex flex-col relative">
          <div className={classRobotTypeContainer}>
            <div className={classRobotType}>Robot Type</div>
            <div className={classRobotTypeValue}>{taskStatus?.robotType}</div>
          </div>
          <div className={classImageGridContainer}>
            <ImageGrid isActive={isActive} />
          </div>
        </div>
        <div className={classRightPanelArea}>
          <button
            onClick={() => setIsRightPanelCollapsed(!isRightPanelCollapsed)}
            className={classHideButton}
            title="Hide"
          >
            <span className="text-gray-600 text-3xl transition-transform duration-200">
              {isRightPanelCollapsed ? (
                <MdKeyboardDoubleArrowLeft />
              ) : (
                <MdKeyboardDoubleArrowRight />
              )}
            </span>
          </button>
          <div className={classRightPanel}>
            <div className="w-full min-h-10"></div>
            <InfoPanel disabled={taskStatus?.phase !== TaskPhase.READY || !isTaskStatusPaused} />
          </div>
        </div>
      </div>
      <ControlPanel />
    </div>
  );
}
