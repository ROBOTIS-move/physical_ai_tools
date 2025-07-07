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
# Author: Seongwoo Kim

from training.trainers.lerobot.lerobot_trainer import LerobotTrainer
from training.trainers.gr00tn1.gr00tn1_trainer import Gr00tN1Trainer
from training.trainers.openvla.openvla_trainer import OpenVLATrainer

class TrainingManager:
    
    def __init__(self, framework, config, device: str = 'cuda'):
        self.framework = framework
        self.config = config
        self.device = device
        self.trainer = self._get_trainer()
        
    def get_training_metrics(self):
        metrics = self.trainer.send_training_metrics()
        return metrics
        
    def _get_trainer(self):
        if self.framework == "lerobot":
            return LerobotTrainer(self.config)
        elif self.framework == "gr00tn1":
            return Gr00tN1Trainer(self.config)
        elif self.framework == "openvla":
            return OpenVLATrainer(self.config)
        else:
            raise ValueError(f"Unknown framework: {self.framework}")

    def train(self):
        self.trainer.train()
