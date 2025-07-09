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

from lerobot.common.datasets.lerobot_dataset import LeRobotDataset
from lerobot.configs.default import DatasetConfig
from inference_manager import InferenceManager


def load_dataset(
        repo_id: str,
        root: str = None,
        episodes: list[int] = None) -> LeRobotDataset:

    dataset_config = DatasetConfig(
        repo_id=repo_id,
        root=root,
        episodes=episodes,
    )

    dataset = LeRobotDataset(
        repo_id=dataset_config.repo_id,
        root=dataset_config.root,
        episodes=dataset_config.episodes,
        delta_timestamps=None,  # Skip temporal offset configuration
        image_transforms=None,  # Skip image transformations
        revision=dataset_config.revision,
        video_backend=dataset_config.video_backend,
    )
    return dataset

def get_episode_data(dataset: LeRobotDataset, episode_idx: int):
    """
    Extract all data from a specific episode in the dataset.
    This function returns all frames belonging to the specified episode
    along with their temporal sequence information.
    
    Args:
        dataset (LeRobotDataset): The loaded LeRobot dataset instance
        episode_idx (int): Index of the episode to extract (0-based)
        
    Returns:
        list: List of dictionaries containing frame data for the episode
    """
    if episode_idx >= dataset.num_episodes:
        raise ValueError(f"Episode index {episode_idx} exceeds available episodes {dataset.num_episodes}")
    
    # Get start and end indices for the specified episode
    episode_start = int(dataset.episode_data_index["from"][episode_idx])
    episode_end = int(dataset.episode_data_index["to"][episode_idx])
    episode_length = episode_end - episode_start
    
    print(f"Extracting episode {episode_idx}: frames {episode_start} to {episode_end-1} (length: {episode_length})")
    
    # Extract all frames from this episode
    episode_frames = []
    for frame_idx in range(episode_start, episode_end):
        frame_data = dataset[frame_idx]
        episode_frames.append(frame_data)
    
    return episode_frames


def analyze_episode_trajectories(dataset: LeRobotDataset, episode_idx: int):
    """
    Analyze the trajectory data (actions and observations) for a specific episode.
    This function provides statistical analysis of the episode's action and state
    sequences to understand the behavior patterns.
    
    Args:
        dataset (LeRobotDataset): The loaded LeRobot dataset instance
        episode_idx (int): Index of the episode to analyze (0-based)
    """
    episode_frames = get_episode_data(dataset, episode_idx)
    
    print(f"\n=== Trajectory Analysis for Episode {episode_idx} ===")
    
    # Extract action sequence if available
    if 'action' in episode_frames[0]:
        actions = torch.stack([frame['action'] for frame in episode_frames])
        print(f"Action sequence shape: {actions.shape}")
        print(f"Action range: min={actions.min().item():.3f}, max={actions.max().item():.3f}")
        print(f"Action mean: {actions.mean(dim=0).numpy()}")
        print(f"Action std: {actions.std(dim=0).numpy()}")
    
    # Extract state sequence if available
    if 'observation.state' in episode_frames[0]:
        states = torch.stack([frame['observation.state'] for frame in episode_frames])
        print(f"State sequence shape: {states.shape}")
        print(f"State range: min={states.min().item():.3f}, max={states.max().item():.3f}")
        print(f"State mean: {states.mean(dim=0).numpy()}")
        print(f"State std: {states.std(dim=0).numpy()}")
    
    # Check for image data
    image_keys = [key for key in episode_frames[0].keys() if key.startswith('observation.images')]
    if image_keys:
        print(f"Available image streams: {image_keys}")
        for img_key in image_keys:
            img_shape = episode_frames[0][img_key].shape
            print(f"  {img_key}: shape={img_shape}")


