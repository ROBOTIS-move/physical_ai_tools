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
from pathlib import Path
import time
from typing import List, Optional, Union

import numpy as np
from physical_ai_server.video_encoder.encoder_base import VideoEncoder


try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst, GLib
    GSTREAMER_AVAILABLE = True
except ImportError:
    GSTREAMER_AVAILABLE = False


class GStreamerEncoder(VideoEncoder):
    QUALITY_PRESETS = {
        # Resolution: (bitrate_low, bitrate_medium, bitrate_high)
        (640, 360): (800000, 1200000, 1500000),      # 0.8, 1.2, 1.5 Mbps
        (1280, 720): (2500000, 3500000, 5000000),    # 2.5, 3.5, 5 Mbps
        (1920, 1080): (5000000, 8000000, 12000000),  # 5, 8, 12 Mbps
        (3840, 2160): (15000000, 25000000, 40000000)  # 15, 25, 40 Mbps (4K)
    }

    def __init__(
        self,
        *args,
        bitrate: Optional[int] = None,
        preset_level: int = 1,
        quality: str = 'medium',
        clear_after_encode: bool = True,
        **kwargs
    ):
        if not GSTREAMER_AVAILABLE:
            raise ImportError('GStreamer Python bindings not available')

        super().__init__(*args, **kwargs)

        self.preset_level = preset_level
        self.quality = quality
        self.clear_after_encode = clear_after_encode

        # GStreamer-specific properties
        self.pipeline = None
        self.appsrc = None
        self.loop = None
        self.width = None
        self.height = None

        # Encoding status tracking (similar to FFmpegBufferEncoder)
        self.is_encoding = False
        self.encoding_completed = False
        self.encoding_started_at = None
        self.encoding_finished_at = None
        self.total_frames_encoded = 0
        self.output_path = None
        self.encoding_error = None

        # Auto-select bitrate if not specified
        if bitrate is None:
            self.bitrate = None  # Will be calculated when buffer is set
        else:
            self.bitrate = bitrate

        Gst.init(None)

    def set_buffer(self, frames: List[np.ndarray]) -> None:
        super().set_buffer(frames)

        if self.buffer:
            # Extract dimensions from first frame
            height, width = self.buffer[0].shape[:2]
            self.height = height
            self.width = width

            # Auto-calculate bitrate if not set
            if self.bitrate is None:
                self.bitrate = self._get_optimal_bitrate(width, height, self.quality)

    def _get_optimal_bitrate(self, width: int, height: int, quality: str) -> int:
        resolution = (width, height)

        # Try exact resolution match first
        if resolution in self.QUALITY_PRESETS:
            presets = self.QUALITY_PRESETS[resolution]
        else:
            # Calculate bitrate based on pixel count for custom resolutions
            pixel_count = width * height
            base_720p = 1280 * 720  # 921,600 pixels

            # Scale from 720p medium quality (3.5 Mbps)
            base_bitrate = 3500000
            scale_factor = pixel_count / base_720p

            medium_bitrate = int(base_bitrate * scale_factor)
            low_bitrate = int(medium_bitrate * 0.7)
            high_bitrate = int(medium_bitrate * 1.4)

            presets = (low_bitrate, medium_bitrate, high_bitrate)

        quality_map = {'low': 0, 'medium': 1, 'high': 2}
        quality_index = quality_map.get(quality.lower(), 1)

        return presets[quality_index]

    def is_encoding_completed(self) -> bool:
        return self.encoding_completed

    def get_encoding_status(self) -> dict:

        status = {
            'is_encoding': self.is_encoding,
            'encoding_completed': self.encoding_completed,
            'total_frames': len(self.buffer),
            'total_frames_encoded': self.total_frames_encoded,
            'progress_percentage': (
                self.total_frames_encoded / len(self.buffer) * 100) if self.buffer else 0,
            'output_path': str(self.output_path) if self.output_path else None,
            'encoding_error': self.encoding_error,
        }

        if self.encoding_started_at:
            status['started_at'] = self.encoding_started_at
            status['elapsed_time'] = (
                self.encoding_finished_at or time.time()) - self.encoding_started_at

            if self.encoding_finished_at:
                status['finished_at'] = self.encoding_finished_at
                status['encoding_time'] = self.encoding_finished_at - self.encoding_started_at

                if self.output_path and self.output_path.exists():
                    status['file_size'] = os.path.getsize(self.output_path)
                    status['file_size_kb'] = status['file_size'] / 1024

                if self.total_frames_encoded > 0:
                    status['encoding_fps'] = self.total_frames_encoded / status['encoding_time']

        return status

    def _create_pipeline(self, output_path: str) -> bool:
        pipeline_str = (
            f'appsrc name=source caps=video/x-raw,format=RGB,width={
                self.width},height={self.height},framerate={self.fps}/1 '
            f'! queue max-size-buffers=50 '
            f'! videoconvert ! nvvidconv '
            f'! nvv4l2h264enc bitrate={self.bitrate} preset-level={self.preset_level} '
            f'! h264parse ! qtmux ! filesink location={output_path}'
        )

        try:
            self.pipeline = Gst.parse_launch(pipeline_str)
            self.appsrc = self.pipeline.get_by_name('source')

            # Configure appsrc for optimal performance
            self.appsrc.set_property('block', False)
            self.appsrc.set_property('is-live', True)
            self.appsrc.set_property('format', Gst.Format.TIME)

            return True
        except Exception as e:
            self.encoding_error = f'Pipeline creation failed: {e}'
            return False

    def _setup_message_handler(self):
        self.loop = GLib.MainLoop()
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()

        def on_message(bus, message):
            msg_type = message.type
            if msg_type == Gst.MessageType.EOS:
                self.encoding_completed = True
                self.is_encoding = False
                self.encoding_finished_at = time.time()
                self.loop.quit()
            elif msg_type == Gst.MessageType.ERROR:
                err, debug = message.parse_error()
                self.encoding_error = f'Encoding error: {err}'
                self.is_encoding = False
                self.loop.quit()
            return True

        bus.connect('message', on_message)

    def _feed_frame_data(self):
        frame_duration = Gst.SECOND // self.fps

        def feed_data():
            try:
                for i, frame in enumerate(self.buffer):
                    # Convert numpy array to RGB bytes if needed
                    if frame.dtype != np.uint8:
                        frame = (frame * 255).astype(np.uint8)

                    # Ensure RGB format (H, W, 3)
                    if len(frame.shape) == 3 and frame.shape[2] == 3:
                        img_bytes = frame.tobytes()
                    else:
                        raise ValueError(f'Unsupported frame shape: {frame.shape}')

                    # Create GStreamer buffer
                    buffer = Gst.Buffer.new_allocate(None, len(img_bytes), None)
                    buffer.fill(0, img_bytes)
                    buffer.pts = i * frame_duration
                    buffer.duration = frame_duration

                    # Push buffer to pipeline
                    ret = self.appsrc.emit('push-buffer', buffer)
                    if ret != Gst.FlowReturn.OK:
                        break

                    self.total_frames_encoded += 1

                # Signal end of stream
                self.appsrc.emit('end-of-stream')
            except Exception as e:
                self.encoding_error = f'Frame feeding error: {e}'
                self.is_encoding = False
                self.loop.quit()

            return False

        GLib.idle_add(feed_data)

    def encode_video(self, video_path: Union[str, Path]) -> None:
        if not self.buffer:
            raise ValueError('No frames in buffer to encode')

        if self.width is None or self.height is None:
            raise ValueError('Frame dimensions not set. Call set_buffer() first.')

        self.is_encoding = True
        self.encoding_completed = False
        self.encoding_started_at = time.time()
        self.encoding_finished_at = None
        self.total_frames_encoded = 0
        self.encoding_error = None

        video_path = Path(video_path)
        self.output_path = video_path
        video_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if not self._create_pipeline(str(video_path)):
                raise RuntimeError(f'Failed to create pipeline: {self.encoding_error}')

            self._setup_message_handler()

            self.pipeline.set_state(Gst.State.PLAYING)

            self._feed_frame_data()

            self.loop.run()

            if self.encoding_error:
                raise RuntimeError(f'GStreamer encoding failed: {self.encoding_error}')

            if not video_path.exists():
                raise OSError(f'Video encoding did not work. File not found: {video_path}')

        except Exception as e:
            self.is_encoding = False
            self.encoding_completed = False
            print(f'Encoding failed: {e}')
            raise
        finally:
            self._cleanup()
            if self.clear_after_encode:
                self.clear_buffer()

    def _cleanup(self):
        """
        Clean up GStreamer resources and reset pipeline components.
        
        This method properly shuts down the GStreamer pipeline by setting it to NULL state,
        releases references to pipeline components, and resets internal variables to prevent
        memory leaks and ensure proper resource management.
        """
        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

        self.appsrc = None
        self.loop = None

    def get_last_error(self) -> Optional[str]:
        """
        Retrieve the last encoding error message if any occurred.
        
        Returns:
            Optional[str]: The error message string if an error occurred during encoding,
                          or None if no error has been recorded.
        """
        return self.encoding_error


