#!/usr/bin/env python3
#
# Copyright 2025 ROBOTIS CO., LTD.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Author: Claude AI Assistant

"""
MP4 Conversion Worker.

Background process that converts rosbag2 episodes to MP4 format.
Follows the HfApiWorker pattern using multiprocessing.Process.

Output structure:
    /workspace/rosbag2/{robot}_{task}/
    ├── 0/                    # Original episode
    ├── 0_converted/          # Converted result
    │   ├── episode.mcap
    │   ├── cam_*.mp4
    │   ├── robot.urdf
    │   └── meshes/
    ├── 1/
    └── 1_converted/
"""

import logging
import multiprocessing
import os
from pathlib import Path
import queue
import time
from typing import Dict, List, Optional


class Mp4ConversionWorker:
    """
    Background worker for MP4 conversion.

    Uses multiprocessing.Process to run conversion in a separate process,
    following the HfApiWorker pattern.
    """

    def __init__(self):
        self.input_queue = multiprocessing.Queue()
        self.output_queue = multiprocessing.Queue()
        self.progress_queue = multiprocessing.Queue()
        self.process = None
        self.logger = logging.getLogger('Mp4ConversionWorker')

        # Task state management
        self.is_processing = False
        self.current_task = None
        self.start_time = None

        # Progress tracking
        self.current_progress = {
            'current': 0,
            'total': 0,
            'percentage': 0.0,
            'current_episode': '',
            'dataset_path': ''
        }

        # Basic config for the main process logger
        logging.basicConfig(
            level=logging.INFO,
            format='%(name)s - %(levelname)s - %(message)s'
        )

    def start(self) -> bool:
        """Start the worker process."""
        if self.process and self.process.is_alive():
            self.logger.warning('MP4 conversion worker process is already running.')
            return False

        try:
            self.logger.info('Starting MP4 conversion worker process...')

            self.process = multiprocessing.Process(
                target=self._worker_process_loop,
                args=(
                    self.input_queue,
                    self.output_queue,
                    self.progress_queue
                )
            )

            self.process.start()
            self.logger.info(
                f'MP4 conversion worker process started with PID: {self.process.pid}'
            )
            return True

        except Exception as e:
            self.logger.error(f'Failed to start MP4 conversion worker: {str(e)}')
            return False

    def stop(self, timeout: float = 3.0):
        """Stop the worker process."""
        if not self.is_alive():
            self.logger.info(
                'MP4 conversion worker process is not running or already stopped.'
            )
            return

        try:
            self.logger.info('Sending shutdown signal to MP4 conversion worker...')
            try:
                self.input_queue.put_nowait(None)
            except Exception:
                pass

            grace_timeout = min(max(timeout, 0.0), 1.0)
            if grace_timeout > 0:
                self.process.join(grace_timeout)

            if self.process.is_alive():
                self.logger.warning(
                    'MP4 conversion worker did not terminate gracefully. '
                    'Forcing termination now.'
                )
                self.process.kill()
                self.process.join(1.0)
        except Exception as e:
            self.logger.error(f'Error stopping MP4 conversion worker process: {e}')
        finally:
            self.process = None
            self.is_processing = False
            self.current_task = None
            self.start_time = None

    def is_alive(self) -> bool:
        """Check if the worker process is alive."""
        return self.process and self.process.is_alive()

    def send_request(self, request_data: dict) -> bool:
        """
        Send a conversion request to the worker.

        Args:
            request_data: Dict containing:
                - dataset_path: Path to the dataset directory
                - robot_type: Robot type string

        Returns:
            True if request was sent successfully.
        """
        if self.is_alive():
            self.input_queue.put(request_data)
            self.is_processing = True
            self.current_task = request_data
            self.start_time = time.time()
            return True
        else:
            self.logger.error(
                'Cannot send request, MP4 conversion worker process is not running.'
            )
            return False

    def get_result(self, block: bool = False, timeout: float = 0.1) -> Optional[tuple]:
        """Get result from the output queue."""
        try:
            return self.output_queue.get(block=block, timeout=timeout)
        except queue.Empty:
            return None

    def check_task_status(self) -> dict:
        """Check the current task status and return appropriate message."""
        result = {
            'operation': 'convert_mp4',
            'status': 'Idle',
            'dataset_path': '',
            'message': '',
            'progress': {
                'current': 0,
                'total': 0,
                'percentage': 0.0,
            }
        }

        if not self.is_alive():
            self.logger.error('MP4 conversion worker process died')
            result['status'] = 'Failed'
            result['message'] = 'MP4 conversion worker process died'
            return result

        if not self.is_processing:
            result['status'] = 'Idle'
            return result

        try:
            if self.current_task:
                result['dataset_path'] = self.current_task.get('dataset_path', '')

            # Check for progress updates from worker process
            self.current_progress = self._get_progress_from_queue()
            current = self.current_progress.get('current', 0)
            total = self.current_progress.get('total', 0)
            percentage = self.current_progress.get('percentage', 0.0)
            result['progress']['current'] = current
            result['progress']['total'] = total
            result['progress']['percentage'] = percentage

            # Check for task result
            task_result = self.get_result(block=False, timeout=0.1)
            if task_result:
                status, message = task_result
                if status == 'success':
                    log_message = f'MP4 conversion completed successfully:\n{message}'
                    self.logger.info(log_message)
                    self.is_processing = False
                    self.current_task = None

                    result['status'] = 'Success'
                    result['message'] = log_message
                    return result
                elif status == 'error':
                    log_message = f'MP4 conversion failed:\n{message}'
                    self.logger.error(log_message)
                    self.is_processing = False
                    self.current_task = None

                    result['status'] = 'Failed'
                    result['message'] = log_message
                    return result

            # Still processing
            result['status'] = 'Converting'
            current_episode = self.current_progress.get('current_episode', '')
            if current_episode:
                result['message'] = f'Converting episode {current_episode}'

            return result

        except Exception as e:
            log_message = f'Error checking MP4 conversion task status: {str(e)}'
            self.logger.error(log_message)
            result['status'] = 'Failed'
            result['message'] = log_message
            return result

    def is_busy(self) -> bool:
        """Check if the worker is currently processing a task."""
        return self.is_processing

    def _get_progress_from_queue(self) -> dict:
        """Get the latest progress information from worker process."""
        latest_progress = None
        try:
            while True:
                try:
                    latest_progress = self.progress_queue.get(block=False, timeout=0.01)
                except queue.Empty:
                    break
        except Exception as e:
            self.logger.error(f'Error updating progress from worker: {e}')

        return latest_progress if latest_progress else self.current_progress

    @staticmethod
    def _worker_process_loop(input_queue, output_queue, progress_queue):
        """
        Main loop for the worker process.

        Processes conversion requests from the input queue and sends
        results to the output queue.
        """
        logging.basicConfig(
            level=logging.INFO,
            format='[MP4_CONVERSION_WORKER] %(levelname)s: %(message)s'
        )
        logger = logging.getLogger('mp4_conversion_worker')

        try:
            logger.info(f'MP4 conversion worker process started with PID: {os.getpid()}')
            logger.info('Worker is ready and waiting for requests')

            request_count = 0
            last_log_time = time.time()

            while True:
                try:
                    current_time = time.time()
                    if current_time - last_log_time > 30.0:
                        logger.info(
                            f'Worker still alive, processed {request_count} requests so far'
                        )
                        last_log_time = current_time

                    try:
                        data = input_queue.get(timeout=1.0)

                        if data is None:
                            logger.info('Received shutdown signal')
                            break

                        request_count += 1
                        logger.info(f'*** Received MP4 conversion request #{request_count} ***')

                        dataset_path = data.get('dataset_path')
                        robot_type = data.get('robot_type', '')

                        logger.info(f'Processing conversion for: {dataset_path}')

                        # Perform the conversion
                        success, message = Mp4ConversionWorker._convert_dataset(
                            dataset_path=dataset_path,
                            progress_queue=progress_queue,
                            logger=logger
                        )

                        if success:
                            logger.info(f'Conversion completed: {dataset_path}')
                            output_queue.put(('success', message))
                        else:
                            logger.error(f'Conversion failed: {message}')
                            output_queue.put(('error', message))

                    except queue.Empty:
                        continue

                except Exception as e:
                    error_msg = f'MP4 conversion operation error: {str(e)}'
                    logger.error(error_msg)
                    import traceback
                    logger.error(f'Traceback: {traceback.format_exc()}')
                    output_queue.put(('error', error_msg))

        except Exception as e:
            error_msg = f'MP4 conversion worker initialization error: {str(e)}'
            logger.error(error_msg)
            import traceback
            logger.error(f'Traceback: {traceback.format_exc()}')
            output_queue.put(('error', error_msg))

        logger.info('MP4 conversion worker process shutting down')

    @staticmethod
    def _convert_dataset(
        dataset_path: str,
        progress_queue: multiprocessing.Queue,
        logger: logging.Logger
    ) -> tuple:
        """
        Convert all episodes in a dataset to MP4 format.

        Args:
            dataset_path: Path to the dataset directory.
            progress_queue: Queue for progress updates.
            logger: Logger instance.

        Returns:
            Tuple of (success: bool, message: str).
        """
        try:
            from physical_ai_server.data_processing.convert_rosbag2mp4 import (
                ScaleAIConverter
            )
        except ImportError as e:
            return False, f'Failed to import converter: {str(e)}'

        try:
            dataset_path = Path(dataset_path)
            if not dataset_path.exists():
                return False, f'Dataset path does not exist: {dataset_path}'

            # Find all episode directories (numeric folders)
            episode_dirs = sorted([
                d for d in dataset_path.iterdir()
                if d.is_dir() and d.name.isdigit()
            ])

            if not episode_dirs:
                return False, f'No episode directories found in {dataset_path}'

            total_episodes = len(episode_dirs)
            logger.info(f'Found {total_episodes} episodes to convert')

            # Initialize converter
            converter = ScaleAIConverter(
                fps=15,
                use_hardware_encoding=True,
                enable_timestamp_smoothing=True
            )

            converted_count = 0
            failed_episodes = []

            for idx, episode_dir in enumerate(episode_dirs):
                episode_id = episode_dir.name
                output_dir = dataset_path / f'{episode_id}_converted'

                # Update progress
                progress_data = {
                    'current': idx,
                    'total': total_episodes,
                    'percentage': (idx / total_episodes) * 100,
                    'current_episode': episode_id,
                    'dataset_path': str(dataset_path)
                }
                progress_queue.put(progress_data)

                logger.info(f'Converting episode {episode_id} ({idx + 1}/{total_episodes})')

                try:
                    results = converter.convert_episode(
                        str(episode_dir),
                        str(output_dir)
                    )

                    # Check if any camera conversion succeeded
                    success = any(
                        result.success for result in results.values()
                        if hasattr(result, 'success')
                    )

                    if success:
                        converted_count += 1
                        logger.info(f'Episode {episode_id} converted successfully')
                    else:
                        failed_episodes.append(episode_id)
                        logger.warning(f'Episode {episode_id} conversion had issues')

                except Exception as e:
                    failed_episodes.append(episode_id)
                    logger.error(f'Error converting episode {episode_id}: {str(e)}')

            # Final progress update
            progress_data = {
                'current': total_episodes,
                'total': total_episodes,
                'percentage': 100.0,
                'current_episode': '',
                'dataset_path': str(dataset_path)
            }
            progress_queue.put(progress_data)

            # Build result message
            if converted_count == total_episodes:
                return True, (
                    f'Successfully converted all {total_episodes} episodes '
                    f'in {dataset_path}'
                )
            elif converted_count > 0:
                return True, (
                    f'Converted {converted_count}/{total_episodes} episodes. '
                    f'Failed episodes: {", ".join(failed_episodes)}'
                )
            else:
                return False, (
                    f'Failed to convert any episodes. '
                    f'Failed episodes: {", ".join(failed_episodes)}'
                )

        except Exception as e:
            import traceback
            logger.error(f'Conversion error: {traceback.format_exc()}')
            return False, f'Conversion error: {str(e)}'
