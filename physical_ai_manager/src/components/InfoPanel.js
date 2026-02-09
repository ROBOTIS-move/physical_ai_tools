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

import React, { useState, useEffect, useCallback } from 'react';
import { useSelector, useDispatch } from 'react-redux';
import clsx from 'clsx';
import { MdFolderOpen } from 'react-icons/md';
import TaskInstructionInput from './TaskInstructionInput';
import TagInput from './TagInput';
import FileBrowserModal from './FileBrowserModal';
import TaskPhase from '../constants/taskPhases';
import { setTaskInfo, setUseMultiTaskMode } from '../features/tasks/taskSlice';
import { useRosServiceCaller } from '../hooks/useRosServiceCaller';
import { DEFAULT_PATHS } from '../constants/paths';

const InfoPanel = () => {
  const dispatch = useDispatch();
  const { sendRecordCommand } = useRosServiceCaller();

  const info = useSelector((state) => state.tasks.taskInfo);
  const taskStatus = useSelector((state) => state.tasks.taskStatus);

  const [isTaskStatusPaused, setIsTaskStatusPaused] = useState(false);
  const [lastTaskStatusUpdate, setLastTaskStatusUpdate] = useState(Date.now());
  const [isConverting, setIsConverting] = useState(false);
  const [convertError, setConvertError] = useState('');
  const [hasSeenConverting, setHasSeenConverting] = useState(false);
  const [showDatasetBrowserModal, setShowDatasetBrowserModal] = useState(false);

  const useMultiTaskMode = useSelector((state) => state.tasks.useMultiTaskMode);

  const disabled = taskStatus.phase !== TaskPhase.IDLE || !isTaskStatusPaused;
  const [isEditable, setIsEditable] = useState(!disabled);

  const handleChange = useCallback(
    (field, value) => {
      if (!isEditable) return; // Block changes when not editable
      dispatch(setTaskInfo({ ...info, [field]: value }));
    },
    [isEditable, info, dispatch]
  );

  // Update isEditable state when the disabled prop changes
  useEffect(() => {
    setIsEditable(!disabled);
  }, [disabled]);

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
      const isPaused = timeSinceLastUpdate >= UPDATE_PAUSE_THRESHOLD;
      if (isPaused !== isTaskStatusPaused) {
        setIsTaskStatusPaused(isPaused);
      }
    }, 1000);

    return () => clearInterval(timer);
  }, [lastTaskStatusUpdate, isTaskStatusPaused]);

  // Update isConverting state based on taskStatus phase
  useEffect(() => {
    if (taskStatus.phase === TaskPhase.CONVERTING) {
      setIsConverting(true);
      setHasSeenConverting(true);
    } else if (isConverting && hasSeenConverting && taskStatus.phase === TaskPhase.READY) {
      // Only reset after CONVERTING phase was actually received from server
      setIsConverting(false);
      setHasSeenConverting(false);
    }
  }, [taskStatus.phase, isConverting, hasSeenConverting]);

  // Handler for Convert MP4 button
  const handleConvertMp4 = useCallback(async () => {
    if (!info.taskName) {
      setConvertError('Task name is required');
      return;
    }

    setConvertError('');
    setIsConverting(true);

    try {
      const result = await sendRecordCommand('convert_mp4');
      if (!result.success) {
        setConvertError(result.message || 'Conversion failed');
        setIsConverting(false);
      }
    } catch (error) {
      setConvertError(error.message || 'Failed to start conversion');
      setIsConverting(false);
    }
  }, [info.taskName, sendRecordCommand]);

  // Handler for dataset folder selection from FileBrowserModal
  const handleDatasetFolderSelect = useCallback(
    (selectedItem) => {
      const folderName = selectedItem.name;
      const robotType = taskStatus?.robotType;
      // Remove {robotType}_ prefix if present
      const prefix = robotType ? `${robotType}_` : '';
      const taskName = prefix && folderName.startsWith(prefix)
        ? folderName.slice(prefix.length)
        : folderName;
      dispatch(setTaskInfo({ ...info, taskName }));
      setShowDatasetBrowserModal(false);
    },
    [taskStatus?.robotType, info, dispatch]
  );

  // Check if Convert MP4 button should be enabled
  const canConvertMp4 = taskStatus.phase === TaskPhase.READY && info.taskName && !isConverting;

  const classLabel = clsx('text-sm', 'text-gray-600', 'w-28', 'flex-shrink-0', 'font-medium');

  const classInfoPanel = clsx(
    'bg-white',
    'border',
    'border-gray-200',
    'rounded-2xl',
    'shadow-md',
    'p-4',
    'w-full',
    'max-w-[350px]',
    'relative',
    'overflow-y-auto',
    'scrollbar-thin'
  );

  const classTaskNameTextarea = clsx(
    'text-sm',
    'resize-y',
    'min-h-8',
    'max-h-20',
    'h-10',
    'w-full',
    'p-2',
    'border',
    'border-gray-300',
    'rounded-md',
    'focus:outline-none',
    'focus:ring-2',
    'focus:ring-blue-500',
    'focus:border-transparent',
    {
      'bg-gray-100 cursor-not-allowed': !isEditable,
      'bg-white': isEditable,
    }
  );

  const classTaskInstructionTextarea = clsx(
    'text-sm',
    'resize-y',
    'min-h-16',
    'max-h-24',
    'w-full',
    'p-2',
    'border',
    'border-gray-300',
    'rounded-md',
    'focus:outline-none',
    'focus:ring-2',
    'focus:ring-blue-500',
    'focus:border-transparent',
    {
      'bg-gray-100 cursor-not-allowed': !isEditable,
      'bg-white': isEditable,
    }
  );

  const classSingleTaskButton = clsx(
    'px-3',
    'py-1',
    'text-sm',
    'rounded-xl',
    'font-medium',
    'transition-colors',
    !useMultiTaskMode ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-700',
    !isEditable && 'cursor-not-allowed opacity-60'
  );

  const classMultiTaskButton = clsx(
    'px-3',
    'py-1',
    'text-sm',
    'rounded-xl',
    'font-medium',
    'transition-colors',
    useMultiTaskMode ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-700',
    !isEditable && 'cursor-not-allowed opacity-60'
  );

  return (
    <div className={classInfoPanel}>
      <div className={clsx('text-lg', 'font-semibold', 'mb-3', 'text-gray-800')}>
        Task Information
      </div>

      {/* Edit mode indicator */}
      <div
        className={clsx('mb-3', 'p-2', 'rounded-md', 'text-sm', 'font-medium', {
          'bg-green-100 text-green-800': isEditable,
          'bg-gray-100 text-gray-600': !isEditable,
        })}
      >
        {isEditable ? (
          'Edit mode'
        ) : (
          <div className="leading-tight">
            <div>Read only</div>
            <div className="text-xs mt-1 opacity-80">task is running or robot is not connected</div>
          </div>
        )}
      </div>

      {/* Task Name */}
      <div className={clsx('flex', 'items-center', 'mb-2.5')}>
        <span className={classLabel}>Task Name</span>
        <textarea
          className={classTaskNameTextarea}
          value={info.taskName || ''}
          onChange={(e) => handleChange('taskName', e.target.value)}
          disabled={!isEditable}
          placeholder="Enter Task Name"
        />
      </div>

      {/* Task Instruction */}
      <div className={clsx('flex', 'items-start', 'mb-2.5')}>
        <span
          className={clsx(
            'text-sm',
            'text-gray-600',
            'w-28',
            'flex-shrink-0',
            'font-medium',
            'pt-2'
          )}
        >
          Task Instruction
        </span>

        <div>
          {/* Single/Multi Task Mode Toggle */}
          <div className={clsx('flex', 'justify-start', 'mb-3', 'gap-3')}>
            <button
              type="button"
              className={classSingleTaskButton}
              onClick={() => isEditable && dispatch(setUseMultiTaskMode(false))}
              disabled={!isEditable}
            >
              Single Task
            </button>
            <button
              type="button"
              className={classMultiTaskButton}
              onClick={() => isEditable && dispatch(setUseMultiTaskMode(true))}
              disabled={!isEditable}
            >
              Multi Task
            </button>
          </div>

          {useMultiTaskMode && (
            <div className="flex-1 min-w-0">
              <TaskInstructionInput
                instructions={info.taskInstruction || []}
                onChange={(newInstructions) => handleChange('taskInstruction', newInstructions)}
                disabled={!isEditable}
              />
            </div>
          )}
          {!useMultiTaskMode && (
            <textarea
              className={classTaskInstructionTextarea}
              value={info.taskInstruction || ''}
              onChange={(e) => handleChange('taskInstruction', [e.target.value])}
              disabled={!isEditable}
              placeholder="Enter Task Instruction"
            />
          )}
        </div>
      </div>

      {/* Tags */}
      <div className={clsx('flex', 'items-start', 'mb-2.5')}>
        <span className={clsx(classLabel, 'pt-2')}>Tags</span>
        <div className="flex-1 min-w-0">
          <TagInput
            tags={info.tags || []}
            onChange={(newTags) => handleChange('tags', newTags)}
            disabled={!isEditable}
          />
          <div className="text-xs text-gray-500 mt-1 leading-relaxed">
            Press Enter or use comma to add tags
          </div>
        </div>
      </div>

      {/* Convert MP4 Button */}
      <div className={clsx('flex', 'flex-col', 'items-start', 'mb-2.5', 'mt-4')}>
        <div className="flex items-center gap-2 w-full">
          <button
            type="button"
            onClick={handleConvertMp4}
            disabled={!canConvertMp4}
            className={clsx(
              'px-4',
              'py-2',
              'text-sm',
              'font-medium',
              'rounded-lg',
              'transition-colors',
              'flex',
              'items-center',
              'gap-2',
              canConvertMp4
                ? 'bg-green-500 text-white hover:bg-green-600'
                : 'bg-gray-300 text-gray-500 cursor-not-allowed'
            )}
          >
            {isConverting ? (
              <>
                <svg
                  className="animate-spin h-4 w-4"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Converting...
              </>
            ) : (
              'Convert MP4'
            )}
          </button>
          <button
            type="button"
            onClick={() => setShowDatasetBrowserModal(true)}
            className={clsx(
              'px-3',
              'py-2',
              'text-sm',
              'font-medium',
              'rounded-lg',
              'transition-colors',
              'flex',
              'items-center',
              'gap-1',
              'bg-blue-500 text-white hover:bg-blue-600'
            )}
          >
            <MdFolderOpen size={16} />
            Browse
          </button>
        </div>
        {/* Progress indicator during conversion */}
        {isConverting && taskStatus.phase === TaskPhase.CONVERTING && (
          <div className="w-full mt-2">
            <div className="flex justify-between text-xs text-gray-600 mb-1">
              <span>Converting episodes...</span>
              <span>{Math.round(taskStatus.encodingProgress || 0)}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2">
              <div
                className="bg-green-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${taskStatus.encodingProgress || 0}%` }}
              />
            </div>
          </div>
        )}
        {/* Error message */}
        {convertError && (
          <div className="text-xs text-red-500 mt-1">{convertError}</div>
        )}
        <div className="text-xs text-gray-500 mt-1 leading-relaxed">
          Convert recorded episodes to MP4 format
        </div>
      </div>

      {/* Dataset save path indicator */}
      <div className="flex flex-col items-center text-xs text-gray-500 mt-3 leading-relaxed bg-gray-100 p-2 rounded-md">
        <div>Dataset will be saved as:</div>
        <div className="text-blue-500 font-bold break-all">
          {taskStatus?.robotType}_{info.taskName}
        </div>
      </div>

      {/* Dataset folder browser modal */}
      <FileBrowserModal
        isOpen={showDatasetBrowserModal}
        onClose={() => setShowDatasetBrowserModal(false)}
        onFileSelect={handleDatasetFolderSelect}
        title="Select Dataset Folder"
        selectButtonText="Select"
        allowDirectorySelect={true}
        allowFileSelect={false}
        initialPath={DEFAULT_PATHS.ROSBAG2_PATH}
        defaultPath={DEFAULT_PATHS.ROSBAG2_PATH}
        homePath=""
      />
    </div>
  );
};

export default InfoPanel;