def create_dummy_frames(num_frames: int = 1000, width: int = 640, height: int = 480) -> List[np.ndarray]:
    """
    Generate a list of dummy RGB frames for testing video encoding functionality.
    
    Creates synthetic video frames with animated gradient patterns that change over time,
    providing meaningful visual content for encoder testing. Each frame contains:
    - Red channel: horizontal gradient with sinusoidal modulation
    - Green channel: vertical gradient with cosinusoidal modulation  
    - Blue channel: radial gradient with circular pattern
    
    Args:
        num_frames (int): Number of frames to generate (default: 1000)
        width (int): Frame width in pixels (default: 640)
        height (int): Frame height in pixels (default: 480)
        
    Returns:
        List[np.ndarray]: List of numpy arrays representing RGB frames with shape (height, width, 3)
                         and dtype uint8, suitable for video encoding
    """
    frames = []
    
    print(f"Generating {num_frames} dummy frames ({width}x{height})...")
    
    for i in range(num_frames):
        # Create a frame with gradient colors that change over time
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Calculate animation progress as normalized value between 0 and 1
        progress = i / num_frames
        
        # Red channel: horizontal gradient with sinusoidal time-based modulation
        # Creates a left-to-right gradient that oscillates in intensity over time
        for x in range(width):
            frame[:, x, 0] = int((x / width) * 255 * (0.5 + 0.5 * np.sin(progress * 2 * np.pi)))
        
        # Green channel: vertical gradient with cosinusoidal time-based modulation
        # Creates a top-to-bottom gradient that oscillates in intensity over time
        for y in range(height):
            frame[y, :, 1] = int((y / height) * 255 * (0.5 + 0.5 * np.cos(progress * 2 * np.pi)))
        
        # Blue channel: radial gradient pattern emanating from center
        # Creates a circular pattern that pulses from center outward over time
        center_x, center_y = width // 2, height // 2
        max_dist = np.sqrt(center_x**2 + center_y**2)
        
        for y in range(height):
            for x in range(width):
                # Calculate distance from center point
                dist = np.sqrt((x - center_x)**2 + (y - center_y)**2)
                # Apply inverse distance gradient with time-based modulation
                frame[y, x, 2] = int((1 - dist / max_dist) * 255 * (0.5 + 0.5 * np.sin(progress * 4 * np.pi)))
        
        frames.append(frame)
        
        # Progress indicator every 100 frames to show generation status
        if (i + 1) % 100 == 0:
            print(f"Generated {i + 1}/{num_frames} frames")
    
    print(f"Dummy frame generation completed!")
    return frames


