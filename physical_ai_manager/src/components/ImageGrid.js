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

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useSelector, useDispatch, useStore } from 'react-redux';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { useRosServiceCaller } from '../hooks/useRosServiceCaller';
import ImageGridCell from './ImageGridCell';
import ImageTopicSelectModal from './ImageTopicSelectModal';
import { setImageTopicList, setAssignedImageTopics } from '../features/ros/rosSlice';

// [left(idx 0), center(idx 1), right(idx 2)]
// rotate: true = wrist camera (landscape stream displayed as portrait)
const DEFAULT_LAYOUT = [
  { aspect: '3/4', rotate: true },
  { aspect: '16/9', rotate: false },
  { aspect: '3/4', rotate: true },
];

// Robot-type specific camera topic assignments: [left, center, right]
const ROBOT_CAMERA_PRESETS = {
  ffw_sg2_rev1: [
    '/robot/camera/cam_left_wrist/image_raw/compressed',
    '/robot/camera/cam_left_head/image_raw/compressed',
    '/robot/camera/cam_right_wrist/image_raw/compressed',
  ],
  ffw_bg2_rev4: [
    '/robot/camera/cam_left_wrist/image_raw/compressed',
    '/robot/camera/cam_left_head/image_raw/compressed',
    '/robot/camera/cam_right_wrist/image_raw/compressed',
  ],
  omy_f3m_3cam: [
    '/camera/cam_wrist/color/image_rect_raw/compressed',
    '/camera/cam_top/color/image_rect_raw/compressed',
    '/camera/cam_belly/color/image_rect_raw/compressed',
  ],
};

