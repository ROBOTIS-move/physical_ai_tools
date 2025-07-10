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

import React from 'react';
import { useDispatch, useSelector } from 'react-redux';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { setIsTraining } from '../features/training/trainingSlice';
import { useRosServiceCaller } from '../hooks/useRosServiceCaller';

export default function TrainingControlButtons() {
  const dispatch = useDispatch();
  const trainingMode = useSelector((state) => state.training.trainingMode);
  const isTraining = useSelector((state) => state.training.isTraining);
  const datasetRepoId = useSelector((state) => state.training.trainingInfo.datasetRepoId);
  const selectedPolicy = useSelector((state) => state.training.trainingInfo.policyType);
  const selectedDevice = useSelector((state) => state.training.trainingInfo.policyDevice);
  const outputFolderName = useSelector((state) => state.training.trainingInfo.outputFolderName);
  const selectedModelWeight = useSelector((state) => state.training.selectedModelWeight);

  const { sendTrainingCommand } = useRosServiceCaller();

  const classButtonContainer = clsx('w-full', 'flex', 'justify-center', 'mt-8', 'px-10');

  const classButton = clsx(
    'px-8',
    'py-3',
    'rounded-xl',
    'font-semibold',
    'text-lg',
    'transition-all',
    'duration-200',
    'transform',
    'active:scale-95',
    'shadow-lg'
  );

  const classStartButton = clsx(
    classButton,
    'bg-blue-600',
    'text-white',
    'hover:bg-blue-700',
    'hover:shadow-xl',
    'disabled:bg-gray-400',
    'disabled:cursor-not-allowed',
    'disabled:hover:bg-gray-400',
    'disabled:hover:shadow-lg'
  );

  const classFinishButton = clsx(
    classButton,
    'bg-red-600',
    'text-white',
    'hover:bg-red-700',
    'hover:shadow-xl',
    'disabled:bg-gray-400',
    'disabled:cursor-not-allowed',
    'disabled:hover:bg-gray-400',
    'disabled:hover:shadow-lg'
  );

  const handleStartTraining = async () => {
    try {
      let command;

      if (trainingMode === 'resume') {
        // Resume training
        if (!selectedModelWeight) {
          toast.error('Please select a model weight to resume training');
          return;
        }
        command = 'resume'; // RESUME
      } else {
        // New training
        if (!datasetRepoId || !selectedPolicy || !selectedDevice || !outputFolderName) {
          toast.error('Please fill in all required fields');
          return;
        }
        command = 'start'; // START
      }

      dispatch(setIsTraining(true));
      const result = await sendTrainingCommand(command);

      if (result.success) {
        toast.success(
          trainingMode === 'resume'
            ? 'Training resumed successfully!'
            : 'Training started successfully!'
        );
      } else {
        toast.error(
          `Failed to ${trainingMode === 'resume' ? 'resume' : 'start'} training: ${result.message}`
        );
        dispatch(setIsTraining(false));
      }
    } catch (error) {
      toast.error(
        `Error ${trainingMode === 'resume' ? 'resuming' : 'starting'} training: ${error.message}`
      );
      dispatch(setIsTraining(false));
    }
  };

  const handleFinishTraining = async () => {
    try {
      dispatch(setIsTraining(false));
      const result = await sendTrainingCommand('finish'); // FINISH command

      if (result.success) {
        toast.success('Training finished successfully!');
      } else {
        toast.error(`Failed to finish training: ${result.message}`);
        // Revert state if finish failed
        dispatch(setIsTraining(true));
      }
    } catch (error) {
      toast.error(`Error finishing training: ${error.message}`);
      // Revert state if finish failed
      dispatch(setIsTraining(true));
    }
  };

  const getStartButtonText = () => {
    if (trainingMode === 'resume') {
      return 'Resume Training';
    }
    return 'Start Training';
  };

  const isStartDisabled = () => {
    if (isTraining) return true;

    if (trainingMode === 'resume') {
      return !selectedModelWeight;
    } else {
      return !datasetRepoId || !selectedPolicy || !selectedDevice || !outputFolderName;
    }
  };

  return (
    <div className={classButtonContainer}>
      <button
        onClick={handleStartTraining}
        disabled={isStartDisabled()}
        className={classStartButton}
        style={{ display: isTraining ? 'none' : 'block' }}
      >
        {getStartButtonText()}
      </button>

      <button
        onClick={handleFinishTraining}
        disabled={!isTraining}
        className={classFinishButton}
        style={{ display: isTraining ? 'block' : 'none' }}
      >
        Finish Training
      </button>
    </div>
  );
}
