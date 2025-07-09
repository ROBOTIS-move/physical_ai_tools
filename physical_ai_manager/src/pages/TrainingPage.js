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
import HeartbeatStatus from '../components/HeartbeatStatus';
import DatasetSelector from '../components/DatasetSelector';
import PolicySelector from '../components/PolicySelector';

export default function TrainingPage() {
  const classContainer = clsx(
    'w-full',
    'h-full',
    'flex',
    'items-center',
    'justify-center',
    'pt-10',
    'gap-8'
  );

  const classHeartbeatStatus = clsx('absolute', 'top-5', 'left-35', 'z-10');

  return (
    <div className={classContainer}>
      <div className={classHeartbeatStatus}>
        <HeartbeatStatus />
      </div>

      <div className="w-full h-full flex p-10 gap-8 items-start justify-start">
        {/* Dataset Selector */}
        <DatasetSelector />

        {/* Policy Selector */}
        <PolicySelector />
      </div>
    </div>
  );
}
