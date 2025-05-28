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
import './InfoPanel.css';

const InfoPanel = ({ info, onChange }) => {
  const handleChange = (field, value) => {
    onChange({ ...info, [field]: value });
  };

  return (
    <div className="info-panel">
      <div style={{ fontSize: 20, fontWeight: 600, marginBottom: 16 }}>Task Information</div>
      <div className="info-panel-row">
        <span className="label">task name</span>
        <textarea
          className="value"
          style={{ fontSize: '15px', resize: 'vertical', minHeight: '16px', maxHeight: '100px' }}
          value={info.taskName || ''}
          onChange={(e) => handleChange('taskName', e.target.value)}
        />
      </div>
      <div className="info-panel-row">
        <span className="label">robot type</span>
        <input
          className="value"
          type="text"
          value={info.robotType || ''}
          onChange={(e) => handleChange('robotType', e.target.value)}
        />
      </div>
      <div className="info-panel-row">
        <span className="label">task type</span>
        <input
          className="value"
          type="text"
          value={info.taskType || ''}
          onChange={(e) => handleChange('taskType', e.target.value)}
        />
      </div>
      <div className="info-panel-row">
        <span className="label">task instruction</span>
        <textarea
          className="value"
          style={{ fontSize: '15px', resize: 'vertical', minHeight: '32px', maxHeight: '120px' }}
          value={info.taskInstruction || ''}
          onChange={(e) => handleChange('taskInstruction', e.target.value)}
        />
      </div>
      <div className="info-panel-row">
        <span className="label">fps</span>
        <input
          className="value"
          type="number"
          value={info.fps || ''}
          onChange={(e) => handleChange('fps', Number(e.target.value))}
        />
      </div>
      <div className="info-panel-row">
        <span className="label">tags</span>
        <input
          className="value"
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
      <div className="info-panel-row">
        <span className="label">warmup time (s)</span>
        <input
          className="value"
          type="text"
          value={info.warmupTime || ''}
          onChange={(e) => handleChange('warmupTime', e.target.value)}
        />
      </div>
      <div className="info-panel-row">
        <span className="label">episode time (s)</span>
        <input
          className="value"
          type="text"
          value={info.episodeTime || ''}
          onChange={(e) => handleChange('episodeTime', e.target.value)}
        />
      </div>
      <div className="info-panel-row">
        <span className="label">reset time (s)</span>
        <input
          className="value"
          type="text"
          value={info.resetTime || ''}
          onChange={(e) => handleChange('resetTime', e.target.value)}
        />
      </div>
      <div className="info-panel-row">
        <span className="label">num episodes</span>
        <input
          className="value"
          type="number"
          value={info.numEpisodes || ''}
          onChange={(e) => handleChange('numEpisodes', Number(e.target.value))}
        />
      </div>
      <div className="info-panel-row">
        <span className="label">resume</span>
        <input
          className="value"
          type="checkbox"
          checked={!!info.resume}
          onChange={(e) => handleChange('resume', e.target.checked)}
        />
      </div>
      <div className="info-panel-row">
        <span className="label">push to hub</span>
        <input
          className="value"
          type="checkbox"
          checked={!!info.pushToHub}
          onChange={(e) => handleChange('pushToHub', e.target.checked)}
        />
      </div>
    </div>
  );
};

export default InfoPanel;