def save_episode_images(dataset: LeRobotDataset, episode_idx: int, output_dir: str = "./saved_images", max_frames: int = 10):
    """
    Save sample images from a specific episode to verify image data integrity.
    This function extracts and saves images from different camera streams to
    validate that the dataset contains properly loaded visual data.
    
    Args:
        dataset (LeRobotDataset): The loaded LeRobot dataset instance
        episode_idx (int): Index of the episode to extract images from (0-based)
        output_dir (str): Directory path where images will be saved
        max_frames (int): Maximum number of frames to save from the episode
    """
    if episode_idx >= dataset.num_episodes:
        raise ValueError(f"Episode index {episode_idx} exceeds available episodes {dataset.num_episodes}")
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Get episode boundaries
    episode_start = int(dataset.episode_data_index["from"][episode_idx])
    episode_end = int(dataset.episode_data_index["to"][episode_idx])
    episode_length = episode_end - episode_start
    
    print(f"Saving images from episode {episode_idx} (length: {episode_length} frames)")
    
    # Select frame indices to save (evenly distributed across the episode)
    frame_indices = []
    if episode_length <= max_frames:
        frame_indices = list(range(episode_start, episode_end))
    else:
        step = episode_length // max_frames
        frame_indices = [episode_start + i * step for i in range(max_frames)]
    
    # Get image keys from the first frame
    first_frame = dataset[episode_start]
    image_keys = [key for key in first_frame.keys() if key.startswith('observation.images')]
    
    print(f"Found image streams: {image_keys}")
    print(f"Saving {len(frame_indices)} frames to {output_dir}")
    
    # Save images for each selected frame
    for i, frame_idx in enumerate(frame_indices):
        frame_data = dataset[frame_idx]
        relative_frame = frame_idx - episode_start
        
        # Save each image stream
        for img_key in image_keys:
            if img_key in frame_data:
                # Convert tensor to numpy array for OpenCV
                img_tensor = frame_data[img_key]  # Shape: [C, H, W]
                
                # Handle different image formats (RGB vs Depth)
                if 'depth' in img_key.lower():
                    # For depth images, use single channel
                    if img_tensor.shape[0] == 3:
                        # Take first channel if depth is stored as 3-channel
                        img_np = img_tensor[0].numpy()
                    else:
                        img_np = img_tensor.squeeze().numpy()
                    
                    # Normalize depth values to 0-255 range for visualization
                    img_np = cv2.normalize(img_np, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
                    
                else:
                    # For RGB images, convert from [C, H, W] to [H, W, C]
                    img_np = img_tensor.permute(1, 2, 0).numpy()
                    
                    # Convert from [0, 1] range to [0, 255] range
                    img_np = (img_np * 255).astype(np.uint8)
                    
                    # Convert RGB to BGR for OpenCV
                    img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
                
                # Create filename
                camera_name = img_key.replace('observation.images.', '')
                filename = f"episode_{episode_idx:03d}_frame_{relative_frame:03d}_{camera_name}.jpg"
                filepath = os.path.join(output_dir, filename)
                
                # Save image
                success = cv2.imwrite(filepath, img_np)
                if success:
                    print(f"  Saved: {filename} (shape: {img_np.shape})")
                else:
                    print(f"  Failed to save: {filename}")


def visualize_episode_data(dataset: LeRobotDataset, episode_idx: int, save_images: bool = True):
    """
    Comprehensive visualization of episode data including images, actions, and states.
    This function provides a complete overview of an episode's content for analysis
    and debugging purposes.
    
    Args:
        dataset (LeRobotDataset): The loaded LeRobot dataset instance
        episode_idx (int): Index of the episode to visualize (0-based)
        save_images (bool): Whether to save sample images from the episode
    """
    print(f"\n{'='*60}")
    print(f"COMPREHENSIVE EPISODE {episode_idx} VISUALIZATION")
    print(f"{'='*60}")
    
    # Get episode data
    episode_frames = get_episode_data(dataset, episode_idx)
    episode_length = len(episode_frames)
    
    # Display basic episode information
    first_frame = episode_frames[0]
    last_frame = episode_frames[-1]
    
    print(f"Episode Length: {episode_length} frames")
    if 'task' in first_frame:
        print(f"Task: {first_frame['task']}")
    
    # Display data structure
    print(f"\nData Structure:")
    for key, value in first_frame.items():
        if isinstance(value, torch.Tensor):
            print(f"  {key}: {value.shape} ({value.dtype})")
        else:
            print(f"  {key}: {type(value).__name__}")
    
    # Display action and state statistics
    if 'action' in first_frame and 'observation.state' in first_frame:
        actions = torch.stack([frame['action'] for frame in episode_frames])
        states = torch.stack([frame['observation.state'] for frame in episode_frames])
        
        print(f"\nAction Statistics:")
        print(f"  Shape: {actions.shape}")
        print(f"  Range: [{actions.min().item():.3f}, {actions.max().item():.3f}]")
        print(f"  Mean: {actions.mean(dim=0).numpy()}")
        
        print(f"\nState Statistics:")
        print(f"  Shape: {states.shape}")
        print(f"  Range: [{states.min().item():.3f}, {states.max().item():.3f}]")
        print(f"  Mean: {states.mean(dim=0).numpy()}")
    
    # Save sample images if requested
    if save_images:
        print(f"\nSaving sample images...")
        save_episode_images(dataset, episode_idx, f"./episode_{episode_idx}_images", max_frames=5)
    
    print(f"\nVisualization completed for episode {episode_idx}")


def evaluate_policy_on_episode(
    policy_manager: InferenceManager,
    dataset: LeRobotDataset,
    episode_idx: int,
    max_steps: int = None,
    action_horizon: int = 16,
    plot: bool = False,
    save_plot_path: str = None
):
    """
    Evaluate policy performance on a single episode by running sequential inference.
    This function iterates through frames in an episode, performs inference at regular
    intervals, and compares predicted actions with ground truth actions.
    
    Args:
        policy_manager (InferenceManager): Loaded policy manager with inference capability
        dataset (LeRobotDataset): The loaded LeRobot dataset instance
        episode_idx (int): Index of the episode to evaluate (0-based)
        max_steps (int, optional): Maximum number of steps to evaluate. If None, evaluates entire episode
        action_horizon (int): Number of action predictions per inference call
        plot (bool): Whether to plot the comparison results
        save_plot_path (str, optional): Path to save the plot. If None, plot is not saved.
        
    Returns:
        float: Mean squared error between predicted and ground truth actions
    """
    if episode_idx >= dataset.num_episodes:
        raise ValueError(f"Episode index {episode_idx} exceeds available episodes {dataset.num_episodes}")

    # Get episode boundaries
    episode_start = int(dataset.episode_data_index["from"][episode_idx])
    episode_end = int(dataset.episode_data_index["to"][episode_idx])
    episode_length = episode_end - episode_start

    # Use entire episode length if max_steps is None, otherwise limit steps
    if max_steps is None:
        steps = episode_length
    else:
        steps = min(max_steps, episode_length)

    print(f"Evaluating policy on episode {episode_idx} (length: {episode_length}, evaluating: {steps} steps)")

    # Storage for trajectory data
    state_across_time = []
    gt_action_across_time = []
    pred_action_across_time = []

    # Action chunk buffer for multi-step predictions
    action_chunk_buffer = []
    action_chunk_index = 0

    for step_count in range(steps):
        # Show progress for long episodes
        if steps > 100 and step_count % (steps // 10) == 0:
            progress = (step_count / steps) * 100
            print(f"  Progress: {progress:.1f}% ({step_count}/{steps})")

        frame_idx = episode_start + step_count
        frame_data = dataset[frame_idx]

        # Extract ground truth state and action
        gt_state = frame_data['observation.state'].numpy()
        gt_action = frame_data['action'].numpy()

        state_across_time.append(gt_state)
        gt_action_across_time.append(gt_action)
        

        progress = (step_count / steps) * 100
        print(f"  Performing inference at step: {step_count}/{steps} ({progress:.1f}%)")
        
        # Prepare observation data for inference
        images = {}
        for key, value in frame_data.items():
            if key.startswith('observation.images.'):
                # Convert tensor back to numpy array in expected format [H, W, C]
                img_tensor = value  # Shape: [C, H, W]
                img_np = img_tensor.permute(1, 2, 0).numpy()
                # Keep in 0-1 range as expected by InferenceManager (it will convert to 0-255 internally)
                img_np = img_np.astype(np.float32)
                img_np = img_np * 255.0
                # Remove the 'observation.images.' prefix for the key since InferenceManager adds it back
                camera_name = key.replace('observation.images.', '')
                images[camera_name] = img_np
        
        # Get task instruction from frame data
        task_instruction = frame_data.get('task', "Pick up the yellow cup.")
        
        # Debug: Print input data info for first few steps
        if step_count == 0:
            print(f"    Input images: {list(images.keys())}")
            for img_key, img_data in images.items():
                print(f"    Image {img_key}: shape={img_data.shape}, range=[{img_data.min():.3f}, {img_data.max():.3f}]")
            print(f"    State shape: {gt_state.shape}, State values: {gt_state[:3]}...")
            print(f"    Task: {task_instruction}")
        
        # # Get task instruction if available
        # task_instruction = frame_data.get('task', None)
        
        # Run inference
        try:
            predicted_action = policy_manager.predict(
                images=images,
                state=gt_state.tolist(),
                task_instruction=task_instruction
            )
            
            # Debug: Check prediction type and convert if necessary
            if step_count == 0:
                print(f"    Prediction type: {type(predicted_action)}")
                print(f"    Prediction shape/len: {getattr(predicted_action, 'shape', len(predicted_action) if hasattr(predicted_action, '__len__') else 'scalar')}")
                print(f"    Raw prediction: {predicted_action}")
            
            # Ensure predicted_action is a numpy array
            if hasattr(predicted_action, 'numpy'):
                predicted_action = predicted_action.numpy()
            elif not isinstance(predicted_action, np.ndarray):
                predicted_action = np.array(predicted_action)
            
            # Debug: Print first few predictions to check if they're reasonable
            if step_count < 64:  # Only print for first few inferences
                print(f"    GT action: {gt_action[:3]}...")
                print(f"    Predicted: {predicted_action[:3]}...")
                
            # Check if prediction is always the same (indicating a problem)
            if step_count > 16 and len(action_chunk_buffer) > 0:
                if np.allclose(predicted_action, action_chunk_buffer[0], atol=1e-6):
                    print(f"    WARNING: Prediction seems identical to previous prediction!")
                    print(f"    This may indicate the policy is not responding to changing inputs.")
            
            # Store action chunk for multi-step prediction
            # Assuming the policy returns a single action, we'll replicate it for action_horizon
            action_chunk_buffer = [predicted_action] * action_horizon
            action_chunk_index = 0
            
        except Exception as e:
            print(f"    Inference failed at step {step_count}: {e}")
            print(f"    Using ground truth action as fallback")
            # Use ground truth action as fallback
            predicted_action = gt_action
            action_chunk_buffer = [predicted_action] * action_horizon
            action_chunk_index = 0
        
        # Get prediction from buffer
        if action_chunk_index < len(action_chunk_buffer):
            current_prediction = action_chunk_buffer[action_chunk_index]
            action_chunk_index += 1
        else:
            # Fallback to last prediction
            current_prediction = action_chunk_buffer[-1] if action_chunk_buffer else gt_action
        
        pred_action_across_time.append(predicted_action)
    
    # Convert to numpy arrays for analysis
    state_across_time = np.array(state_across_time)
    gt_action_across_time = np.array(gt_action_across_time)
    pred_action_across_time = np.array(pred_action_across_time)
    
    # Ensure arrays have same shape
    min_length = min(len(gt_action_across_time), len(pred_action_across_time))
    gt_action_across_time = gt_action_across_time[:min_length]
    pred_action_across_time = pred_action_across_time[:min_length]
    
    # Calculate MSE
    mse = np.mean((gt_action_across_time - pred_action_across_time) ** 2)
    
    # Calculate additional metrics
    mae = np.mean(np.abs(gt_action_across_time - pred_action_across_time))
    max_error = np.max(np.abs(gt_action_across_time - pred_action_across_time))
    
    print(f"\n=== Episode {episode_idx} Evaluation Results ===")
    print(f"Evaluated {min_length}/{episode_length} frames ({(min_length/episode_length)*100:.1f}%)")
    print(f"Action MSE: {mse:.6f}")
    print(f"Action MAE: {mae:.6f}")
    print(f"Max absolute error: {max_error:.6f}")
    print(f"State shape: {state_across_time.shape}")
    print(f"GT action shape: {gt_action_across_time.shape}")
    print(f"Predicted action shape: {pred_action_across_time.shape}")
    
    # Plot results if requested
    if plot:
        # Generate save path if save_plot_path is provided
        actual_save_path = None
        if save_plot_path:
            actual_save_path = save_plot_path
        elif plot:  # Auto-generate path if plotting is requested but no path provided
            os.makedirs("./plots", exist_ok=True)
            actual_save_path = f"./plots/episode_{episode_idx}_action_comparison.png"
        
        plot_action_comparison(
            episode_idx=episode_idx,
            state_across_time=state_across_time,
            gt_action_across_time=gt_action_across_time,
            pred_action_across_time=pred_action_across_time,
            action_horizon=action_horizon,
            steps=min_length,
            save_path=actual_save_path
        )
    
    return mse


def plot_action_comparison(
    episode_idx: int,
    state_across_time: np.ndarray,
    gt_action_across_time: np.ndarray,
    pred_action_across_time: np.ndarray,
    action_horizon: int,
    steps: int,
    save_path: str = None
):
    """
    Plot comparison between ground truth and predicted actions over time.
    This function creates detailed plots showing the trajectory of each action dimension
    with inference points marked for analysis and optionally saves the plot.
    
    Args:
        episode_idx (int): Episode index for plot title
        state_across_time (np.ndarray): State trajectory over time
        gt_action_across_time (np.ndarray): Ground truth actions over time
        pred_action_across_time (np.ndarray): Predicted actions over time
        action_horizon (int): Action horizon for marking inference points
        steps (int): Total number of steps plotted
        save_path (str, optional): Path to save the plot. If None, plot is not saved.
    """
    action_dim = gt_action_across_time.shape[1]
    
    fig, axes = plt.subplots(nrows=action_dim, ncols=1, figsize=(12, 3 * action_dim))
    if action_dim == 1:
        axes = [axes]
    
    # Add global title
    fig.suptitle(
        f"Episode {episode_idx} - Action Prediction Evaluation (MSE: {np.mean((gt_action_across_time - pred_action_across_time) ** 2):.6f})",
        fontsize=14,
        color="blue",
    )
    
    for i, ax in enumerate(axes):
        # Plot state if dimensions match (joint positions vs joint commands)
        if state_across_time.shape[1] == gt_action_across_time.shape[1]:
            ax.plot(state_across_time[:, i], label="Current State", alpha=0.7, linestyle='--')
        
        # Plot ground truth and predicted actions
        ax.plot(gt_action_across_time[:, i], label="Ground Truth Action", color='green', linewidth=2)
        ax.plot(pred_action_across_time[:, i], label="Predicted Action", color='red', linewidth=2)
        
        # Mark inference points
        for j in range(0, steps, action_horizon):
            if j == 0:
                ax.plot(j, gt_action_across_time[j, i], "ko", markersize=8, label="Inference Point")
            else:
                ax.plot(j, gt_action_across_time[j, i], "ko", markersize=8)
        
        ax.set_title(f"Action Dimension {i}")
        ax.set_xlabel("Time Step")
        ax.set_ylabel("Action Value")
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save plot if save_path is provided
    if save_path:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"Plot saved to: {save_path}")
    
    plt.show()


def evaluate_multiple_episodes(
    policy_manager: InferenceManager,
    dataset: LeRobotDataset,
    episode_indices: list[int],
    max_steps: int = None,
    action_horizon: int = 16,
    plot_individual: bool = False,
    plot_summary: bool = True,
    save_individual_plots: bool = True,
    save_summary_plot: bool = True
):
    """
    Evaluate policy performance across multiple episodes and provide summary statistics.
    This function runs evaluation on multiple episodes and aggregates results for
    comprehensive policy performance analysis with optional plot saving.
    
    Args:
        policy_manager (InferenceManager): Loaded policy manager with inference capability
        dataset (LeRobotDataset): The loaded LeRobot dataset instance
        episode_indices (list[int]): List of episode indices to evaluate
        max_steps (int, optional): Maximum number of steps to evaluate per episode. If None, evaluates entire episodes
        action_horizon (int): Number of action predictions per inference call
        plot_individual (bool): Whether to plot individual episode results
        plot_summary (bool): Whether to plot summary statistics
        save_individual_plots (bool): Whether to save individual episode plots
        save_summary_plot (bool): Whether to save summary plot
        
    Returns:
        dict: Dictionary containing evaluation results and statistics
    """
    print(f"Evaluating policy on {len(episode_indices)} episodes...")

    episode_mses = []
    episode_results = {}
    
    for episode_idx in episode_indices:
        print(f"\n{'='*50}")
        print(f"Evaluating Episode {episode_idx}")
        print(f"{'='*50}")
        
        try:
            # Generate save path for individual episode plot if requested
            individual_save_path = None
            if save_individual_plots and plot_individual:
                os.makedirs("./plots", exist_ok=True)
                individual_save_path = f"./plots/episode_{episode_idx}_action_comparison.png"
            
            mse = evaluate_policy_on_episode(
                policy_manager=policy_manager,
                dataset=dataset,
                episode_idx=episode_idx,
                max_steps=max_steps,
                action_horizon=action_horizon,
                plot=plot_individual,
                save_plot_path=individual_save_path
            )
            
            episode_mses.append(mse)
            episode_results[episode_idx] = {
                'mse': mse,
                'status': 'success'
            }
            
        except Exception as e:
            print(f"Failed to evaluate episode {episode_idx}: {e}")
            episode_results[episode_idx] = {
                'mse': float('inf'),
                'status': 'failed',
                'error': str(e)
            }
    
    # Calculate summary statistics
    valid_mses = [mse for mse in episode_mses if mse != float('inf')]
    
    if valid_mses:
        mean_mse = np.mean(valid_mses)
        std_mse = np.std(valid_mses)
        min_mse = np.min(valid_mses)
        max_mse = np.max(valid_mses)
        
        print(f"\n{'='*60}")
        print(f"EVALUATION SUMMARY")
        print(f"{'='*60}")
        print(f"Episodes evaluated: {len(episode_indices)}")
        print(f"Successful evaluations: {len(valid_mses)}")
        print(f"Mean MSE: {mean_mse:.6f}")
        print(f"Std MSE: {std_mse:.6f}")
        print(f"Min MSE: {min_mse:.6f}")
        print(f"Max MSE: {max_mse:.6f}")
        
        # Plot summary if requested
        if plot_summary and len(valid_mses) > 1:

            plt.figure(figsize=(10, 6))
            
            plt.subplot(1, 2, 1)
            plt.bar(range(len(valid_mses)), valid_mses)
            plt.title("MSE per Episode")
            plt.xlabel("Episode Index")
            plt.ylabel("MSE")
            plt.xticks(range(len(valid_mses)), [idx for idx in episode_indices if episode_results[idx]['status'] == 'success'])
            
            plt.subplot(1, 2, 2)
            plt.hist(valid_mses, bins=10, alpha=0.7, edgecolor='black')
            plt.title("MSE Distribution")
            plt.xlabel("MSE")
            plt.ylabel("Frequency")
            plt.axvline(mean_mse, color='red', linestyle='--', label=f'Mean: {mean_mse:.6f}')
            plt.legend()
            
            plt.tight_layout()
            
            # Save summary plot if requested
            if save_summary_plot:
                os.makedirs("./plots", exist_ok=True)
                summary_save_path = f"./plots/evaluation_summary_{len(episode_indices)}_episodes.png"
                plt.savefig(summary_save_path, dpi=300, bbox_inches='tight')
                print(f"Summary plot saved to: {summary_save_path}")
            
            plt.show()
        
        summary = {
            'episode_results': episode_results,
            'mean_mse': mean_mse,
            'std_mse': std_mse,
            'min_mse': min_mse,
            'max_mse': max_mse,
            'num_episodes': len(episode_indices),
            'num_successful': len(valid_mses)
        }
        
    else:
        print("No successful evaluations to summarize.")
        summary = {
            'episode_results': episode_results,
            'mean_mse': float('inf'),
            'std_mse': 0.0,
            'min_mse': float('inf'),
            'max_mse': float('inf'),
            'num_episodes': len(episode_indices),
            'num_successful': 0
        }
    
    return summary


def main():
    repo_id = "ROBOTIS/omy_f3m_Stack_cup"
    policy_path = '/root/.cache/huggingface/hub/models--ROBOTIS--omy_stack_cup_60k/snapshots/9744b906b355d6c82bfb39da5e34cc8866f47ad6'
    dataset = load_dataset(repo_id)

    explore_dataset_episodes(dataset, max_episodes=3)
    
    # Analyze specific episode if dataset has episodes
    if dataset.num_episodes > 0:
        episode_idx = 0
        print(f"\nAnalyzing episode {episode_idx}...")
        
        # Get episode data
        episode_data = get_episode_data(dataset, episode_idx)
        print(f"Episode {episode_idx} contains {len(episode_data)} frames")
        
        # Analyze trajectory
        analyze_episode_trajectories(dataset, episode_idx)
        
        # Save sample images
        print(f"\nSaving sample images from episode {episode_idx}...")
        save_episode_images(dataset, episode_idx, "./episode_images", max_frames=5)
        
        # Comprehensive visualization
        visualize_episode_data(dataset, episode_idx, save_images=True)
        
        # Load and evaluate policy if path is provided
        print(f"\nLoading policy for evaluation...")
        try:
            policy_manager = InferenceManager()
            success, message = policy_manager.validate_policy(policy_path)
            
            if success:
                print(f"Policy validation: {message}")
                policy_loaded = policy_manager.load_policy()
                
                if policy_loaded:
                    print("Policy loaded successfully!")
                    
                    # Evaluate on single episode with plot saving - full episode
                    print(f"\nEvaluating policy on episode {episode_idx} (full episode)...")
                    mse = evaluate_policy_on_episode(
                        policy_manager=policy_manager,
                        dataset=dataset,
                        episode_idx=episode_idx,
                        max_steps=None,  # Evaluate entire episode
                        action_horizon=16,
                        plot=True,
                        save_plot_path=f"./plots/single_episode_{episode_idx}_evaluation.png"
                    )
                    
                    # Evaluate on multiple episodes with plot saving - full episodes
                    episode_indices = list(range(min(3, dataset.num_episodes)))
                    print(f"\nEvaluating policy on episodes {episode_indices} (full episodes)...")
                    summary = evaluate_multiple_episodes(
                        policy_manager=policy_manager,
                        dataset=dataset,
                        episode_indices=episode_indices,
                        max_steps=None,  # Evaluate entire episodes
                        action_horizon=16,
                        plot_individual=True,  # Enable individual episode plots
                        plot_summary=True,
                        save_individual_plots=True,
                        save_summary_plot=True
                    )
                    
                    print(f"\nPolicy evaluation completed!")
                    print(f"Summary: {summary}")
                    
                else:
                    print("Failed to load policy")
            else:
                print(f"Policy validation failed: {message}")
                
        except Exception as e:
            print(f"Policy evaluation failed: {e}")
            print("Continuing with dataset analysis only...")
    
    print("\nDataset evaluation completed!")


if __name__ == "__main__":
    main()