def test_gstreamer_encoder():
    """
    Comprehensive test function for GStreamerEncoder class functionality.
    
    This function performs extensive testing of the GStreamerEncoder with multiple
    quality settings and resolutions. It creates dummy video frames, tests encoding
    with different parameters, monitors encoding progress, and validates output files.
    
    Test cases include:
    - Low quality 360p encoding with 300 frames
    - Medium quality 720p encoding with 500 frames  
    - High quality 1080p encoding with 200 frames
    
    For each test case, the function:
    1. Creates an encoder instance with specific quality settings
    2. Generates dummy frames with appropriate resolution
    3. Performs video encoding and monitors progress
    4. Validates output file creation and measures performance metrics
    5. Reports encoding statistics including time, file size, and FPS
    """
    
    # Define test cases with different quality and resolution parameters
    test_cases = [
        {
            'name': 'Low Quality 360p',
            'width': 640,
            'height': 360,
            'quality': 'low',
            'fps': 30,
            'num_frames': 300
        },
        {
            'name': 'Medium Quality 720p', 
            'width': 1280,
            'height': 720,
            'quality': 'medium',
            'fps': 30,
            'num_frames': 500
        },
        {
            'name': 'High Quality 1080p',
            'width': 1920,
            'height': 1080, 
            'quality': 'high',
            'fps': 30,
            'num_frames': 200
        }
    ]
    
    # Create output directory for test video files
    output_dir = Path('./test_outputs')
    output_dir.mkdir(exist_ok=True)
    
    print("Starting GStreamerEncoder tests...")
    print("=" * 60)
    
    # Execute each test case sequentially
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}/{len(test_cases)}: {test_case['name']}")
        print("-" * 40)
        
        try:
            # Create encoder instance with test-specific parameters
            encoder = GStreamerEncoder(
                fps=test_case['fps'],
                quality=test_case['quality'],
                clear_after_encode=True
            )
            
            # Generate dummy frames for this test case
            frames = create_dummy_frames(
                num_frames=test_case['num_frames'],
                width=test_case['width'],
                height=test_case['height']
            )
            
            # Set frame buffer in encoder
            print("Setting frame buffer...")
            encoder.set_buffer(frames)
            
            # Define output path for encoded video
            output_path = output_dir / f"test_video_{i}_{test_case['quality']}_{test_case['width']}x{test_case['height']}.mp4"
            
            # Begin encoding process and measure performance
            print(f"Starting encoding to: {output_path}")
            start_time = time.time()
            
            # Execute video encoding
            encoder.encode_video(output_path)
            
            end_time = time.time()
            
            # Retrieve final encoding status and statistics
            final_status = encoder.get_encoding_status()
            
            print(f"\nEncoding completed successfully!")
            print(f"Encoding time: {end_time - start_time:.2f} seconds")
            print(f"Output file: {output_path}")
            print(f"File size: {final_status.get('file_size_kb', 0):.2f} KB")
            print(f"Encoding FPS: {final_status.get('encoding_fps', 0):.2f}")
            
            # Verify output file creation and report file statistics
            if output_path.exists():
                print(f"✓ Video file created successfully")
                file_size_mb = output_path.stat().st_size / (1024 * 1024)
                print(f"✓ File size: {file_size_mb:.2f} MB")
            else:
                print("✗ Video file was not created")
                
        except Exception as e:
            print(f"✗ Test failed: {e}")
            
            # Report detailed error information from encoder
            if 'encoder' in locals():
                error = encoder.get_last_error()
                if error:
                    print(f"Encoder error: {error}")
            
            continue
    
    print("\n" + "=" * 60)
    print("All tests completed!")


