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

import React, { useCallback, useMemo, useState } from 'react';
import clsx from 'clsx';
import { useSelector, useDispatch } from 'react-redux';
import toast from 'react-hot-toast';
import { TbArrowMerge } from 'react-icons/tb';
import { MdFolderOpen, MdClose } from 'react-icons/md';
import {
  setMergeSourceTaskDirs,
  setMergeOutputPath,
  setMergeOutputFolderName,
  setMergeMoveSources,
} from '../editDatasetSlice';
import { useRosServiceCaller } from '../../../hooks/useRosServiceCaller';
import FileBrowserModal from '../../../components/FileBrowserModal';
import { DEFAULT_PATHS } from '../../../constants/paths';

const STYLES = {
  textInput: clsx(
    'text-sm w-full h-8 p-2 border border-gray-300 rounded-md',
    'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent'
  ),
};

export default function MergeSection({ isEditable = true }) {
  const dispatch = useDispatch();
  const { sendEditDatasetCommand } = useRosServiceCaller();

  const mergeSourceTaskDirs = useSelector(
    (state) => state.editDataset.mergeSourceTaskDirs
  );
  const mergeOutputPath = useSelector((state) => state.editDataset.mergeOutputPath);
  const mergeOutputFolderName = useSelector(
    (state) => state.editDataset.mergeOutputFolderName
  );
  const mergeMoveSources = useSelector((state) => state.editDataset.mergeMoveSources);

  const [showSourcePicker, setShowSourcePicker] = useState(false);
  const [showOutputPicker, setShowOutputPicker] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const handleAddSources = useCallback(
    (selectedItems) => {
      const items = Array.isArray(selectedItems) ? selectedItems : [selectedItems];
      const newPaths = items
        .map((it) => it.full_path || it.path || '')
        .filter((p) => p);
      const merged = Array.from(new Set([...(mergeSourceTaskDirs || []), ...newPaths]));
      dispatch(setMergeSourceTaskDirs(merged));
    },
    [dispatch, mergeSourceTaskDirs]
  );

  const removeSource = useCallback(
    (idx) => {
      const next = (mergeSourceTaskDirs || []).filter((_, i) => i !== idx);
      dispatch(setMergeSourceTaskDirs(next));
    },
    [dispatch, mergeSourceTaskDirs]
  );

  const handleOutputPathSelect = useCallback(
    (item) => {
      dispatch(setMergeOutputPath(item.full_path || item.path || ''));
      setShowOutputPicker(false);
    },
    [dispatch]
  );

  const handleMerge = useCallback(async () => {
    if (!mergeSourceTaskDirs || mergeSourceTaskDirs.length < 2) {
      toast.error('Pick at least 2 source task folders to merge.');
      return;
    }
    if (!mergeOutputPath) {
      toast.error('Pick a parent directory for the merged output.');
      return;
    }
    if (!mergeOutputFolderName) {
      toast.error('Enter a name for the merged output folder.');
      return;
    }

    setSubmitting(true);
    try {
      const result = await sendEditDatasetCommand('merge');
      if (result?.success) {
        toast.success(
          result.message ||
            `Merged ${result.affected_count || 0} episodes successfully.`
        );
        dispatch(setMergeSourceTaskDirs([]));
        dispatch(setMergeOutputFolderName(''));
      } else {
        toast.error(result?.message || 'Merge failed.');
      }
    } catch (err) {
      toast.error(err.message || 'Merge request failed.');
    } finally {
      setSubmitting(false);
    }
  }, [
    mergeSourceTaskDirs,
    mergeOutputPath,
    mergeOutputFolderName,
    sendEditDatasetCommand,
    dispatch,
  ]);

  const fullOutputPath = useMemo(() => {
    const base = (mergeOutputPath || '').replace(/\/$/, '');
    return mergeOutputFolderName ? `${base}/${mergeOutputFolderName}` : base;
  }, [mergeOutputPath, mergeOutputFolderName]);

  const canSubmit =
    isEditable &&
    !submitting &&
    mergeSourceTaskDirs &&
    mergeSourceTaskDirs.length >= 2 &&
    mergeOutputPath &&
    mergeOutputFolderName;

  return (
    <div className="w-full flex flex-col items-center justify-start bg-gray-100 p-10 gap-8 rounded-xl">
      <div className="w-full flex items-center justify-start gap-2">
        <TbArrowMerge className="w-7 h-7 text-blue-500 rotate-90" />
        <span className="text-2xl font-bold">Merge Rosbag Task Folders</span>
      </div>

      <div className="w-full flex flex-row items-stretch gap-6">
        {/* Source list ----------------------------------------------------- */}
        <div className="flex-1 bg-white p-5 rounded-md shadow-md flex flex-col gap-3 min-w-72">
          <div className="text-xl font-bold">Source task folders</div>
          <div className="text-xs text-gray-500">
            Pick the rosbag2 task folders you want to combine. All episodes are
            renumbered to a contiguous 0..N-1 sequence in the output.
          </div>

          {mergeSourceTaskDirs && mergeSourceTaskDirs.length > 0 ? (
            <div className="flex flex-col gap-1">
              {mergeSourceTaskDirs.map((p, idx) => (
                <div
                  key={`${p}-${idx}`}
                  className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded px-2 py-1 text-xs"
                >
                  <span className="text-gray-500 font-mono w-5">{idx}.</span>
                  <span className="flex-1 truncate text-gray-700" title={p}>
                    {p}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeSource(idx)}
                    disabled={!isEditable || submitting}
                    className="text-red-400 hover:text-red-600 disabled:opacity-50"
                    aria-label={`Remove source ${idx}`}
                  >
                    <MdClose />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-gray-400">No sources picked yet.</div>
          )}

          <button
            type="button"
            onClick={() => setShowSourcePicker(true)}
            disabled={!isEditable || submitting}
            className="self-start mt-1 px-3 py-1.5 text-xs font-medium rounded-md bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-50 flex items-center gap-1"
          >
            <MdFolderOpen size={14} /> Add task folder
          </button>

          <label className="flex items-center gap-2 mt-2 cursor-pointer">
            <input
              type="checkbox"
              checked={Boolean(mergeMoveSources)}
              onChange={(e) => dispatch(setMergeMoveSources(e.target.checked))}
              disabled={!isEditable || submitting}
              className="rounded"
            />
            <span className="text-sm text-gray-700">
              Move sources after merge (frees disk; cannot be undone)
            </span>
          </label>
        </div>

        {/* Output ---------------------------------------------------------- */}
        <div className="flex-1 bg-white p-5 rounded-md shadow-md flex flex-col gap-3 min-w-72">
          <div className="text-xl font-bold">Output task folder</div>
          <div className="text-xs text-gray-500">
            The output is created at <code>parent / folder name</code>. The
            folder must not already exist (or must be empty).
          </div>

          <div className="flex flex-row items-center gap-2">
            <input
              className={STYLES.textInput}
              type="text"
              placeholder="Parent directory"
              value={mergeOutputPath || ''}
              onChange={(e) => dispatch(setMergeOutputPath(e.target.value))}
              disabled={!isEditable || submitting}
            />
            <button
              type="button"
              onClick={() => setShowOutputPicker(true)}
              disabled={!isEditable || submitting}
              className="flex items-center justify-center w-10 h-10 text-blue-500 bg-gray-200 rounded-md hover:text-blue-700 disabled:opacity-50"
              aria-label="Browse output directory"
            >
              <MdFolderOpen className="w-6 h-6" />
            </button>
          </div>

          <input
            className={STYLES.textInput}
            type="text"
            placeholder="Output folder name (e.g. ffw_sg2_rev1_recycle_merged)"
            value={mergeOutputFolderName || ''}
            onChange={(e) => dispatch(setMergeOutputFolderName(e.target.value))}
            disabled={!isEditable || submitting}
          />

          <div className="flex items-center gap-2 mt-1 text-xs">
            <span className="bg-blue-400 text-white font-bold py-0.5 px-2 rounded-full">
              Output
            </span>
            <span className="text-blue-600 break-all">{fullOutputPath || '—'}</span>
          </div>
        </div>
      </div>

      <button
        type="button"
        onClick={handleMerge}
        disabled={!canSubmit}
        className={clsx(
          'px-6 py-3 text-base font-semibold rounded-xl shadow-md transition-colors',
          canSubmit
            ? 'bg-green-500 text-white hover:bg-green-600'
            : 'bg-gray-300 text-gray-500 cursor-not-allowed'
        )}
      >
        {submitting ? 'Merging…' : 'Merge'}
      </button>

      {/* Pickers ----------------------------------------------------------- */}
      <FileBrowserModal
        isOpen={showSourcePicker}
        onClose={() => setShowSourcePicker(false)}
        onFileSelect={(items) => {
          handleAddSources(items);
          setShowSourcePicker(false);
        }}
        title="Select source task folders"
        selectButtonText="Add"
        allowDirectorySelect={true}
        allowFileSelect={false}
        initialPath={DEFAULT_PATHS.ROSBAG2_PATH}
        defaultPath={DEFAULT_PATHS.ROSBAG2_PATH}
        homePath=""
        multiSelect={true}
      />
      <FileBrowserModal
        isOpen={showOutputPicker}
        onClose={() => setShowOutputPicker(false)}
        onFileSelect={handleOutputPathSelect}
        title="Select parent directory for the merged output"
        selectButtonText="Select"
        allowDirectorySelect={true}
        allowFileSelect={false}
        initialPath={DEFAULT_PATHS.ROSBAG2_PATH}
        defaultPath={DEFAULT_PATHS.ROSBAG2_PATH}
        homePath=""
      />
    </div>
  );
}
