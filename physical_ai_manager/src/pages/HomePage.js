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

export default function HomePage({ rosHost }) {
  const rosbridgeUrl = `ws://${rosHost.split(':')[0]}:9090`;

  return (
    <div className="w-full h-full flex items-start justify-center text-xl flex-row gap-8">
      <div className="flex flex-col items-center mt-10 w-full">
        <div className="mb-6 text-3xl font-semibold">Home Page</div>
        <div className="text-gray-500 text-base">This is the home page.</div>
      </div>
    </div>
  );
}
