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

import React, { useState } from 'react';
import clsx from 'clsx';
import { useSelector } from 'react-redux';
import TaskPhase from '../constants/taskPhases';

const STATUS_OK = 0;
const STATUS_SLOW = 1;
const STATUS_STALLED = 2;

const statusColor = {
  [STATUS_OK]: 'bg-green-500',
  [STATUS_SLOW]: 'bg-yellow-400',
  [STATUS_STALLED]: 'bg-red-500',
};

const statusLabel = {
  [STATUS_OK]: 'OK',
  [STATUS_SLOW]: 'Slow',
  [STATUS_STALLED]: 'Stalled',
};

const shortenTopic = (name) => {
  const parts = (name || '').split('/').filter(Boolean);
  if (parts.length <= 2) return name;
  return '.../' + parts.slice(-2).join('/');
};

function TopicRow({ t }) {
  return (
    <tr className="border-b border-gray-50 last:border-0">
      <td className="py-1 truncate max-w-[160px]" title={t.name}>
        {shortenTopic(t.name)}
      </td>
      <td className="py-1 text-right font-mono text-gray-700">
        {t.rateHz.toFixed(1)}
      </td>
      <td className="py-1 text-center">
        <span
          className={clsx(
            'inline-block w-2.5 h-2.5 rounded-full',
            statusColor[t.status] || 'bg-gray-300'
          )}
          title={`${statusLabel[t.status] || '?'} (baseline ${t.baselineHz.toFixed(1)} Hz, last ${t.secondsSinceLast >= 0 ? t.secondsSinceLast.toFixed(1) + 's ago' : 'never'})`}
        />
      </td>
    </tr>
  );
}

export default function RecordTopicMonitor() {
  const phase = useSelector((state) => state.tasks.taskStatus.phase);
  const monitor = useSelector((state) => state.tasks.recordingMonitor);
  const [expanded, setExpanded] = useState(false);

  const isRecording =
    phase === TaskPhase.WARMING_UP ||
    phase === TaskPhase.RESETTING ||
    phase === TaskPhase.RECORDING ||
    phase === TaskPhase.SAVING;

  if (!isRecording || !monitor?.topics?.length) return null;

  const problemTopics = monitor.topics.filter((t) => t.status !== STATUS_OK);
  const okCount = monitor.topics.length - problemTopics.length;
  const allOk = problemTopics.length === 0;

  // Overall status dot colour: worst status wins.
  const worstStatus = monitor.topics.reduce(
    (max, t) => Math.max(max, t.status),
    STATUS_OK
  );
  const overallColor = statusColor[worstStatus] || 'bg-green-500';

  const sorted = [...monitor.topics].sort((a, b) => b.status - a.status);

  return (
    <div className="bg-white border border-gray-200 rounded-2xl shadow-md p-3 w-full h-full overflow-y-auto">
      {/* Header — always visible */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between text-sm cursor-pointer hover:bg-gray-50 rounded-lg px-1 py-0.5"
      >
        <div className="flex items-center gap-2">
          <span className={clsx('inline-block w-3 h-3 rounded-full', overallColor)} />
          <span className="font-semibold text-gray-800">Topic Monitor</span>
        </div>
        <span className="text-xs text-gray-400">
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {/* Compact summary — always visible */}
      <div className="text-xs text-gray-500 mt-1 px-1">
        {allOk ? (
          <span className="text-green-600 font-medium">All {okCount} topics OK</span>
        ) : (
          <span>
            <span className="text-red-500 font-medium">{problemTopics.length} issue(s)</span>
            {' / '}
            {monitor.topics.length} topics
          </span>
        )}
      </div>

      {/* Problem topics — always visible when there are issues */}
      {!allOk && !expanded && (
        <table className="w-full text-xs mt-2">
          <tbody>
            {problemTopics.map((t) => (
              <TopicRow key={t.name} t={t} />
            ))}
          </tbody>
        </table>
      )}

      {/* Full list — only when expanded */}
      {expanded && (
        <table className="w-full text-xs mt-2">
          <thead>
            <tr className="text-gray-500 border-b border-gray-100">
              <th className="text-left py-1 font-medium">Topic</th>
              <th className="text-right py-1 font-medium w-14">Hz</th>
              <th className="text-center py-1 font-medium w-12">Status</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((t) => (
              <TopicRow key={t.name} t={t} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
