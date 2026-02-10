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

  const [mergeMode, setMergeMode] = useState(false);
  const [sourceFolders, setSourceFolders] = useState([]);
  const [mergedName, setMergedName] = useState('');
  const [showSourceBrowserModal, setShowSourceBrowserModal] = useState(false);
  const [pendingMergeConvert, setPendingMergeConvert] = useState(false);

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

  // Handler for Merge & Convert button
  const handleMergeConvert = useCallback(() => {
    if (!mergedName) {
      setConvertError('Merged output name is required');
      return;
    }
    if (sourceFolders.length < 2) {
      setConvertError('At least 2 source folders are required');
      return;
    }

    setConvertError('');
    setIsConverting(true);

    // Set taskInstruction to source folder names for the server to detect merge mode
    // The actual sendRecordCommand is deferred to useEffect after Redux state propagates
    dispatch(setTaskInfo({
      ...info,
      taskName: mergedName,
      taskInstruction: sourceFolders,
    }));
    setPendingMergeConvert(true);
  }, [mergedName, sourceFolders, info, dispatch]);

  // Send merge convert command after Redux state has propagated
  useEffect(() => {
    if (!pendingMergeConvert) return;
    if (info.taskName !== mergedName) return;

    setPendingMergeConvert(false);

    const doConvert = async () => {
      try {
        const result = await sendRecordCommand('convert_mp4');
        if (!result.success) {
          setConvertError(result.message || 'Merge & Convert failed');
          setIsConverting(false);
        }
      } catch (error) {
        setConvertError(error.message || 'Failed to start Merge & Convert');
        setIsConverting(false);
      }
    };
    doConvert();
  }, [pendingMergeConvert, info.taskName, mergedName, sendRecordCommand]);

  // Handler for source folder selection from FileBrowserModal (merge mode, multi-select)
  const handleSourceFolderSelect = useCallback(
    (selectedItems) => {
      const items = Array.isArray(selectedItems) ? selectedItems : [selectedItems];
      const newNames = items.map((item) => item.name);
      setSourceFolders((prev) => {
        const existing = new Set(prev);
        newNames.forEach((name) => existing.add(name));
        return Array.from(existing);
      });
    },
    []
  );

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
          {!mergeMode && (
            <>
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
                {isConverting && !mergeMode ? (
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
                  'Convert Dataset'
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
            </>
          )}
        </div>

        {/* Merge & Convert toggle */}
        <label className="flex items-center gap-2 mt-2 cursor-pointer">
          <input
            type="checkbox"
            checked={mergeMode}
            onChange={(e) => setMergeMode(e.target.checked)}
            disabled={isConverting}
            className="rounded"
          />
          <span className="text-sm text-gray-700 font-medium">Merge & Convert</span>
        </label>

        {/* Merge & Convert UI */}
        {mergeMode && (
          <div className="w-full mt-2 p-2 bg-gray-50 rounded-lg border border-gray-200">
            {/* Source folder list */}
            <div className="text-xs text-gray-600 font-medium mb-1">Source Folders:</div>
            {sourceFolders.length === 0 ? (
              <div className="text-xs text-gray-400 mb-2">No folders added yet</div>
            ) : (
              <div className="mb-2 space-y-1">
                {sourceFolders.map((folder, idx) => (
                  <div key={idx} className="flex items-center gap-1 text-xs bg-white rounded px-2 py-1 border border-gray-200">
                    <span className="text-gray-500 font-mono w-4">{idx}.</span>
                    <span className="flex-1 truncate text-gray-700" title={folder}>{folder}</span>
                    <button
                      type="button"
                      onClick={() => setSourceFolders((prev) => prev.filter((_, i) => i !== idx))}
                      disabled={isConverting}
                      className="text-red-400 hover:text-red-600 font-bold ml-1"
                    >
                      x
                    </button>
                  </div>
                ))}
              </div>
            )}
            <button
              type="button"
              onClick={() => setShowSourceBrowserModal(true)}
              disabled={isConverting}
              className={clsx(
                'px-3', 'py-1', 'text-xs', 'font-medium', 'rounded-md',
                'transition-colors', 'flex', 'items-center', 'gap-1',
                isConverting
                  ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                  : 'bg-blue-500 text-white hover:bg-blue-600'
              )}
            >
              <MdFolderOpen size={14} />
              Add Folder
            </button>

            {/* Merged output name */}
            <div className="mt-2">
              <div className="text-xs text-gray-600 font-medium mb-1">Merged Output Name:</div>
              <input
                type="text"
                value={mergedName}
                onChange={(e) => setMergedName(e.target.value)}
                disabled={isConverting}
                placeholder="e.g. recycle_task"
                className={clsx(
                  'text-sm', 'w-full', 'p-1.5', 'border', 'border-gray-300', 'rounded-md',
                  'focus:outline-none', 'focus:ring-2', 'focus:ring-blue-500',
                  isConverting ? 'bg-gray-100 cursor-not-allowed' : 'bg-white'
                )}
              />
            </div>

            {/* Merge & Convert button */}
            <button
              type="button"
              onClick={handleMergeConvert}
              disabled={isConverting || sourceFolders.length < 2 || !mergedName}
              className={clsx(
                'w-full', 'mt-2', 'px-4', 'py-2', 'text-sm', 'font-medium', 'rounded-lg',
                'transition-colors', 'flex', 'items-center', 'justify-center', 'gap-2',
                (isConverting || sourceFolders.length < 2 || !mergedName)
                  ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                  : 'bg-green-500 text-white hover:bg-green-600'
              )}
            >
              {isConverting && mergeMode ? (
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
                  Merging & Converting...
                </>
              ) : (
                'Merge & Convert'
              )}
            </button>
          </div>
        )}

        {/* Progress indicator during conversion */}
        {isConverting && taskStatus.phase === TaskPhase.CONVERTING && (
          <div className="w-full mt-2">
            <div className="flex justify-between text-xs text-gray-600 mb-1">
              <span>
                {mergeMode
                  ? (taskStatus.encodingProgress || 0) < 5
                    ? '[0/3] Merging episodes...'
                    : (taskStatus.encodingProgress || 0) < 35
                      ? '[1/3] Converting to MP4...'
                      : (taskStatus.encodingProgress || 0) < 68
                        ? '[2/3] Converting to LeRobot v2.1...'
                        : '[3/3] Converting to LeRobot v3.0...'
                  : (taskStatus.encodingProgress || 0) < 33
                    ? '[1/3] Converting to MP4...'
                    : (taskStatus.encodingProgress || 0) < 66
                      ? '[2/3] Converting to LeRobot v2.1...'
                      : '[3/3] Converting to LeRobot v3.0...'}
              </span>
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
          Convert to MP4, LeRobot v2.1, and v3.0 formats
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

      {/* Source folder browser modal for merge mode */}
      <FileBrowserModal
        isOpen={showSourceBrowserModal}
        onClose={() => setShowSourceBrowserModal(false)}
        onFileSelect={handleSourceFolderSelect}
        title="Select Source Folders"
        selectButtonText="Select"
        allowDirectorySelect={true}
        allowFileSelect={false}
        initialPath={DEFAULT_PATHS.ROSBAG2_PATH}
        defaultPath={DEFAULT_PATHS.ROSBAG2_PATH}
        homePath=""
        multiSelect={true}
      />
    </div>
  );
};

export default InfoPanel;
