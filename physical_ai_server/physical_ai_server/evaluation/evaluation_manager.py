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

import os
import torch
import cv2
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional

from lerobot.common.datasets.lerobot_dataset import LeRobotDataset
from lerobot.configs.default import DatasetConfig
from inference_manager import InferenceManager


class VisualizationManager:

    def __init__(self, default_save_dir: str = "/root/.cache"):
        self.default_save_dir = default_save_dir
        os.makedirs(self.default_save_dir, exist_ok=True)

    def plot_action_comparison(
        self,
        episode_idx: int,
        state_across_time: np.ndarray,
        gt_action_across_time: np.ndarray,
        pred_action_across_time: np.ndarray,
        save_path: str = None,
        mse: float = None
    ) -> None:

        action_dim = gt_action_across_time.shape[1]

        fig, axes = plt.subplots(nrows=action_dim, ncols=1, figsize=(12, 3 * action_dim))
        if action_dim == 1:
            axes = [axes]

        # Add global title with MSE information
        title = f"Episode {episode_idx} - Action Prediction Evaluation"
        if mse is not None:
            title += f" (MSE: {mse:.6f})"
        fig.suptitle(title, fontsize=14, color="blue")

        # Plot each action dimension
        for i, ax in enumerate(axes):
            self._plot_single_action_dimension(
                ax,
                i,
                state_across_time,
                gt_action_across_time,
                pred_action_across_time
            )

        plt.tight_layout()

        # Save plot if path is provided
        if save_path:
            self._save_plot(save_path)
        else:
            # Auto-generate path if not provided
            auto_path = os.path.join(self.default_save_dir, f"episode_{episode_idx}_action_comparison.png")
            self._save_plot(auto_path)
    
    def _plot_single_action_dimension(
        self,
        ax: plt.Axes,
        dim_idx: int,
        state_across_time: np.ndarray,
        gt_action_across_time: np.ndarray,
        pred_action_across_time: np.ndarray
    ) -> None:

        if state_across_time.shape[1] == gt_action_across_time.shape[1]:
            ax.plot(
                state_across_time[:, dim_idx], label="Current State", alpha=0.7, linestyle='--')

        # Plot ground truth and predicted actions
        ax.plot(
            gt_action_across_time[:, dim_idx],
            label="Ground Truth Action",
            color='green',
            linewidth=2)
        ax.plot(
            pred_action_across_time[:, dim_idx],
            label="Predicted Action",
            color='red',
            linewidth=2)

        # Configure plot appearance
        ax.set_title(f"Action Dimension {dim_idx}")
        ax.set_xlabel("Time Step")
        ax.set_ylabel("Action Value")
        ax.legend()
        ax.grid(True, alpha=0.3)

    def _save_plot(self, save_path: str) -> None:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to: {save_path}")

    def plot_episode_mse_comparison(
        self,
        episode_mses: List[float],
        save_path: str = None,
        title: str = "Episode MSE Comparison"
    ) -> None:
        """
        Create a bar plot showing MSE values across all episodes.
        
        Args:
            episode_mses (List[float]): List of MSE values for each episode
            save_path (str, optional): Path to save the plot
            title (str): Title for the plot
        """
        if not episode_mses:
            print("No episode MSE data to plot")
            return
        
        # Create figure and axis
        fig, ax = plt.subplots(figsize=(max(12, len(episode_mses) * 0.8), 6))
        
        # Episode indices
        episode_indices = list(range(len(episode_mses)))
        
        # Create bar plot
        bars = ax.bar(episode_indices, episode_mses, alpha=0.7, color='skyblue', edgecolor='navy')
        
        # Highlight the episode with highest MSE
        if episode_mses:
            max_mse_idx = np.argmax(episode_mses)
            bars[max_mse_idx].set_color('red')
            bars[max_mse_idx].set_alpha(0.8)
        
        # Highlight the episode with lowest MSE
        if episode_mses:
            min_mse_idx = np.argmin(episode_mses)
            bars[min_mse_idx].set_color('green')
            bars[min_mse_idx].set_alpha(0.8)
        
        # Configure plot appearance
        ax.set_xlabel("Episode Index")
        ax.set_ylabel("MSE Value")
        ax.set_title(title)
        ax.grid(True, alpha=0.3, axis='y')
        
        # Add value labels on bars
        for i, mse in enumerate(episode_mses):
            ax.text(i, mse + max(episode_mses) * 0.01, f'{mse:.4f}', 
                   ha='center', va='bottom', fontsize=8, rotation=45)
        
        # Add statistics text
        if episode_mses:
            stats_text = f"Mean: {np.mean(episode_mses):.4f}\n"
            stats_text += f"Std: {np.std(episode_mses):.4f}\n"
            stats_text += f"Min: {np.min(episode_mses):.4f} (Episode {np.argmin(episode_mses)})\n"
            stats_text += f"Max: {np.max(episode_mses):.4f} (Episode {np.argmax(episode_mses)})"
            
            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, 
                   verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        # Create legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='skyblue', alpha=0.7, label='Episode MSE'),
            Patch(facecolor='green', alpha=0.8, label='Best Episode (Lowest MSE)'),
            Patch(facecolor='red', alpha=0.8, label='Worst Episode (Highest MSE)')
        ]
        ax.legend(handles=legend_elements, loc='upper right')
        
        plt.tight_layout()
        
        # Save plot if path is provided
        if save_path:
            self._save_plot(save_path)
        else:
            # Auto-generate path if not provided
            auto_path = os.path.join(self.default_save_dir, "episode_mse_comparison.png")
            self._save_plot(auto_path)
    
    def plot_episode_mse_distribution(
        self,
        episode_mses: List[float],
        save_path: str = None,
        bins: int = 10
    ) -> None:
        """
        Create a histogram showing the distribution of MSE values across episodes.
        
        Args:
            episode_mses (List[float]): List of MSE values for each episode
            save_path (str, optional): Path to save the plot
            bins (int): Number of bins for the histogram
        """
        if not episode_mses:
            print("No episode MSE data to plot")
            return
        
        # Create figure and axis
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Create histogram
        n, bins_edges, patches = ax.hist(episode_mses, bins=bins, alpha=0.7, color='lightblue', edgecolor='black')
        
        # Add vertical lines for mean and median
        mean_mse = np.mean(episode_mses)
        median_mse = np.median(episode_mses)
        
        ax.axvline(mean_mse, color='red', linestyle='--', linewidth=2, label=f'Mean: {mean_mse:.4f}')
        ax.axvline(median_mse, color='green', linestyle='--', linewidth=2, label=f'Median: {median_mse:.4f}')
        
        # Configure plot appearance
        ax.set_xlabel("MSE Value")
        ax.set_ylabel("Frequency")
        ax.set_title("Distribution of MSE Values Across Episodes")
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Add statistics text
        stats_text = f"Episodes: {len(episode_mses)}\n"
        stats_text += f"Mean: {mean_mse:.4f}\n"
        stats_text += f"Std: {np.std(episode_mses):.4f}\n"
        stats_text += f"Min: {np.min(episode_mses):.4f}\n"
        stats_text += f"Max: {np.max(episode_mses):.4f}"
        
        ax.text(0.98, 0.98, stats_text, transform=ax.transAxes, 
               verticalalignment='top', horizontalalignment='right',
               bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        plt.tight_layout()
        
        # Save plot if path is provided
        if save_path:
            self._save_plot(save_path)
        else:
            # Auto-generate path if not provided
            auto_path = os.path.join(self.default_save_dir, "episode_mse_distribution.png")
            self._save_plot(auto_path)


class EvaluationManager:

    def __init__(self):
        self.visualization_manager = VisualizationManager()

    def load_dataset(
        self,
        repo_id: str,
        root: str = None,
        episodes: List[int] = None
    ) -> LeRobotDataset:
        dataset_config = DatasetConfig(
            repo_id=repo_id,
            root=root,
            episodes=episodes,
        )

        dataset = LeRobotDataset(
            repo_id=dataset_config.repo_id,
            root=dataset_config.root,
            episodes=dataset_config.episodes,
            delta_timestamps=None,
            image_transforms=None,
            revision=dataset_config.revision,
            video_backend=dataset_config.video_backend,
        )
        return dataset

    def get_episode_boundaries(
        self,
        dataset: LeRobotDataset,
        episode_idx: int
    ) -> Tuple[int, int, int]:
        if episode_idx >= dataset.num_episodes:
            raise ValueError(
                f"Episode index {episode_idx} exceeds available episodes {dataset.num_episodes}")

        episode_start = int(dataset.episode_data_index["from"][episode_idx])
        episode_end = int(dataset.episode_data_index["to"][episode_idx])
        episode_length = episode_end - episode_start

        return episode_start, episode_end, episode_length
    
    def get_episode_data(
        self,
        dataset: LeRobotDataset,
        episode_idx: int
    ) -> List[Dict]:
        episode_start, episode_end, _ = self.get_episode_boundaries(dataset, episode_idx)
        
        episode_frames = []
        for frame_idx in range(episode_start, episode_end):
            frame_data = dataset[frame_idx]
            episode_frames.append(frame_data)
        
        return episode_frames
    
    def extract_frame_components(
        self,
        frame_data: Dict
    ) -> Tuple[np.ndarray, np.ndarray, Dict[str, np.ndarray], str]:
        # Extract ground truth state and action
        gt_state = frame_data['observation.state'].numpy()
        gt_action = frame_data['action'].numpy()
        
        # Prepare observation data for inference
        images = {}
        for key, value in frame_data.items():
            if key.startswith('observation.images.'):
                # Convert tensor back to numpy array in expected format [H, W, C]
                img_tensor = value  # Shape: [C, H, W]
                img_np = img_tensor.permute(1, 2, 0).numpy()
                img_np = img_np.astype(np.float32)
                img_np = img_np * 255.0
                camera_name = key.replace('observation.images.', '')
                images[camera_name] = img_np

        task_instruction = frame_data.get('task')
        
        return gt_state, gt_action, images, task_instruction
    
    def calculate_mse(
        self,
        gt_actions: np.ndarray,
        pred_actions: np.ndarray
    ) -> float:
        return np.mean((gt_actions - pred_actions) ** 2)
    
    def evaluate_policy_on_episode(
        self,
        inference_manager: InferenceManager,
        dataset: LeRobotDataset,
        episode_idx: int,
        plot: bool = False,
        save_plot_path: str = None
    ) -> float:
        episode_start, episode_end, episode_length = self.get_episode_boundaries(dataset, episode_idx)

        # Storage for trajectory data
        state_across_time = []
        gt_action_across_time = []
        pred_action_across_time = []

        # Process each frame in the episode
        for step_count in range(episode_length):
            frame_idx = episode_start + step_count
            frame_data = dataset[frame_idx]

            # Extract frame components
            gt_state, gt_action, images, task_instruction = self.extract_frame_components(frame_data)

            # Store ground truth data
            state_across_time.append(gt_state)
            gt_action_across_time.append(gt_action)

            # Get policy prediction
            predicted_action = inference_manager.predict(
                images=images,
                state=gt_state.tolist(),
                task_instruction=task_instruction
            )
            pred_action_across_time.append(predicted_action)

        # Convert to numpy arrays
        state_across_time = np.array(state_across_time)
        gt_action_across_time = np.array(gt_action_across_time)
        pred_action_across_time = np.array(pred_action_across_time)

        # Calculate evaluation metrics
        mse = self.calculate_mse(gt_action_across_time, pred_action_across_time)

        # Create visualization if requested
        if plot:
            self.visualization_manager.plot_action_comparison(
                episode_idx=episode_idx,
                state_across_time=state_across_time,
                gt_action_across_time=gt_action_across_time,
                pred_action_across_time=pred_action_across_time,
                save_path=save_plot_path,
                mse=mse
            )

        return mse

    def evaluate_policy_on_dataset(
        self,
        inference_manager: InferenceManager,
        dataset: LeRobotDataset,
        sample_episodes: List[int] = None,
        plot_episodes: bool = False,
        plot_summary: bool = True,
        save_plot_dir: str = None
    ) -> Dict[str, float]:
        """
        Evaluate a policy on all episodes in a dataset.
        
        Args:
            inference_manager (InferenceManager): Manager for policy inference
            dataset (LeRobotDataset): Dataset to evaluate on
            plot_episodes (bool): Whether to create plots for individual episodes
            plot_summary (bool): Whether to create summary plots (MSE comparison and distribution)
            save_plot_dir (str, optional): Directory to save plots
            
        Returns:
            Dict[str, float]: Dictionary containing evaluation metrics and episode MSEs
        """
        episode_mses = []
        total_episodes = dataset.num_episodes
        if sample_episodes is None:
            sample_episodes = list(range(total_episodes))

        for episode_idx in sample_episodes:
            try:
                # Determine save path for this episode
                episode_save_path = None
                if plot_episodes and save_plot_dir:
                    episode_save_path = os.path.join(save_plot_dir, f"episode_{episode_idx}_evaluation.png")

                # Evaluate episode
                mse = self.evaluate_policy_on_episode(
                    inference_manager=inference_manager,
                    dataset=dataset,
                    episode_idx=episode_idx,
                    plot=plot_episodes,
                    save_plot_path=episode_save_path
                )

                episode_mses.append(mse)
                print(f"Episode {episode_idx}: MSE = {mse:.6f}")

            except Exception as e:
                print(f"Failed to evaluate episode {episode_idx}: {e}")
                continue

        # Calculate aggregate metrics
        if episode_mses:
            results = {
                'mean_mse': np.mean(episode_mses),
                'std_mse': np.std(episode_mses),
                'min_mse': np.min(episode_mses),
                'max_mse': np.max(episode_mses),
                'best_episode_idx': np.argmin(episode_mses),
                'worst_episode_idx': np.argmax(episode_mses),
                'total_episodes': len(episode_mses),
                'episode_mses': episode_mses
            }
        else:
            results = {
                'mean_mse': float('inf'),
                'std_mse': 0.0,
                'min_mse': float('inf'),
                'max_mse': float('inf'),
                'best_episode_idx': -1,
                'worst_episode_idx': -1,
                'total_episodes': 0,
                'episode_mses': []
            }

        # Plot MSE comparison across episodes
        if plot_summary and episode_mses:
            mse_comparison_path = None
            mse_distribution_path = None
            
            if save_plot_dir:
                mse_comparison_path = os.path.join(save_plot_dir, "overall_mse_comparison.png")
                mse_distribution_path = os.path.join(save_plot_dir, "overall_mse_distribution.png")
            
            self.visualization_manager.plot_episode_mse_comparison(
                episode_mses=episode_mses,
                save_path=mse_comparison_path,
                title="Overall Episode MSE Comparison"
            )

            # Plot MSE distribution
            self.visualization_manager.plot_episode_mse_distribution(
                episode_mses=episode_mses,
                save_path=mse_distribution_path,
                bins=20
            )

        return results


def main():
    """
    Main function demonstrating the usage of EvaluationManager and VisualizationManager.
    """
    # Initialize managers
    evaluation_manager = EvaluationManager()
    
    # Configuration
    repo_id = "ROBOTIS/omy_f3m_Stack_cup"
    policy_path = '/root/.cache/huggingface/hub/models--ROBOTIS--omy_stack_cup_60k/snapshots/9744b906b355d6c82bfb39da5e34cc8866f47ad6'
    
    # Load dataset
    dataset = evaluation_manager.load_dataset(repo_id)
    
    # Initialize inference manager
    inference_manager = InferenceManager()
    success, message = inference_manager.validate_policy(policy_path)
    
    if success:
        policy_loaded = inference_manager.load_policy()
        if policy_loaded:
            # Evaluate policy on entire dataset
            results = evaluation_manager.evaluate_policy_on_dataset(
                inference_manager=inference_manager,
                dataset=dataset,
                sample_episodes=[1, 3, 5],
                plot_episodes=True,
                plot_summary=True,
                save_plot_dir="./plots"
            )
            
            print(f"\nEvaluation Results:")
            print(f"Mean MSE: {results['mean_mse']:.6f}")
            print(f"Std MSE: {results['std_mse']:.6f}")
            print(f"Min MSE: {results['min_mse']:.6f} (Episode {results['best_episode_idx']})")
            print(f"Max MSE: {results['max_mse']:.6f} (Episode {results['worst_episode_idx']})")
            print(f"Total Episodes: {results['total_episodes']}")
            print(f"\nBest performing episode: {results['best_episode_idx']}")
            print(f"Worst performing episode: {results['worst_episode_idx']}")
            
            # Display episode MSE summary
            if results['episode_mses']:
                print(f"\nEpisode MSE Summary:")
                for i, mse in enumerate(results['episode_mses']):
                    status = ""
                    if i == results['best_episode_idx']:
                        status = " (BEST)"
                    elif i == results['worst_episode_idx']:
                        status = " (WORST)"
                    print(f"  Episode {i}: {mse:.6f}{status}")
            
        else:
            print("Failed to load policy")
    else:
        print(f"Policy validation failed: {message}")
    
    print("\nDataset evaluation completed!")


if __name__ == "__main__":
    main()
