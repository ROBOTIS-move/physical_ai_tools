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
# Author: Dongyun Kim

from lerobot.lerobot.common.datasets.lerobot_dataset import LeRobotDataset
from lerobot.lerobot.common.robot_devices.control_utils import (
    warmup_record, record_episode, reset_environment, stop_recording,
    init_keyboard_listener, sanity_check_dataset_name, sanity_check_dataset_robot_compatibility
)

class DataSaver(LeRobotDataset):
    def __init__(self, robot, config):
        # Assume config is of type RecordControlConfig
        self.robot = robot
        self.config = config
        # Create or load dataset
        if getattr(config, 'resume', False):
            super().__init__(config.repo_id, root=config.root)
            if hasattr(robot, 'cameras') and len(robot.cameras) > 0:
                self.start_image_writer(
                    num_processes=config.num_image_writer_processes,
                    num_threads=config.num_image_writer_threads_per_camera * len(robot.cameras),
                )
            sanity_check_dataset_robot_compatibility(self, robot, config.fps, config.video)
        else:
            sanity_check_dataset_name(config.repo_id, None)
            ds = LeRobotDataset.create(
                config.repo_id,
                config.fps,
                root=config.root,
                robot=robot,
                use_videos=config.video,
                image_writer_processes=config.num_image_writer_processes,
                image_writer_threads=config.num_image_writer_threads_per_camera * len(robot.cameras),
            )
            # LeRobotDataset.create returns an instance, so copy its internal state
            self.__dict__.update(ds.__dict__)

    def record(self):
        # Prepare keyboard event listener
        listener, events = init_keyboard_listener()
        # Warmup phase
        self._warmup(events)
        if hasattr(self.robot, 'teleop_safety_stop'):
            self.robot.teleop_safety_stop()
        recorded_episodes = 0
        while recorded_episodes < self.config.num_episodes:
            self._record_episode(events)
            # Reset environment if not the last episode
            if not events["stop_recording"] and (
                (recorded_episodes < self.config.num_episodes - 1) or events["rerecord_episode"]
            ):
                self._reset_env(events)
            if events["rerecord_episode"]:
                events["rerecord_episode"] = False
                events["exit_early"] = False
                self.clear_episode_buffer()
                continue
            self.save_episode()
            recorded_episodes += 1
            if events["stop_recording"]:
                break
        # Finalize
        stop_recording(self.robot, listener, self.config.display_data)
        if getattr(self.config, 'push_to_hub', False):
            self.push_to_hub(tags=self.config.tags, private=self.config.private)

    def _warmup(self, events):
        # Only teleoperation is supported in warmup_record (no policy)
        warmup_record(
            self.robot,
            events,
            enable_teleoperation=True,
            warmup_time_s=self.config.warmup_time_s,
            display_data=self.config.display_data,
            fps=self.config.fps,
        )

    def _reset_env(self, events):
        reset_environment(
            self.robot,
            events,
            reset_time_s=self.config.reset_time_s,
            fps=self.config.fps,
        )

    def _record_episode(self, events):
        # Only teleoperation is supported (no policy)
        record_episode(
            robot=self.robot,
            dataset=self,
            events=events,
            episode_time_s=self.config.episode_time_s,
            display_data=self.config.display_data,
            policy=None,
            fps=self.config.fps,
            single_task=self.config.single_task,
        )

    def save_data(self, data: dict):
        self.dataset.save_data(data)
