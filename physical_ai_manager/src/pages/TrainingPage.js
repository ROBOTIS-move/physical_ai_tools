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

import React, { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import clsx from 'clsx';
import toast, { useToasterStore } from 'react-hot-toast';
import HeartbeatStatus from '../components/HeartbeatStatus';
import DatasetSelector from '../components/DatasetSelector';
import PolicySelector from '../components/PolicySelector';
import TrainingOutputFolderInput from '../components/TrainingOutputFolderInput';
import ModelWeightSelector from '../components/ModelWeightSelector';
import TrainingControlButtons from '../components/TrainingControlButtons';
import { setTrainingMode } from '../features/training/trainingSlice';

export default function TrainingPage() {
  const dispatch = useDispatch();
  const trainingMode = useSelector((state) => state.training.trainingMode);
  const isTraining = useSelector((state) => state.training.isTraining);

  const classContainer = clsx(
    'w-full',
    'h-full',
    'flex',
    'flex-col',
    'items-start',
    'justify-start',
    'pt-10'
  );

  const classHeartbeatStatus = clsx('absolute', 'top-5', 'left-35', 'z-10');

  const classModeSelector = clsx(
    'flex',
    'items-center',
    'gap-6',
    'bg-white',
    'border',
    'border-gray-200',
    'rounded-2xl',
    'shadow-lg',
    'mt-10',
    'ml-10',
    'p-6'
  );

  const classRadioGroup = clsx('flex', 'items-center', 'gap-2');

  const classRadioInput = clsx(
    'w-4',
    'h-4',
    'text-blue-600',
    'bg-gray-100',
    'border-gray-300',
    'focus:ring-blue-500',
    'focus:ring-2'
  );

  const classRadioLabel = clsx('text-lg', 'font-medium', 'text-gray-700', 'cursor-pointer');

  const classComponentsContainer = clsx(
    'w-full',
    'flex',
    'p-10',
    'gap-8',
    'items-start',
    'justify-center'
  );

  // Toast limit implementation using useToasterStore
  const { toasts } = useToasterStore();
  const TOAST_LIMIT = 3;

  useEffect(() => {
    toasts
      .filter((t) => t.visible) // Only consider visible toasts
      .filter((_, i) => i >= TOAST_LIMIT) // Is toast index over limit?
      .forEach((t) => toast.dismiss(t.id)); // Dismiss – Use toast.remove(t.id) for no exit animation
  }, [toasts]);

  const handleModeChange = (mode) => {
    dispatch(setTrainingMode(mode));
  };

  const renderTrainingComponents = () => {
    if (trainingMode === 'resume') {
      return <ModelWeightSelector />;
    } else {
      return (
        <>
          <DatasetSelector />
          <PolicySelector />
          <TrainingOutputFolderInput />
        </>
      );
    }
  };

  return (
    <div className={classContainer}>
      <div className={classHeartbeatStatus}>
        <HeartbeatStatus />
      </div>

      {/* Training Mode Selector */}
      <div className={classModeSelector}>
        <h3 className="text-xl font-bold text-gray-800 mr-4">Training Mode</h3>

        <div className="flex flex-col items-start gap-2">
          <div className={classRadioGroup}>
            <input
              type="radio"
              id="new-training"
              name="trainingMode"
              value="new"
              checked={trainingMode === 'new'}
              onChange={() => handleModeChange('new')}
              className={classRadioInput}
              disabled={isTraining}
            />
            <label htmlFor="new-training" className={classRadioLabel}>
              New Training
            </label>
          </div>

          <div className={classRadioGroup}>
            <input
              type="radio"
              id="resume-training"
              name="trainingMode"
              value="resume"
              checked={trainingMode === 'resume'}
              onChange={() => handleModeChange('resume')}
              className={classRadioInput}
              disabled={isTraining}
            />
            <label htmlFor="resume-training" className={classRadioLabel}>
              Resume Training
            </label>
          </div>
        </div>
      </div>

      {/* Components based on selected mode */}
      <div className={classComponentsContainer}>{renderTrainingComponents()}</div>

      {/* Training Control Buttons */}
      <TrainingControlButtons />
    </div>
  );
}
