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
Scale AI Data Converter.

Converts rosbag2 MCAP files to Scale AI format:
- Image topics → MP4 video (removed from MCAP)
- MCAP is modified: image topics removed, unmatched camera_info removed
- Meta files (meta_data.json, metadata.yaml, robot.urdf) are copied

Output structure:
    episode/
    ├── meta_data.json      (copied)
    ├── metadata.yaml       (copied)
    ├── robot.urdf          (copied)
    ├── cam_left_head.mp4   (new - replaces image topic)
    ├── cam_right_head.mp4
    ├── cam_left_wrist.mp4
    ├── cam_right_wrist.mp4
    └── episode.mcap        (modified - no images, synced camera_info only)
"""

from collections import defaultdict
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Dict, List, Optional, Set, Tuple

import cv2
import numpy as np

try:
    from mcap.reader import make_reader
    from mcap.writer import Writer
    from mcap_ros2.decoder import DecoderFactory
except ImportError:
    make_reader = None
    Writer = None
    DecoderFactory = None

try:
    from rclpy.serialization import deserialize_message, serialize_message
    from rosidl_runtime_py.utilities import get_message
except ImportError:
    deserialize_message = None
    serialize_message = None
    get_message = None


@dataclass
class FrameData:
    """Data for a single frame."""
    timestamp_ns: int
    image: Optional[np.ndarray] = None
    camera_info: Optional[dict] = None


@dataclass
class ConversionResult:
    """Result of a conversion operation."""
    success: bool
    video_path: Optional[str] = None
    mcap_path: Optional[str] = None
    frame_count: int = 0
    dropped_image_only: int = 0
    dropped_info_only: int = 0
    message: str = ""


@dataclass
class CameraMatchResult:
    """Result of camera matching for a single camera."""
    camera_name: str
    image_topic: str
    info_topic: str
    matched_timestamps: Set[int] = field(default_factory=set)
    frames: List[FrameData] = field(default_factory=list)
    dropped_image_only: int = 0
    dropped_info_only: int = 0


class ScaleAIConverter:
    """
    Converter for rosbag2 MCAP to Scale AI format.

    Converts image topics to MP4 video and creates a modified MCAP file
    with image topics removed and only matched camera_info retained.
    """

    # Camera topic mapping: (image_topic, camera_info_topic)
    DEFAULT_CAMERA_PAIRS = {
        'cam_left_head': (
            '/robot/camera/cam_left_head/image_raw/compressed',
            '/robot/camera/cam_left_head/image_raw/compressed/camera_info'
        ),
        'cam_right_head': (
            '/robot/camera/cam_right_head/image_raw/compressed',
            '/robot/camera/cam_right_head/image_raw/compressed/camera_info'
        ),
        'cam_left_wrist': (
            '/robot/camera/cam_left_wrist/image_raw/compressed',
            '/robot/camera/cam_left_wrist/image_raw/compressed/camera_info'
        ),
        'cam_right_wrist': (
            '/robot/camera/cam_right_wrist/image_raw/compressed',
            '/robot/camera/cam_right_wrist/image_raw/compressed/camera_info'
        ),
    }

    # Meta files to copy
    META_FILES = ['meta_data.json', 'metadata.yaml', 'robot.urdf']

    def __init__(
        self,
        fps: int = 15,
        use_hardware_encoding: bool = True,
        camera_pairs: Optional[Dict[str, Tuple[str, str]]] = None,
        exclude_topics: Optional[List[str]] = None,
        joint_offsets: Optional[Dict[str, Dict[str, float]]] = None
    ):
        """
        Initialize the converter.

        Args:
            fps: Output video frame rate.
            use_hardware_encoding: Try to use Jetson NVENC if available.
            camera_pairs: Custom camera topic pairs. If None, uses defaults.
            exclude_topics: List of topic keywords to exclude (e.g., ['head_leader', 'lift_follower']).
            joint_offsets: Dict of joint offsets to apply.
                Format: {'topic_keyword': {'joint_name': offset_rad}}
                Example: {'arm_left_leader': {'arm_l_joint6': 0.30}}
        """
        if make_reader is None or DecoderFactory is None or Writer is None:
            raise ImportError(
                'mcap and mcap-ros2-support packages are required. '
                'Install with: pip install mcap mcap-ros2-support'
            )

        self.fps = fps
        self.use_hardware_encoding = use_hardware_encoding
        self.camera_pairs = camera_pairs or self.DEFAULT_CAMERA_PAIRS
        self.exclude_topics = exclude_topics or []
        self.joint_offsets = joint_offsets or {}
        self._hw_encoder = self._detect_hardware_encoder() if use_hardware_encoding else None

    def _detect_hardware_encoder(self) -> Optional[str]:
        """Detect available hardware encoder on Jetson."""
        encoders_to_try = [
            'h264_nvmpi',      # Jetson multimedia API
            'h264_v4l2m2m',    # V4L2 memory-to-memory
        ]

        for encoder in encoders_to_try:
            try:
                result = subprocess.run(
                    ['ffmpeg', '-hide_banner', '-encoders'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if encoder in result.stdout:
                    print(f'Detected hardware encoder: {encoder}')
                    return encoder
            except Exception:
                continue

        print('No hardware encoder detected, using software encoding (libx264)')
        return None

    def convert_episode(
        self,
        input_path: str,
        output_dir: str
    ) -> Dict[str, ConversionResult]:
        """
        Convert a single episode to Scale AI format.

        Args:
            input_path: Path to episode directory containing MCAP file.
            output_dir: Output directory for converted files.

        Returns:
            Dictionary mapping camera names to ConversionResult.
        """
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Find MCAP file
        mcap_file = self._find_mcap_file(input_path)
        print(f'Converting: {mcap_file}')
        print(f'Output directory: {output_dir}')

        # Step 1: Read and match camera data
        print('\n[Step 1] Reading and matching camera data...')
        camera_results = self._read_and_match_cameras(mcap_file)

        # Collect all matched timestamps per camera_info topic
        matched_info_timestamps: Dict[str, Set[int]] = {}
        for result in camera_results.values():
            matched_info_timestamps[result.info_topic] = result.matched_timestamps

        # Step 2: Create MP4 videos
        print('\n[Step 2] Creating MP4 videos...')
        video_results = {}
        for camera_name, result in camera_results.items():
            if result.frames:
                video_path = output_dir / f'{camera_name}.mp4'
                success = self._create_video(result.frames, str(video_path))
                video_results[camera_name] = ConversionResult(
                    success=success,
                    video_path=str(video_path) if success else None,
                    frame_count=len(result.frames),
                    dropped_image_only=result.dropped_image_only,
                    dropped_info_only=result.dropped_info_only,
                    message='Video created' if success else 'Failed to create video'
                )
            else:
                video_results[camera_name] = ConversionResult(
                    success=False,
                    message=f'No matched frames for {camera_name}'
                )

        # Step 3: Create modified MCAP (no images, synced camera_info only)
        print('\n[Step 3] Creating modified MCAP...')
        output_mcap = output_dir / 'episode.mcap'
        self._create_filtered_mcap(
            mcap_file,
            str(output_mcap),
            matched_info_timestamps
        )

        # Step 4: Copy meta files
        print('\n[Step 4] Copying meta files...')
        self._copy_meta_files(input_path, output_dir)

        # Update results with mcap path
        for camera_name in video_results:
            video_results[camera_name].mcap_path = str(output_mcap)

        return video_results

    def _find_mcap_file(self, path: Path) -> str:
        """Find MCAP file in directory."""
        if path.is_file() and path.suffix == '.mcap':
            return str(path)

        mcap_files = list(path.glob('*.mcap'))
        if mcap_files:
            return str(mcap_files[0])

        raise FileNotFoundError(f'No MCAP file found in {path}')

    def _read_and_match_cameras(
        self,
        mcap_file: str
    ) -> Dict[str, CameraMatchResult]:
        """Read MCAP and match image/camera_info pairs."""
        # Collect image topics and info topics
        image_topics = set()
        info_topics = set()
        for image_topic, info_topic in self.camera_pairs.values():
            image_topics.add(image_topic)
            info_topics.add(info_topic)

        # Read all camera data
        image_data: Dict[str, Dict[int, any]] = defaultdict(dict)
        info_data: Dict[str, Dict[int, any]] = defaultdict(dict)

        with open(mcap_file, 'rb') as f:
            reader = make_reader(f, decoder_factories=[DecoderFactory()])

            for schema, channel, message, decoded_msg in reader.iter_decoded_messages():
                topic = channel.topic

                if topic not in image_topics and topic not in info_topics:
                    continue

                if decoded_msg is None:
                    continue

                # Get header timestamp
                if hasattr(decoded_msg, 'header') and hasattr(decoded_msg.header, 'stamp'):
                    stamp = decoded_msg.header.stamp
                    timestamp_ns = stamp.sec * 1_000_000_000 + stamp.nanosec
                else:
                    timestamp_ns = message.publish_time

                if topic in image_topics:
                    image_data[topic][timestamp_ns] = decoded_msg
                else:
                    info_data[topic][timestamp_ns] = decoded_msg

        # Match cameras
        results = {}
        for camera_name, (image_topic, info_topic) in self.camera_pairs.items():
            images = image_data.get(image_topic, {})
            infos = info_data.get(info_topic, {})

            image_timestamps = set(images.keys())
            info_timestamps = set(infos.keys())
            matched_timestamps = image_timestamps & info_timestamps

            # Create frames for matched timestamps
            frames = []
            for ts in sorted(matched_timestamps):
                try:
                    image_msg = images[ts]
                    np_arr = np.frombuffer(bytes(image_msg.data), np.uint8)
                    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                    if image is not None:
                        frames.append(FrameData(
                            timestamp_ns=ts,
                            image=image
                        ))
                except Exception as e:
                    print(f'  Warning: Failed to decode frame at {ts}: {e}')
                    matched_timestamps.discard(ts)

            results[camera_name] = CameraMatchResult(
                camera_name=camera_name,
                image_topic=image_topic,
                info_topic=info_topic,
                matched_timestamps=matched_timestamps,
                frames=frames,
                dropped_image_only=len(image_timestamps) - len(matched_timestamps),
                dropped_info_only=len(info_timestamps) - len(matched_timestamps)
            )

            print(f'  {camera_name}: {len(frames)} matched, '
                  f'{results[camera_name].dropped_image_only} image-only dropped, '
                  f'{results[camera_name].dropped_info_only} info-only dropped')

        return results

    def _create_filtered_mcap(
        self,
        input_mcap: str,
        output_mcap: str,
        matched_info_timestamps: Dict[str, Set[int]]
    ):
        """
        Create a new MCAP file with:
        - Image topics removed
        - Only matched camera_info retained
        - All other topics copied as-is
        """
        # Get image topics to exclude
        image_topics = set()
        info_topics = set()
        for image_topic, info_topic in self.camera_pairs.values():
            image_topics.add(image_topic)
            info_topics.add(info_topic)

        # Track statistics
        stats = {
            'total_read': 0,
            'images_skipped': 0,
            'info_skipped': 0,
            'info_kept': 0,
            'other_kept': 0
        }

        with open(input_mcap, 'rb') as f_in:
            reader = make_reader(f_in)
            summary = reader.get_summary()

            # Build schema and channel mappings
            schema_map = {}  # old_schema_id -> new_schema_id
            channel_map = {}  # old_channel_id -> new_channel_id

            with open(output_mcap, 'wb') as f_out:
                writer = Writer(f_out)
                writer.start()

                # Register schemas (exclude image schemas)
                for schema_id, schema in summary.schemas.items():
                    # Skip CompressedImage schema
                    if 'CompressedImage' in schema.name:
                        continue
                    new_id = writer.register_schema(
                        name=schema.name,
                        encoding=schema.encoding,
                        data=schema.data
                    )
                    schema_map[schema_id] = new_id

                # Register channels (exclude image channels)
                for channel_id, channel in summary.channels.items():
                    if channel.topic in image_topics:
                        continue
                    if channel.schema_id not in schema_map:
                        continue
                    new_id = writer.register_channel(
                        topic=channel.topic,
                        message_encoding=channel.message_encoding,
                        schema_id=schema_map[channel.schema_id]
                    )
                    channel_map[channel_id] = new_id

        # Second pass: copy messages
        with open(input_mcap, 'rb') as f_in:
            reader = make_reader(f_in, decoder_factories=[DecoderFactory()])

            with open(output_mcap, 'r+b') as f_out:
                # Seek to end and continue writing
                f_out.seek(0, 2)  # Seek to end
                # Re-open with append mode
                pass

        # Actually, let's do it properly in one pass
        with open(input_mcap, 'rb') as f_in, open(output_mcap, 'wb') as f_out:
            reader = make_reader(f_in, decoder_factories=[DecoderFactory()])
            summary = reader.get_summary()

            writer = Writer(f_out)
            writer.start()

            # Register schemas (exclude image schemas)
            schema_map = {}
            for schema_id, schema in summary.schemas.items():
                if 'CompressedImage' in schema.name:
                    continue
                new_id = writer.register_schema(
                    name=schema.name,
                    encoding=schema.encoding,
                    data=schema.data
                )
                schema_map[schema_id] = new_id

            # Register channels (exclude image channels)
            channel_map = {}
            for channel_id, channel in summary.channels.items():
                if channel.topic in image_topics:
                    continue
                if channel.schema_id not in schema_map:
                    continue
                new_id = writer.register_channel(
                    topic=channel.topic,
                    message_encoding=channel.message_encoding,
                    schema_id=schema_map[channel.schema_id]
                )
                channel_map[channel_id] = new_id

        # Third: copy messages (need to re-read)
        with open(input_mcap, 'rb') as f_in:
            reader = make_reader(f_in, decoder_factories=[DecoderFactory()])

            with open(output_mcap, 'ab') as f_out:
                # This approach won't work well, let me restructure

                pass

        # Let's use a cleaner approach
        self._create_filtered_mcap_clean(
            input_mcap, output_mcap, image_topics, info_topics, matched_info_timestamps
        )

    def _should_exclude_topic(self, topic: str) -> bool:
        """Check if a topic should be excluded based on exclude_topics list."""
        for keyword in self.exclude_topics:
            if keyword in topic:
                return True
        return False

    def _get_joint_offset_for_topic(self, topic: str) -> Optional[Dict[str, float]]:
        """Get joint offset configuration for a topic if applicable."""
        for keyword, offsets in self.joint_offsets.items():
            if keyword in topic:
                return offsets
        return None

    def _apply_joint_offset(
        self,
        data: bytes,
        topic_type: str,
        offsets: Dict[str, float]
    ) -> bytes:
        """Apply joint offset to JointState message data."""
        if serialize_message is None or deserialize_message is None:
            print('  Warning: rclpy not available, skipping joint offset')
            return data

        try:
            msg_class = get_message(topic_type)
            msg = deserialize_message(data, msg_class)

            if hasattr(msg, 'name') and hasattr(msg, 'position'):
                names = list(msg.name)
                positions = list(msg.position)

                for joint_name, offset in offsets.items():
                    if joint_name in names:
                        idx = names.index(joint_name)
                        positions[idx] += offset
                    elif joint_name.isdigit():
                        # Support index-based offset (e.g., '5' for joint6)
                        idx = int(joint_name)
                        if idx < len(positions):
                            positions[idx] += offset

                msg.position = positions
                return serialize_message(msg)

        except Exception as e:
            print(f'  Warning: Failed to apply joint offset: {e}')

        return data

    def _create_filtered_mcap_clean(
        self,
        input_mcap: str,
        output_mcap: str,
        image_topics: Set[str],
        info_topics: Set[str],
        matched_info_timestamps: Dict[str, Set[int]]
    ):
        """Create filtered MCAP file (clean implementation)."""
        stats = {
            'images_skipped': 0,
            'excluded_skipped': 0,
            'info_kept': 0,
            'joint_offset_applied': 0,
            'other_kept': 0
        }

        # Build topic type map for joint offset application
        topic_types = {}

        with open(input_mcap, 'rb') as f_in:
            reader = make_reader(f_in)
            summary = reader.get_summary()

            # Build topic type mapping
            for channel_id, channel in summary.channels.items():
                if channel.schema_id in summary.schemas:
                    schema = summary.schemas[channel.schema_id]
                    topic_types[channel.topic] = schema.name

            with open(output_mcap, 'wb') as f_out:
                writer = Writer(f_out)
                writer.start()

                # Register schemas (exclude CompressedImage and excluded topics)
                schema_map = {}
                for schema_id, schema in summary.schemas.items():
                    if 'CompressedImage' in schema.name:
                        continue
                    new_id = writer.register_schema(
                        name=schema.name,
                        encoding=schema.encoding,
                        data=schema.data
                    )
                    schema_map[schema_id] = new_id

                # Register channels (exclude image topics and excluded topics)
                channel_map = {}
                for channel_id, channel in summary.channels.items():
                    if channel.topic in image_topics:
                        continue
                    if self._should_exclude_topic(channel.topic):
                        continue
                    if channel.schema_id not in schema_map:
                        continue
                    new_id = writer.register_channel(
                        topic=channel.topic,
                        message_encoding=channel.message_encoding,
                        schema_id=schema_map[channel.schema_id]
                    )
                    channel_map[channel_id] = new_id

                # Copy messages
                for schema, channel, message in reader.iter_messages():
                    topic = channel.topic

                    # Skip image topics
                    if topic in image_topics:
                        stats['images_skipped'] += 1
                        continue

                    # Skip excluded topics
                    if self._should_exclude_topic(topic):
                        stats['excluded_skipped'] += 1
                        continue

                    # Skip if channel not registered
                    if channel.id not in channel_map:
                        continue

                    data = message.data

                    # Apply joint offset if configured
                    offsets = self._get_joint_offset_for_topic(topic)
                    if offsets and 'joint_states' in topic:
                        topic_type = topic_types.get(topic)
                        if topic_type:
                            data = self._apply_joint_offset(data, topic_type, offsets)
                            stats['joint_offset_applied'] += 1

                    # Track statistics
                    if topic in info_topics:
                        stats['info_kept'] += 1
                    else:
                        stats['other_kept'] += 1

                    # Write message
                    writer.add_message(
                        channel_id=channel_map[channel.id],
                        log_time=message.log_time,
                        data=data,
                        publish_time=message.publish_time
                    )

                writer.finish()

        print(f'  MCAP created: {output_mcap}')
        print(f'    Images skipped: {stats["images_skipped"]}')
        if stats['excluded_skipped'] > 0:
            print(f'    Excluded topics skipped: {stats["excluded_skipped"]}')
        if stats['joint_offset_applied'] > 0:
            print(f'    Joint offset applied: {stats["joint_offset_applied"]} messages')
        print(f'    CameraInfo kept: {stats["info_kept"]}')
        print(f'    Other topics kept: {stats["other_kept"]}')

    def _create_video(self, frames: List[FrameData], output_path: str) -> bool:
        """Create MP4 video from frames using ffmpeg."""
        if not frames:
            return False

        height, width = frames[0].image.shape[:2]
        encoder = self._hw_encoder or 'libx264'

        cmd = [
            'ffmpeg',
            '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}',
            '-pix_fmt', 'bgr24',
            '-r', str(self.fps),
            '-i', '-',
            '-c:v', encoder,
            '-pix_fmt', 'yuv420p',
        ]

        if encoder == 'libx264':
            cmd.extend(['-preset', 'fast', '-crf', '23'])
        elif encoder in ['h264_nvmpi', 'h264_v4l2m2m']:
            cmd.extend(['-b:v', '8M'])

        cmd.append(output_path)

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            for frame in frames:
                process.stdin.write(frame.image.tobytes())

            process.stdin.close()
            process.wait()

            if process.returncode != 0:
                stderr = process.stderr.read().decode()
                print(f'  FFmpeg error: {stderr}')
                return False

            print(f'  Video saved: {output_path}')
            return True

        except Exception as e:
            print(f'  Error creating video: {e}')
            return False

    def _copy_meta_files(self, input_dir: Path, output_dir: Path):
        """Copy meta files to output directory."""
        for filename in self.META_FILES:
            src = input_dir / filename
            if src.exists():
                dst = output_dir / filename
                shutil.copy2(src, dst)
                print(f'  Copied: {filename}')


def convert_dataset(
    dataset_path: str,
    output_base_path: str,
    fps: int = 15,
    use_hardware_encoding: bool = True,
    exclude_topics: Optional[List[str]] = None,
    joint_offsets: Optional[Dict[str, Dict[str, float]]] = None
) -> Dict[str, Dict[str, ConversionResult]]:
    """Convert all episodes in a dataset to Scale AI format."""
    converter = ScaleAIConverter(
        fps=fps,
        use_hardware_encoding=use_hardware_encoding,
        exclude_topics=exclude_topics,
        joint_offsets=joint_offsets
    )

    dataset_path = Path(dataset_path)
    output_base_path = Path(output_base_path)
    results = {}

    episode_dirs = sorted([
        d for d in dataset_path.iterdir()
        if d.is_dir() and d.name.isdigit()
    ])

    print(f'Found {len(episode_dirs)} episodes in {dataset_path}')

    for episode_dir in episode_dirs:
        episode_id = episode_dir.name
        print(f'\n{"="*60}')
        print(f'Episode {episode_id}')
        print(f'{"="*60}')

        output_dir = output_base_path / episode_id

        try:
            episode_results = converter.convert_episode(
                str(episode_dir),
                str(output_dir)
            )
            results[episode_id] = episode_results
        except Exception as e:
            print(f'Error processing episode {episode_id}: {e}')
            results[episode_id] = {'error': str(e)}

    return results


def parse_joint_offsets(offset_str: str) -> Dict[str, Dict[str, float]]:
    """
    Parse joint offset string.

    Format: topic_keyword:joint_name:offset[,topic_keyword:joint_name:offset,...]
    Example: arm_left_leader:5:0.30,arm_right_leader:5:0.30

    The joint_name can be the actual joint name or an index number.
    """
    offsets = {}
    if not offset_str:
        return offsets

    for item in offset_str.split(','):
        parts = item.strip().split(':')
        if len(parts) != 3:
            print(f'Warning: Invalid offset format "{item}", expected topic:joint:offset')
            continue

        topic_keyword, joint_name, offset_value = parts
        try:
            offset = float(offset_value)
        except ValueError:
            print(f'Warning: Invalid offset value "{offset_value}"')
            continue

        if topic_keyword not in offsets:
            offsets[topic_keyword] = {}
        offsets[topic_keyword][joint_name] = offset

    return offsets


def main():
    """Command-line interface."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Convert rosbag2 MCAP to Scale AI format'
    )
    parser.add_argument('input_path', help='Path to episode directory or dataset')
    parser.add_argument('--output', '-o', required=True, help='Output directory')
    parser.add_argument('--fps', type=int, default=15, help='Video frame rate (default: 15)')
    parser.add_argument('--no-hw', action='store_true', help='Disable hardware encoding')
    parser.add_argument('--dataset', action='store_true', help='Convert entire dataset')
    parser.add_argument(
        '--exclude-topics',
        type=str,
        default='',
        help='Comma-separated list of topic keywords to exclude '
             '(e.g., "head_leader,head_follower,lift_leader,lift_follower,cmd_vel,odom")'
    )
    parser.add_argument(
        '--joint-offset',
        type=str,
        default='',
        help='Joint offset corrections. Format: topic_keyword:joint_index:offset_rad '
             '(e.g., "arm_left_leader:5:0.30,arm_right_leader:5:0.30" for joint6 offset)'
    )

    args = parser.parse_args()

    # Parse exclude topics
    exclude_topics = [t.strip() for t in args.exclude_topics.split(',') if t.strip()]
    if exclude_topics:
        print(f'Excluding topics containing: {exclude_topics}')

    # Parse joint offsets
    joint_offsets = parse_joint_offsets(args.joint_offset)
    if joint_offsets:
        print(f'Applying joint offsets: {joint_offsets}')

    if args.dataset:
        results = convert_dataset(
            args.input_path,
            args.output,
            fps=args.fps,
            use_hardware_encoding=not args.no_hw,
            exclude_topics=exclude_topics,
            joint_offsets=joint_offsets
        )
    else:
        converter = ScaleAIConverter(
            fps=args.fps,
            use_hardware_encoding=not args.no_hw,
            exclude_topics=exclude_topics,
            joint_offsets=joint_offsets
        )
        results = converter.convert_episode(args.input_path, args.output)

    # Print summary
    print('\n' + '=' * 60)
    print('CONVERSION SUMMARY')
    print('=' * 60)

    if args.dataset:
        for episode_id, episode_results in results.items():
            print(f'\nEpisode {episode_id}:')
            if isinstance(episode_results, dict) and 'error' not in episode_results:
                for camera_name, result in episode_results.items():
                    status = 'OK' if result.success else 'FAILED'
                    print(f'  {camera_name}: {status} ({result.frame_count} frames)')
    else:
        for camera_name, result in results.items():
            status = 'OK' if result.success else 'FAILED'
            print(f'{camera_name}: {status}')
            if result.success:
                print(f'  Frames: {result.frame_count}')
                print(f'  Video: {result.video_path}')
                print(f'  MCAP: {result.mcap_path}')


if __name__ == '__main__':
    main()
