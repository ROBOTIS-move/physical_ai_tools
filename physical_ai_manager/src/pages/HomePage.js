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

export default function HomePage({ topics, setTopics, rosHost, yamlContent }) {
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

  const { sendRecordCommand } = useRosServiceCaller(
    `ws://${rosHost.split(':')[0]}:9090`
  );

  const handleControlCommand = (cmd) => {
    console.log('Control command received:', cmd);
    try {
      if (cmd === 'Start') {
        console.log('Calling sendRecordCommand with start');
        sendRecordCommand('start_record', info);
      } else if (cmd === 'Stop') {
        console.log('Calling sendRecordCommand with stop');
        sendRecordCommand('stop', info);
      } else if (cmd === 'Retry') {
        console.log('Calling sendRecordCommand with retry');
        sendRecordCommand('rerecord', info);
      } else if (cmd === 'Next') {
        console.log('Calling sendRecordCommand with next');
        sendRecordCommand('next', info);
      } else if (cmd === 'Finish') {
        console.log('Calling sendRecordCommand with finish');
        sendRecordCommand('terminate_all', info);
      }
    } catch (error) {
      console.error('Error handling control command:', error);
    }
  };

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Main content area */}
      <div className="flex-1 flex min-h-0 pt-0 px-0 justify-center items-start overflow-hidden">
        <div
          className={clsx(
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
          )}
        >
          <ImageGrid topics={topics} setTopics={setTopics} rosHost={rosHost} />
        </div>
        <div
          className={clsx('transition-all', 'duration-300', 'ease-in-out', 'relative', {
            'flex-[0_0_40px]': isRightPanelCollapsed,
            'flex-[1]': !isRightPanelCollapsed,
            'min-w-[60px]': isRightPanelCollapsed,
            'min-w-[400px]': !isRightPanelCollapsed,
            'max-w-[60px]': isRightPanelCollapsed,
            'max-w-[400px]': !isRightPanelCollapsed,
          })}
        >
          <button
            onClick={() => setIsRightPanelCollapsed(!isRightPanelCollapsed)}
            className={clsx(
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
            )}
          >
            <span
              className={clsx(
                'text-gray-600',
                'text-3xl',
                'transition-transform',
                'duration-200',
              )}
            >
              {isRightPanelCollapsed ? <MdKeyboardDoubleArrowLeft /> : <MdKeyboardDoubleArrowRight />}
            </span>
          </button>
          <div
            className={clsx('h-full', 'overflow-hidden', 'transition-opacity', 'duration-300', {
              'opacity-0': isRightPanelCollapsed,
              'opacity-100': !isRightPanelCollapsed,
              'pointer-events-none': isRightPanelCollapsed,
              'pointer-events-auto': !isRightPanelCollapsed,
            })}
          >
            <div className="ml-1 mr-1 flex flex-col items-center h-full">
              <div className="w-full h-10"></div>
              <div className="w-[250px] flex justify-center">
                <EpisodeStatus episodeStatus={episodeStatus} />
              </div>
              <div className="w-full h-10"></div>
              <div className="flex-1 overflow-y-auto">
                <InfoPanel info={info} onChange={setInfo} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Control Panel - Fixed at bottom */}
      <div className="flex-shrink-0">
        <ControlPanel onCommand={handleControlCommand} episodeStatus={episodeStatus} />
      </div>
    </div>
  );
} 