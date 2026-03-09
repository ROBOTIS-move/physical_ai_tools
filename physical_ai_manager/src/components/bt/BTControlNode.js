// Copyright 2026 ROBOTIS CO., LTD.
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
// Author: Seongwoo Kim

import React from 'react';
import { Handle, Position } from '@xyflow/react';

const TYPE_ICONS = {
  Sequence: '→',
  Loop: '↻',
  Fallback: '?',
  Parallel: '⇉',
};

export default function BTControlNode({ data }) {
  const icon = TYPE_ICONS[data.nodeType] || '□';

  return (
    <div
      className="px-4 py-3 rounded-lg border-2 border-blue-500 bg-blue-50 min-w-[160px] text-center shadow-sm"
    >
      <Handle type="target" position={Position.Top} className="!bg-blue-500" />
      <div className="text-xs text-blue-600 font-semibold mb-1">
        {icon} {data.nodeType}
      </div>
      <div className="text-sm font-medium text-gray-800 truncate">
        {data.label}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-blue-500" />
    </div>
  );
}
