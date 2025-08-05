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

import React, { useCallback, useEffect, useState } from 'react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import {
  MdRefresh,
  MdFolder,
  MdDescription,
  MdHome,
  MdArrowUpward,
  MdKeyboardArrowRight,
  MdCheck,
  MdStar,
} from 'react-icons/md';
import { useRosServiceCaller } from '../hooks/useRosServiceCaller';

export default function FileBrowser({
  onFileSelect,
  onPathChange,
  initialPath = '',
  fileFilter = null,
  className = '',
  title = 'File Browser',
  targetFileName = null, // 특정 파일이 포함된 폴더를 찾는 경우
  onDirectorySelect = null, // 디렉토리 선택 콜백
  targetFileLabel = null, // 타겟 파일 표시용 커스텀 라벨
  homePath = null, // 홈 버튼 클릭 시 이동할 경로 (기본값: 시스템 홈)
}) {
  const { browseFile } = useRosServiceCaller();

  const [currentPath, setCurrentPath] = useState(initialPath);
  const [parentPath, setParentPath] = useState('');
  const [items, setItems] = useState([]);
  const [selectedItem, setSelectedItem] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [directoriesWithTarget, setDirectoriesWithTarget] = useState(new Set());

  // Check which directories contain the target file
  const checkDirectoriesForTargetFile = useCallback(
    async (itemList) => {
      if (!targetFileName) return;

      const newDirectoriesWithTarget = new Set();
      const directories = itemList.filter((item) => item.is_directory);

      // Check each directory for the target file
      const checkPromises = directories.map(async (dir) => {
        try {
          const result = await browseFile('browse', dir.full_path, '');
          if (result.success && result.items) {
            const hasTargetFile = result.items.some(
              (subItem) => !subItem.is_directory && subItem.name === targetFileName
            );
            if (hasTargetFile) {
              newDirectoriesWithTarget.add(dir.full_path);
            }
          }
        } catch (error) {
          console.log(`Failed to check directory ${dir.name}:`, error);
        }
      });

      await Promise.all(checkPromises);
      setDirectoriesWithTarget(newDirectoriesWithTarget);
    },
    [targetFileName, browseFile]
  );

  // Browse current directory
  const browsePath = useCallback(
    async (path = currentPath, action = 'browse', targetName = '') => {
      setLoading(true);
      setError(null);

      try {
        const result = await browseFile(action, path, targetName);

        if (result.success) {
          setCurrentPath(result.current_path);
          setParentPath(result.parent_path);
          setItems(result.items || []);

          if (onPathChange) {
            onPathChange(result.current_path);
          }

          // If looking for specific file, check which directories contain it
          if (targetFileName && result.items) {
            checkDirectoriesForTargetFile(result.items);
          }
        } else {
          setError(result.message || 'Failed to browse directory');
          toast.error(result.message || 'Failed to browse directory');
        }
      } catch (err) {
        const errorMessage = err.message || 'Failed to browse directory';
        setError(errorMessage);
        toast.error(errorMessage);
        console.error('Browse error:', err);
      } finally {
        setLoading(false);
      }
    },
    [browseFile, currentPath, onPathChange, targetFileName, checkDirectoriesForTargetFile]
  );

  // Initial load
  useEffect(() => {
    if (initialPath) {
      browsePath(initialPath, 'browse');
    } else {
      browsePath('', 'get_path');
    }
  }, [initialPath, browsePath]);

  // Navigate to home directory
  const goHome = useCallback(async () => {
    if (homePath) {
      await browsePath(homePath, 'browse');
    } else {
      await browsePath('', 'get_path');
    }
  }, [browsePath, homePath]);

  // Navigate to parent directory
  const goParent = useCallback(async () => {
    if (parentPath) {
      await browsePath(currentPath, 'go_parent');
    }
  }, [browsePath, currentPath, parentPath]);

  // Handle item click
  const handleItemClick = useCallback(
    async (item) => {
      if (item.is_directory) {
        // If we're looking for a specific file in directories
        if (targetFileName) {
          try {
            // Check if the target file exists in this directory
            const result = await browseFile('browse', item.full_path, '');

            if (result.success && result.items) {
              const hasTargetFile = result.items.some(
                (subItem) => !subItem.is_directory && subItem.name === targetFileName
              );

              if (hasTargetFile) {
                // Target file found! Select this directory
                setSelectedItem(item);
                if (onDirectorySelect) {
                  onDirectorySelect(item);
                } else if (onFileSelect) {
                  onFileSelect(item);
                }
                return;
              }
            }
          } catch (error) {
            console.log('Failed to check directory contents:', error);
          }
        }

        // Target file not found or not looking for specific file - navigate into directory
        await browsePath(currentPath, 'browse', item.name);
        setSelectedItem(null);
      } else {
        // Select file
        setSelectedItem(item);
        if (onFileSelect) {
          onFileSelect(item);
        }
      }
    },
    [browsePath, currentPath, onFileSelect, onDirectorySelect, targetFileName, browseFile]
  );

  // Refresh current directory
  const refresh = useCallback(() => {
    browsePath(currentPath, 'browse');
    setSelectedItem(null);
  }, [browsePath, currentPath]);

  // Filter items based on file filter and targetFileName
  const filteredItems = (() => {
    if (targetFileName) {
      // When looking for specific files in directories, only show directories
      return items.filter((item) => item.is_directory);
    } else if (fileFilter) {
      // Apply file filter when not looking for target files
      return items.filter((item) => item.is_directory || fileFilter(item));
    }
    // Show all items when no filtering is applied
    return items;
  })();

  // Format file size
  const formatFileSize = (bytes) => {
    if (bytes < 0) return '-'; // Directory
    if (bytes === 0) return '0 B';

    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <div className={clsx('bg-white border border-gray-300 rounded-lg', className)}>
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200">
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        <div className="flex items-center space-x-2">
          <button
            onClick={goHome}
            disabled={loading}
            className="p-2 text-gray-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
            title={homePath ? `Home: ${homePath}` : 'Home'}
          >
            <MdHome size={20} />
          </button>
          <button
            onClick={goParent}
            disabled={loading || !parentPath}
            className="p-2 text-gray-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="Parent Directory"
          >
            <MdArrowUpward size={20} />
          </button>
          <button
            onClick={refresh}
            disabled={loading}
            className="p-2 text-gray-600 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <MdRefresh size={20} className={clsx(loading && 'animate-spin')} />
          </button>
        </div>
      </div>

      {/* Current Path */}
      <div className="px-4 py-2 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center text-sm text-gray-600">
          <span className="font-medium">Path:</span>
          <span className="ml-2 font-mono break-all">{currentPath || '/'}</span>
        </div>
        {homePath && (
          <div className="flex items-center mt-1 text-xs text-purple-600">
            <span className="font-medium">Home:</span>
            <span className="ml-2 font-mono bg-purple-100 px-2 py-1 rounded">{homePath}</span>
          </div>
        )}
        {targetFileName && (
          <div className="flex items-center mt-1 text-xs text-blue-600">
            <span className="font-medium">Looking for:</span>
            <span className="ml-2 font-mono bg-blue-100 px-2 py-1 rounded">{targetFileName}</span>
            <span className="ml-2">in directories</span>
          </div>
        )}
      </div>

      {/* Error Display */}
      {error && (
        <div className="px-4 py-3 bg-red-50 border-b border-red-200">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          <span className="ml-2 text-gray-600">Loading...</span>
        </div>
      )}

      {/* File List */}
      {!loading && (
        <div className="max-h-96 overflow-y-auto">
          {filteredItems.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-gray-500">
              <span>No items found</span>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {filteredItems.map((item, index) => {
                const hasTargetFile =
                  targetFileName && item.is_directory && directoriesWithTarget.has(item.full_path);

                return (
                  <div
                    key={index}
                    onClick={() => handleItemClick(item)}
                    className={clsx(
                      'flex items-center px-4 py-3 cursor-pointer transition-colors',
                      hasTargetFile ? 'hover:bg-green-50 bg-green-25' : 'hover:bg-blue-50',
                      selectedItem?.full_path === item.full_path &&
                        (hasTargetFile
                          ? 'bg-green-100 border-l-4 border-green-500'
                          : 'bg-blue-100 border-l-4 border-blue-500')
                    )}
                  >
                    {/* Icon */}
                    <div className="flex-shrink-0 mr-3 relative">
                      {item.is_directory ? (
                        <>
                          <MdFolder
                            className={clsx(
                              'w-5 h-5',
                              hasTargetFile ? 'text-green-500' : 'text-blue-500'
                            )}
                          />
                          {hasTargetFile && (
                            <MdStar className="w-3 h-3 text-yellow-500 absolute -top-1 -right-1" />
                          )}
                        </>
                      ) : (
                        <MdDescription className="w-5 h-5 text-gray-400" />
                      )}
                    </div>

                    {/* File Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center">
                          <p
                            className={clsx(
                              'text-sm font-medium truncate',
                              hasTargetFile ? 'text-green-900' : 'text-gray-900'
                            )}
                          >
                            {item.name}
                          </p>
                          {hasTargetFile && (
                            <span className="ml-2 text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">
                              {targetFileLabel || `Contains ${targetFileName}`}
                            </span>
                          )}
                        </div>
                        {selectedItem?.full_path === item.full_path && (
                          <MdCheck
                            className={clsx(
                              'w-4 h-4 ml-2',
                              hasTargetFile ? 'text-green-600' : 'text-blue-600'
                            )}
                          />
                        )}
                      </div>
                      <div className="flex items-center mt-1 text-xs text-gray-500">
                        <span>{formatFileSize(item.size)}</span>
                        <span className="mx-2">•</span>
                        <span>{item.modified_time}</span>
                      </div>
                    </div>

                    {/* Directory Indicator */}
                    {item.is_directory && (
                      <MdKeyboardArrowRight className="w-4 h-4 text-gray-400 ml-2" />
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Selected Item Info */}
      {selectedItem && (
        <div
          className={clsx(
            'px-4 py-3 border-t',
            selectedItem.is_directory &&
              targetFileName &&
              directoriesWithTarget.has(selectedItem.full_path)
              ? 'bg-green-50 border-green-200'
              : 'bg-blue-50 border-blue-200'
          )}
        >
          <div className="text-sm">
            {selectedItem.is_directory ? (
              <>
                <p
                  className={clsx(
                    'font-medium',
                    targetFileName && directoriesWithTarget.has(selectedItem.full_path)
                      ? 'text-green-900'
                      : 'text-blue-900'
                  )}
                >
                  Selected Directory:
                </p>
                <p
                  className={clsx(
                    'font-mono break-all mt-1',
                    targetFileName && directoriesWithTarget.has(selectedItem.full_path)
                      ? 'text-green-700'
                      : 'text-blue-700'
                  )}
                >
                  {selectedItem.full_path}
                </p>
                {targetFileName && directoriesWithTarget.has(selectedItem.full_path) && (
                  <p className="text-green-600 text-xs mt-2 flex items-center">
                    <MdStar className="w-3 h-3 mr-1" />
                    {targetFileLabel || `This directory contains ${targetFileName}`}
                  </p>
                )}
              </>
            ) : (
              <>
                <p className="font-medium text-blue-900">Selected File:</p>
                <p className="text-blue-700 font-mono break-all mt-1">{selectedItem.full_path}</p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
