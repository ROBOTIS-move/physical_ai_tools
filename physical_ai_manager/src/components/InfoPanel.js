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
import clsx from 'clsx';

const InfoPanel = ({ info, onChange }) => {
  const handleChange = (field, value) => {
    onChange({ ...info, [field]: value });
  };

  return (
    <div className="bg-white rounded-xl shadow-md p-4 w-full max-w-xs">
      <div className="text-lg font-semibold mb-3">Task Information</div>
      <div className="flex items-center mb-2">
        <span className="text-xs text-gray-600 w-28 flex-shrink-0">task name</span>
        <textarea
          className={clsx(
            'text-xs',
            'resize-y',
            'min-h-3',
            'max-h-20',
            'w-full',
            'p-1.5',
            'border',
            'border-gray-300',
            'rounded',
            'focus:outline-none',
            'focus:ring-1',
            'focus:ring-blue-500'
          )}
          value={info.taskName || ''}
          onChange={(e) => handleChange('taskName', e.target.value)}
        />
      </div>
      <div className="flex items-center mb-2">
        <span className="text-xs text-gray-600 w-28 flex-shrink-0">robot type</span>
        <input
          className={clsx(
            'text-xs',
            'w-full',
            'p-1.5',
            'border',
            'border-gray-300',
            'rounded',
            'focus:outline-none',
            'focus:ring-1',
            'focus:ring-blue-500'
          )}
          type="text"
          value={info.robotType || ''}
          onChange={(e) => handleChange('robotType', e.target.value)}
        />
      </div>
      <div className="flex items-center mb-2">
        <span className="text-xs text-gray-600 w-28 flex-shrink-0">task type</span>
        <input
          className={clsx(
            'text-xs',
            'w-full',
            'p-1.5',
            'border',
            'border-gray-300',
            'rounded',
            'focus:outline-none',
            'focus:ring-1',
            'focus:ring-blue-500'
          )}
          type="text"
          value={info.taskType || ''}
          onChange={(e) => handleChange('taskType', e.target.value)}
        />
      </div>
      <div className="flex items-center mb-2">
        <span className="text-xs text-gray-600 w-28 flex-shrink-0">task instruction</span>
        <textarea
          className={clsx(
            'text-xs',
            'resize-y',
            'min-h-6',
            'max-h-24',
            'w-full',
            'p-1.5',
            'border',
            'border-gray-300',
            'rounded',
            'focus:outline-none',
            'focus:ring-1',
            'focus:ring-blue-500'
          )}
          value={info.taskInstruction || ''}
          onChange={(e) => handleChange('taskInstruction', e.target.value)}
        />
      </div>
      <div className="flex items-center mb-2">
        <span className="text-xs text-gray-600 w-28 flex-shrink-0">fps</span>
        <input
          className={clsx(
            'text-xs',
            'w-full',
            'p-1.5',
            'border',
            'border-gray-300',
            'rounded',
            'focus:outline-none',
            'focus:ring-1',
            'focus:ring-blue-500'
          )}
          type="number"
          value={info.fps || ''}
          onChange={(e) => handleChange('fps', Number(e.target.value))}
        />
      </div>
      <div className="flex items-center mb-2">
        <span className="text-xs text-gray-600 w-28 flex-shrink-0">tags</span>
        <input
          className={clsx(
            'text-xs',
            'w-full',
            'p-1.5',
            'border',
            'border-gray-300',
            'rounded',
            'focus:outline-none',
            'focus:ring-1',
            'focus:ring-blue-500'
          )}
          type="text"
          value={Array.isArray(info.tags) ? info.tags.join(', ') : ''}
          onChange={(e) =>
            handleChange(
              'tags',
              e.target.value.split(',').map((s) => s.trim())
            )
          }
        />
      </div>
      <div className="flex items-center mb-2">
        <span className="text-xs text-gray-600 w-28 flex-shrink-0">warmup time (s)</span>
        <input
          className={clsx(
            'text-xs',
            'w-full',
            'p-1.5',
            'border',
            'border-gray-300',
            'rounded',
            'focus:outline-none',
            'focus:ring-1',
            'focus:ring-blue-500'
          )}
          type="text"
          value={info.warmupTime || ''}
          onChange={(e) => handleChange('warmupTime', e.target.value)}
        />
      </div>
      <div className="flex items-center mb-2">
        <span className="text-xs text-gray-600 w-28 flex-shrink-0">episode time (s)</span>
        <input
          className={clsx(
            'text-xs',
            'w-full',
            'p-1.5',
            'border',
            'border-gray-300',
            'rounded',
            'focus:outline-none',
            'focus:ring-1',
            'focus:ring-blue-500'
          )}
          type="text"
          value={info.episodeTime || ''}
          onChange={(e) => handleChange('episodeTime', e.target.value)}
        />
      </div>
      <div className="flex items-center mb-2">
        <span className="text-xs text-gray-600 w-28 flex-shrink-0">reset time (s)</span>
        <input
          className={clsx(
            'text-xs',
            'w-full',
            'p-1.5',
            'border',
            'border-gray-300',
            'rounded',
            'focus:outline-none',
            'focus:ring-1',
            'focus:ring-blue-500'
          )}
          type="text"
          value={info.resetTime || ''}
          onChange={(e) => handleChange('resetTime', e.target.value)}
        />
      </div>
      <div className="flex items-center mb-2">
        <span className="text-xs text-gray-600 w-28 flex-shrink-0">num episodes</span>
        <input
          className={clsx(
            'text-xs',
            'w-full',
            'p-1.5',
            'border',
            'border-gray-300',
            'rounded',
            'focus:outline-none',
            'focus:ring-1',
            'focus:ring-blue-500'
          )}
          type="number"
          value={info.numEpisodes || ''}
          onChange={(e) => handleChange('numEpisodes', Number(e.target.value))}
        />
      </div>
      <div className="flex items-center mb-2">
        <span className="text-xs text-gray-600 w-28 flex-shrink-0">resume</span>
        <input
          className={clsx(
            'w-3',
            'h-3',
            'text-blue-600',
            'bg-gray-100',
            'border-gray-300',
            'rounded',
            'focus:ring-blue-500'
          )}
          type="checkbox"
          checked={!!info.resume}
          onChange={(e) => handleChange('resume', e.target.checked)}
        />
      </div>
      <div className="flex items-center mb-2">
        <span className="text-xs text-gray-600 w-28 flex-shrink-0">push to hub</span>
        <input
          className={clsx(
            'w-3',
            'h-3',
            'text-blue-600',
            'bg-gray-100',
            'border-gray-300',
            'rounded',
            'focus:ring-blue-500'
          )}
          type="checkbox"
          checked={!!info.pushToHub}
          onChange={(e) => handleChange('pushToHub', e.target.checked)}
        />
      </div>
    </div>
  );
};

export default InfoPanel;
