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

import React, { useState } from 'react';
import clsx from 'clsx';
import { MdKeyboardDoubleArrowLeft, MdKeyboardDoubleArrowRight } from 'react-icons/md';
import ImageGrid from '../components/ImageGrid';
import EpisodeStatus from '../components/EpisodeStatus';
import ControlPanel from '../components/ControlPanel';
import InfoPanel from '../components/InfoPanel';
import { useRosServiceCaller } from '../hooks/useRosServiceCaller';

export default function HomePage({ topics, setTopics, rosHost }) {
  const [info, setInfo] = useState({
    taskName: 'ai_worker_task_abcd_12345',
    robotType: 'ai-worker',
    taskType: 'record',
    taskInstruction: 'pick and place objects',
    repoId: 'robotis/ai_worker_dataset',
    fps: 30,
    tags: ['tutorial'],
    warmupTime: 5,
    episodeTime: 60,
    resetTime: 60,
    numEpisodes: 100,
    resume: true,
    pushToHub: true,
  });

  const [episodeStatus, setEpisodeStatus] = useState({
    taskName: 'idle',
    running: false,
    phase: 4,
    progress: 60,
    numEpisodes: 0,
    currentEpisodeNumber: 0,
    repoId: '',
  });

  const [isRightPanelCollapsed, setIsRightPanelCollapsed] = useState(false);

  const { sendRecordCommand } = useRosServiceCaller(`ws://${rosHost.split(':')[0]}:9090`);

  const handleControlCommand = (cmd) => {
    console.log('Control command received:', cmd);
    try {
      if (cmd === 'Start') {
        sendRecordCommand('start_record', info);
      } else if (cmd === 'Stop') {
        sendRecordCommand('stop', info);
      } else if (cmd === 'Retry') {
        sendRecordCommand('rerecord', info);
      } else if (cmd === 'Next') {
        sendRecordCommand('next', info);
      } else if (cmd === 'Finish') {
        sendRecordCommand('terminate_all', info);
      }
      console.log('Calling sendRecordCommand with', cmd);
    } catch (error) {
      console.error('Error handling control command:', error);
    }
  };

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
    'top-10',
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

  return (
    <div className={classMainContainer}>
      <div className={classContentsArea}>
        <div className={classImageGridContainer}>
          <ImageGrid topics={topics} setTopics={setTopics} rosHost={rosHost} />
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
            <div className="w-[250px] flex justify-center">
              <EpisodeStatus episodeStatus={episodeStatus} />
            </div>
            <div className="w-full min-h-10"></div>
            <InfoPanel info={info} onChange={setInfo} />
          </div>
        </div>
      </div>
      <ControlPanel onCommand={handleControlCommand} episodeStatus={episodeStatus} />
    </div>
  );
}
