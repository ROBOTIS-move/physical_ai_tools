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

import React, { useState, useCallback } from 'react';
import { MdClose, MdFolderOpen } from 'react-icons/md';
import FileBrowser from './FileBrowser';

export default function FileBrowserModal({
  isOpen,
  onClose,
  onFileSelect,
  initialPath = '',
  fileFilter = null,
  title = 'Select File',
  selectButtonText = 'Select',
  allowDirectorySelect = false,
  targetFileName = null,
  targetFileLabel = null,
  homePath = null,
}) {
  const [selectedItem, setSelectedItem] = useState(null);
  const [currentPath, setCurrentPath] = useState(initialPath);

  const handleFileSelect = useCallback((item) => {
    setSelectedItem(item);
  }, []);

  const handlePathChange = useCallback((path) => {
    setCurrentPath(path);
  }, []);

  const handleConfirm = useCallback(() => {
    if (selectedItem) {
      onFileSelect(selectedItem);
      onClose();
      setSelectedItem(null);
    } else if (allowDirectorySelect && currentPath) {
      // If directory selection is allowed and no file is selected, select current directory
      onFileSelect({
        name: currentPath.split('/').pop() || currentPath,
        full_path: currentPath,
        is_directory: true,
        size: -1,
        modified_time: '',
      });
      onClose();
    }
  }, [selectedItem, currentPath, allowDirectorySelect, onFileSelect, onClose]);

  const handleCancel = useCallback(() => {
    onClose();
    setSelectedItem(null);
  }, [onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black bg-opacity-50 transition-opacity" />

      {/* Modal */}
      <div className="flex min-h-full items-center justify-center p-4">
        <div className="relative bg-white rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <h2 className="text-xl font-semibold text-gray-900">{title}</h2>
            <button
              onClick={handleCancel}
              className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <MdClose size={24} />
            </button>
          </div>

          {/* File Browser Content */}
          <div className="flex-1 overflow-hidden">
            <FileBrowser
              onFileSelect={handleFileSelect}
              onPathChange={handlePathChange}
              initialPath={initialPath}
              fileFilter={fileFilter}
              className="border-0 rounded-none h-full"
              title=""
              targetFileName={targetFileName}
              onDirectorySelect={handleFileSelect}
              targetFileLabel={targetFileLabel}
              homePath={homePath}
            />
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 bg-gray-50">
            <div className="flex items-center text-sm text-gray-600">
              {selectedItem ? (
                <div className="flex items-center">
                  <MdFolderOpen className="w-4 h-4 mr-2" />
                  <span className="font-medium">Selected:</span>
                  <span className="ml-2 font-mono break-all">{selectedItem.name}</span>
                </div>
              ) : allowDirectorySelect && currentPath ? (
                <div className="flex items-center">
                  <MdFolderOpen className="w-4 h-4 mr-2" />
                  <span className="font-medium">Current Directory:</span>
                  <span className="ml-2 font-mono break-all">{currentPath}</span>
                </div>
              ) : (
                <span>
                  {allowDirectorySelect
                    ? 'Select a file or use current directory'
                    : 'Select a file to continue'}
                </span>
              )}
            </div>

            <div className="flex items-center space-x-3">
              <button
                onClick={handleCancel}
                className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirm}
                disabled={!selectedItem && !(allowDirectorySelect && currentPath)}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
              >
                {selectButtonText}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
