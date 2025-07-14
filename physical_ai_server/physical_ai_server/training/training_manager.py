#!/usr/bin/env python3
#
# Copyright 2025 ROBOTIS CO., LTD.
#
# Licensed under the Apache License, Version 2.0 (the 'License');
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an 'AS IS' BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Author: Seongwoo Kim

from physical_ai_server.training.trainers.lerobot.lerobot_trainer import LerobotTrainer
from lerobot.configs.train import TrainPipelineConfig
from lerobot.configs.default import DatasetConfig
from lerobot.configs.policies import PreTrainedConfig
# TODO: Uncomment when training metrics is implemented
# from physical_ai_server.training.trainers.gr00tn1.gr00tn1_trainer import Gr00tN1Trainer
# from physical_ai_server.training.trainers.openvla.openvla_trainer import OpenVLATrainer
import draccus

class TrainingManager:
    
    TRAINER_MAPPING = {
        'pi0fast': LerobotTrainer,
        'pi0': LerobotTrainer,
        'diffusion': LerobotTrainer,
        'act': LerobotTrainer,
        'tdmpc': LerobotTrainer,
        'vqbet': LerobotTrainer,
        # TODO: Uncomment when Gr00t and OpenVLA are implemented
        # 'gr00tn1': Gr00tN1Trainer,
        # 'openvla': OpenVLATrainer,
    }
    
    def __init__(self):
        self.training_info = None
        self.trainer = None
        
    def _get_trainer(self):
        policy_type = self.training_info.policy_type.lower()
        trainer_class = self.TRAINER_MAPPING.get(policy_type)

        if not trainer_class:
            raise ValueError(
                f"Unknown policy type: '{policy_type}'."
        )            
        args = [
            f"--policy.type={self.training_info.policy_type}",
            f"--policy.device={self.training_info.policy_device}",
            f"--dataset.repo_id={self.training_info.dataset}",
            f"--output_dir={self.training_info.output_folder_name}",
            f"--resume={'true' if self.training_info.resume else 'false'}",
            f"--seed={self.training_info.seed or 1000}",
            f"--num_workers={self.training_info.num_workers or 4}",
            f"--batch_size={self.training_info.batch_size or 8}",
            f"--steps={self.training_info.steps or 100000}",
            f"--eval_freq={self.training_info.eval_freq or 20000}",
            f"--log_freq={self.training_info.log_freq or 200}",
            f"--save_freq={self.training_info.save_freq or 1000}",
        ]
        cfg = draccus.parse(TrainPipelineConfig, None, args=args)
        return trainer_class(), cfg
    # TODO: Uncomment when training metrics is implemented
    # def get_training_metrics(self):
    #     metrics = self.trainer.send_training_metrics()
    #     return metrics

    def train(self):
        self.trainer, cfg = self._get_trainer()
        self.trainer.train(cfg)
