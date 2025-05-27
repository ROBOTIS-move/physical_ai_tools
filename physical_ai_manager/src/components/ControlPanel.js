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

import React, { useState, useEffect, useRef } from 'react';
import ProgressBar from './ProgressBar';
import { MdPlayArrow, MdStop, MdReplay, MdSkipNext, MdCheck } from 'react-icons/md';

const panelStyle = {
  height: 200,
  background: '#bdbdbd',
  borderRadius: 27,
  margin: 30,
  padding: 14,
  display: 'flex',
  flexDirection: 'row',
  alignItems: 'center',
  gap: 8,
  boxShadow: 'rgba(0, 0, 0, 0.1) 0px 2px 8px',
};

const buttonStyle = {
  fontSize: '40px',
  fontFamily: 'Pretendard Variable',
  fontWeight: 800,
  height: '100%',
  flexGrow: 1,
  minWidth: 60,
  borderRadius: 20,
  border: 'none',
  background: '#ededed',
  cursor: 'pointer',
  marginRight: 8,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  flexDirection: 'column',
  gap: 4,
};

const iconWrapperStyle = {
  background: 'transparent',
  borderRadius: '50%',
  width: 86,
  height: 86,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  marginBottom: 4,
};

const buttons = [
  { label: 'Start', icon: MdPlayArrow, color: '#1976d2' },
  { label: 'Stop', icon: MdStop, color: '#d32f2f' },
  { label: 'Retry', icon: MdReplay, color: '#fbc02d' },
  { label: 'Next', icon: MdSkipNext, color: '#388e3c' },
  { label: 'Finish', icon: MdCheck, color: '#388e3c' },
];

export default function ControlPanel() {
  const icon_size = 70;
  const [hovered, setHovered] = useState(null);
  const [pressed, setPressed] = useState(null);
  const [started, setStarted] = useState(false);
  const startedRef = useRef(started);

  useEffect(() => {
    startedRef.current = started;
  }, [started]);

  const handleCommand = (label) => {
    console.log(label + ' command executed');
    if (label === 'Start') setStarted(true);
    if (label === 'Stop') setStarted(false);
    // 다른 명령은 상태 변화 없음
  };

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'ArrowLeft') {
        handleCommand('Retry');
      } else if (e.key === 'ArrowRight') {
        handleCommand('Next');
      } else if (e.key === ' ' || e.key === 'Spacebar' || e.code === 'Space') {
        if (!startedRef.current) {
          handleCommand('Start');
        } else {
          handleCommand('Stop');
        }
      } else if ((e.ctrlKey || e.metaKey) && (e.key === 'c' || e.key === 'C')) {
        handleCommand('Finish');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <div className="control-panel-fixed" style={panelStyle}>
      <div
        style={{
          display: 'flex',
          flex: 2,
          alignItems: 'center',
          width: '100%',
          height: '100%',
          gap: 16,
        }}
      >
        {buttons.map(({ label, icon: Icon, color }) => {
          let bg = buttonStyle.background;
          if (pressed === label) {
            bg = '#d1d1d1';
          } else if (hovered === label) {
            bg = '#e0e0e0';
          }
          return (
            <button
              key={label}
              style={{ ...buttonStyle, background: bg }}
              tabIndex={0}
              onClick={() => handleCommand(label)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  handleCommand(label);
                }
                if (e.key === ' ') {
                  e.preventDefault();
                }
              }}
              onMouseEnter={() => setHovered(label)}
              onMouseLeave={() => {
                setHovered(null);
                setPressed(null);
              }}
              onMouseDown={() => setPressed(label)}
              onMouseUp={() => setPressed(null)}
            >
              <span style={iconWrapperStyle}>
                <Icon size={icon_size} color={color} />
              </span>
              {label}
            </button>
          );
        })}
      </div>
      <div
        style={{
          display: 'flex',
          flex: 1,
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          width: '100%',
          gap: 30,
        }}
      >
        <div style={{ flex: 1, minWidth: 0, fontSize: 33, textAlign: 'center' }}>
          Please prepare next episode
        </div>
        <ProgressBar percent={60} />
      </div>
    </div>
  );
}