def test_simple_encoding():
    """
    Simple and quick test function for basic GStreamerEncoder functionality verification.
    
    This function provides a lightweight test case for rapid verification of encoder
    functionality without the overhead of multiple test scenarios. It creates a
    small set of dummy frames (100 frames at 640x480 resolution) and performs
    basic encoding with medium quality settings.
    
    The test includes:
    - Creation of encoder instance with default medium quality
    - Generation of 100 dummy frames at standard resolution
    - Video encoding to a simple output file
    - Basic validation of output file creation and size
    - Performance metrics reporting (encoding time and FPS)
    
    This function is ideal for quick functionality checks during development
    or when full test suite execution is not required.
    """
    print("Running simple GStreamerEncoder test...")
    
    try:
        # Create encoder instance with medium quality defaults
        encoder = GStreamerEncoder(fps=30, quality='medium')
        
        # Generate small set of test frames for quick validation
        frames = create_dummy_frames(num_frames=100, width=640, height=480)
        
        # Configure encoder with generated frames
        encoder.set_buffer(frames)
        
        # Define simple output path
        output_path = Path('./simple_test_output.mp4')
        print(f"Encoding to: {output_path}")
        
        # Execute encoding process
        encoder.encode_video(output_path)
        
        # Validate results and report statistics
        if output_path.exists():
            file_size = output_path.stat().st_size / (1024 * 1024)
            print(f"✓ Success! Video created: {file_size:.2f} MB")
            
            # Extract and display encoding performance metrics
            status = encoder.get_encoding_status()
            print(f"Encoding time: {status.get('encoding_time', 0):.2f} seconds")
            print(f"Encoding FPS: {status.get('encoding_fps', 0):.2f}")
        else:
            print("✗ Failed! Video file not created")
            
    except Exception as e:
        print(f"✗ Test failed: {e}")


# Test execution entry point
if __name__ == '__main__':
    """
    Main execution block for running GStreamerEncoder tests.
    
    This block provides command-line interface for test execution with two modes:
    1. Simple test mode (--simple flag): Executes quick basic functionality test
    2. Full test mode (default): Runs comprehensive test suite with multiple scenarios
    
    Usage:
        python3 gstreamer_encoder.py           # Run full test suite
        python3 gstreamer_encoder.py --simple  # Run simple quick test
    """
    import sys
    
    print("GStreamerEncoder Test Script")
    print("=" * 60)
    
    # Determine test mode based on command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == '--simple':
        test_simple_encoding()
    else:
        print("Running full test suite...")
        print("Use '--simple' flag for quick test")
        print()
        test_gstreamer_encoder()