export default function ImageGrid({ isActive = true }) {
  const dispatch = useDispatch();
  const store = useStore();
  const imageTopicList = useSelector((state) => state.ros.imageTopicList);
  const robotType = useSelector((state) => state.tasks.taskStatus.robotType);

  const [modalOpen, setModalOpen] = React.useState(false);
  const [selectedIdx, setSelectedIdx] = React.useState(null);
  const [isLoadingTopics, setIsLoadingTopics] = useState(false);
  const [topicListError, setTopicListError] = useState(null);
  // Mount-time initial value: prefer whatever this component last persisted
  // (so Record↔Inference page transitions remember the user's selection),
  // otherwise fall back to the robot preset. We deliberately read via
  // store.getState() instead of useSelector so the component does NOT
  // subscribe to this slice — the only writer is this component itself, and
  // round-tripping our own dispatch back into local state used to ping-pong
  // with the persist effect below (React error #185, blank screen on page
  // transition).
  const [asignedImageTopicList, setAsignedImageTopicList] = useState(() => {
    const saved = store.getState().ros.assignedImageTopics;
    if (
      Array.isArray(saved) &&
      saved.length === DEFAULT_LAYOUT.length &&
      saved.some(Boolean)
    ) {
      return [...saved];
    }
    return Array(DEFAULT_LAYOUT.length).fill(null);
  });
  // Track which robotType's preset has been applied; null = not yet applied
  const [presetRobotType, setPresetRobotType] = useState(null);
  // Per-cell rotation override: 0 = landscape, -90 = portrait; undefined = use layout default
  const [rotationOverrides, setRotationOverrides] = useState({});

  const { getImageTopicList } = useRosServiceCaller();

  const layout = DEFAULT_LAYOUT;

  const rotationDegrees = useMemo(
    () => layout.map((cell, idx) => rotationOverrides[idx] ?? (cell.rotate ? -90 : 0)),
    [layout, rotationOverrides]
  );

  const handleRotateClick = useCallback((idx) => {
    setRotationOverrides((prev) => ({
      ...prev,
      [idx]: rotationDegrees[idx] === -90 ? 0 : -90,
    }));
  }, [rotationDegrees]);

  const preset = useMemo(
    () => ROBOT_CAMERA_PRESETS[robotType] || null,
    [robotType]
  );

  // Apply preset on robotType change; on first mount, preserve saved topics if any.
  useEffect(() => {
    if (!preset) return;
    if (presetRobotType === robotType) return;

    const isFirstMount = presetRobotType === null;
    const hasLocal = asignedImageTopicList.length === layout.length && asignedImageTopicList.some(Boolean);

    if (isFirstMount && hasLocal) {
      // Preserve topics saved from a previous session
      setPresetRobotType(robotType);
      return;
    }

    setAsignedImageTopicList([...preset]);
    setPresetRobotType(robotType);
    console.log(`Applied camera preset for ${robotType}:`, preset);
  }, [preset, robotType, presetRobotType, asignedImageTopicList, layout.length]);

  const autoAssignTopics = useCallback((imageTopics, isRefresh = false) => {
    if (imageTopics.length > 0) {
      const autoTopics = Array(layout.length).fill(null);
      const assignmentOrder = [1, 0, 2];

      for (let i = 0; i < Math.min(imageTopics.length, assignmentOrder.length); i++) {
        autoTopics[assignmentOrder[i]] = imageTopics[i];
      }

      console.log(`${isRefresh ? 'Re-assigned' : 'Auto-assigned'} topics:`, autoTopics);
      setAsignedImageTopicList(autoTopics);
      toast.success(
        `${isRefresh ? 'Re-a' : 'Auto-a'}ssigned ${Math.min(imageTopics.length, 3)} topics to grid`
      );
    }
  }, [layout.length]);

  // Sync list length when layout length changes (extend or trim)
  useEffect(() => {
    setAsignedImageTopicList((prev) => {
      const L = layout.length;
      if (prev.length === L) return prev;
      if (prev.length < L) return [...prev, ...Array(L - prev.length).fill(null)];
      return prev.slice(0, L);
    });
  }, [layout]);

  // Persist topic assignment to Redux so it survives remounts (page swap).
  // Compare against the latest store value via getState() so we never
  // re-trigger this effect from our own dispatch.
  useEffect(() => {
    if (asignedImageTopicList.length === 0) return;
    const current = store.getState().ros.assignedImageTopics;
    const same =
      Array.isArray(current) &&
      current.length === asignedImageTopicList.length &&
      asignedImageTopicList.every((t, i) => t === current[i]);
    if (!same) {
      dispatch(setAssignedImageTopics(asignedImageTopicList));
    }
  }, [asignedImageTopicList, dispatch, store]);

  useEffect(() => {
    const fetchTopicList = async () => {
      setIsLoadingTopics(true);
      setTopicListError(null);
      try {
        const result = await getImageTopicList();
        if (result && result.success) {
          const imageTopics = result.image_topic_list || [];
          dispatch(setImageTopicList(imageTopics));
          setTopicListError(null);
          toast.success(`Loaded ${imageTopics.length} image topics`);
          // Preset is always used (with fallback), so no need to auto-assign from list here
        } else {
          const errorMsg = result?.message || 'Unknown error occurred';
          setTopicListError(`Service error: ${errorMsg}`);
          dispatch(setImageTopicList([]));
          toast.error(`Failed to load image topics: ${errorMsg}`);
        }
      } catch (error) {
        setTopicListError('Failed to load image topic list');
        dispatch(setImageTopicList([]));
        toast.error('Failed to load image topic list');
      } finally {
        setIsLoadingTopics(false);
      }
    };

    fetchTopicList();
  }, [getImageTopicList, autoAssignTopics, dispatch, preset]);

  const handlePlusClick = (idx) => {
    setSelectedIdx(idx);
    setModalOpen(true);
  };

  const handleRefreshTopics = async () => {
    setIsLoadingTopics(true);
    setTopicListError(null);
    try {
      const result = await getImageTopicList();
      if (result && result.success) {
        const imageTopics = result.image_topic_list || [];
        dispatch(setImageTopicList(imageTopics));
        setTopicListError(null);
        toast.success(`Refreshed: ${imageTopics.length} image topics`);
      } else {
        const errorMsg = result?.message || 'Unknown error occurred';
        setTopicListError(`Service error: ${errorMsg}`);
        dispatch(setImageTopicList([]));
        toast.error(`Failed to refresh topics: ${errorMsg}`);
      }
    } catch (error) {
      setTopicListError('Failed to load image topic list');
      dispatch(setImageTopicList([]));
      toast.error('Failed to refresh image topics');
    } finally {
      setIsLoadingTopics(false);
    }
  };

  const handleTopicSelect = (topic) => {
    setAsignedImageTopicList(asignedImageTopicList.map((t, i) => (i === selectedIdx ? topic : t)));
    setModalOpen(false);
    setSelectedIdx(null);
  };

  const handleCellClose = (idx) => {
    setAsignedImageTopicList(asignedImageTopicList.map((t, i) => (i === idx ? null : t)));
  };

  const classImageGridArea = clsx(
    'flex', 'flex-row', 'justify-center', 'items-center',
    'gap-[0.5vw]', 'w-full', 'h-full', 'max-w-full', 'max-h-full', 'overflow-hidden'
  );

  const classImageGridCell = (idx) =>
    clsx('min-w-0', 'min-h-0', 'flex', 'items-center', 'justify-center', 'relative', {
      'flex-[7_1_0]': idx === 1,
      'flex-[3_1_0]': idx !== 1,
    });

  const classTopicLabel = clsx(
    'absolute', 'bottom-2', 'left-2', 'text-xs', 'text-white',
    'bg-black', 'bg-opacity-50', 'px-2', 'py-1', 'rounded', 'z-10'
  );

  return (
    <div className="w-full h-full overflow-hidden">
      <div className={classImageGridArea}>
        {layout.map((cell, idx) => (
          <div key={idx} className={classImageGridCell(idx)} data-cell-idx={idx}>
            <ImageGridCell
              topic={asignedImageTopicList[idx]}
              aspect={cell.aspect}
              rotationDegrees={rotationDegrees[idx]}
              onRotateClick={handleRotateClick}
              idx={idx}
              onClose={handleCellClose}
              onPlusClick={handlePlusClick}
              isActive={isActive}
            />
            <div className={classTopicLabel}>{asignedImageTopicList[idx] || ''}</div>
          </div>
        ))}
        {modalOpen && (
          <ImageTopicSelectModal
            topicList={imageTopicList}
            onSelect={handleTopicSelect}
            onClose={() => setModalOpen(false)}
            isLoading={isLoadingTopics}
            onRefresh={handleRefreshTopics}
            errorMessage={topicListError}
          />
        )}
      </div>
    </div>
  );
}
