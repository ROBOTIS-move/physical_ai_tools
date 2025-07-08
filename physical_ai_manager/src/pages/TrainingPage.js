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
import { MdRefresh } from 'react-icons/md';
import HeartbeatStatus from '../components/HeartbeatStatus';

export default function TrainingPage() {
  const itemList = ['item1', 'item2', 'item3'];

  const title = 'Training';
  const itemType = 'Item';

  const [loading, setLoading] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [selectedItem, setSelectedItem] = useState('');

  const fetchItemList = async () => {
    setFetching(true);
    try {
      // const result = await getItemList();
      console.log('fetching item list');
      await new Promise((resolve) => setTimeout(resolve, 1000));
      console.log('item list fetched');
    } catch (error) {
      console.error('Error fetching item list:', error);
    } finally {
      setFetching(false);
    }
  };

  const classContainer = clsx(
    'w-full',
    'h-full',
    'flex',
    'items-center',
    'justify-center',
    'pt-10'
  );

  const classHeartbeatStatus = clsx('absolute', 'top-5', 'left-35', 'z-10');

  const classCard = clsx(
    'bg-white',
    'border',
    'border-gray-200',
    'rounded-2xl',
    'shadow-lg',
    'p-8',
    'w-full',
    'max-w-md'
  );

  const classSelect = clsx(
    'w-full',
    'px-3',
    'py-2',
    'border',
    'border-gray-300',
    'rounded-md',
    'focus:outline-none',
    'focus:ring-2',
    'focus:ring-blue-500',
    'focus:border-transparent',
    'mb-4'
  );

  const classCurrentType = clsx(
    'text-sm',
    'text-gray-600',
    'bg-gray-100',
    'px-3',
    'py-2',
    'rounded-md',
    'text-center',
    'mb-4'
  );

  const classRefreshButton = clsx(
    'w-full',
    'px-4',
    'py-2',
    'bg-gray-500',
    'text-white',
    'rounded-md',
    'font-medium',
    'transition-colors',
    'hover:bg-gray-600',
    'disabled:bg-gray-400',
    'disabled:cursor-not-allowed'
  );

  const classTitle = clsx('text-2xl', 'font-bold', 'text-gray-800', 'mb-6', 'text-center');
  const classLabel = clsx('text-sm', 'font-medium', 'text-gray-700', 'mb-2', 'block');

  return (
    <div className={classContainer}>
      <div className={classHeartbeatStatus}>
        <HeartbeatStatus />
      </div>
      <div className={classCard}>
        <h1 className={classTitle}>{title}</h1>
        <label className={classLabel}>Select {itemType}:</label>

        <select
          className={classSelect}
          value={selectedItem}
          onChange={(e) => setSelectedItem(e.target.value)}
          disabled={fetching || loading}
        >
          <option value="" disabled>
            Choose a {itemType}...
          </option>
          {itemList.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <button
          className={classRefreshButton}
          onClick={fetchItemList}
          disabled={fetching || loading}
        >
          <div className="flex items-center justify-center gap-2">
            <MdRefresh size={16} className={fetching ? 'animate-spin' : ''} />
            {fetching ? 'Loading...' : `Refresh ${itemType} List`}
          </div>
        </button>
      </div>
    </div>
  );
}
