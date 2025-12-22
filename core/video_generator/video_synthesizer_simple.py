import os
import tempfile
import shutil
from pathlib import Path
from typing import List, Union, Optional, Tuple, Dict
import logging
import subprocess
from PIL import Image
import numpy as np
import json

logger = logging.getLogger(__name__)


class VideoSynthesizer:
    """Synthesize video from images and audio files using ffmpeg directly"""
    
    def __init__(
        self,
        fps: int = 30,
        resolution: Tuple[int, int] = (1920, 1080),
        transition_duration: float = 0.5
    ):
        """
        Initialize video synthesizer
        
        Args:
            fps: Frames per second for output video
            resolution: Output video resolution (width, height)
            transition_duration: Duration of fade transition between slides
        """
        self.fps = fps
        self.resolution = resolution
        self.transition_duration = transition_duration
        
        # Check if ffmpeg is available
        if not self._check_ffmpeg():
            raise RuntimeError("ffmpeg not found. Please install ffmpeg to use video synthesis.")
    
    def synthesize(
        self,
        images: List[Union[str, Path, Image.Image]],
        audio_files: List[Union[str, Path]],
        output_path: Union[str, Path],
        title: Optional[str] = None,
        fade_in: bool = True,
        fade_out: bool = True,
        background_color: str = "black",
        progress_callback: Optional[callable] = None
    ) -> Path:
        """
        Synthesize video from images and audio files
        
        Args:
            images: List of image paths or PIL Image objects
            audio_files: List of audio file paths
            output_path: Output video file path
            title: Optional title to display at the beginning
            fade_in: Whether to fade in the first slide
            fade_out: Whether to fade out the last slide
            background_color: Background color for letterboxing
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Path to the generated video file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if len(images) != len(audio_files):
            raise ValueError(f"Number of images ({len(images)}) must match number of audio files ({len(audio_files)})")
        
        logger.info(f"Synthesizing video with {len(images)} slides using ffmpeg")
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir = Path(tmp_dir)
            
            # Prepare images
            image_paths = []
            for i, image in enumerate(images):
                if progress_callback:
                    progress_callback(i / (len(images) * 2), f"Preparing image {i+1}")
                
                if isinstance(image, Image.Image):
                    img_path = tmp_dir / f"slide_{i:03d}.png"
                    # Resize and save
                    img_resized = self._resize_pil_image(image, self.resolution, background_color)
                    img_resized.save(img_path, "PNG")
                    image_paths.append(img_path)
                else:
                    # Load, resize and save
                    img = Image.open(image)
                    img_resized = self._resize_pil_image(img, self.resolution, background_color)
                    img_path = tmp_dir / f"slide_{i:03d}.png"
                    img_resized.save(img_path, "PNG")
                    image_paths.append(img_path)
            
            # Create video segments
            video_segments = []
            for i, (img_path, audio_file) in enumerate(zip(image_paths, audio_files)):
                if progress_callback:
                    progress_callback((len(images) + i) / (len(images) * 2), f"Creating video segment {i+1}")
                
                segment_path = tmp_dir / f"segment_{i:03d}.mp4"
                duration = self._get_audio_duration(audio_file)
                logger.info(f"Audio file {audio_file} duration: {duration} seconds")
                
                # Build ffmpeg command
                cmd = [
                    'ffmpeg', '-y',
                    '-loop', '1',
                    '-framerate', str(self.fps),
                    '-i', str(img_path),
                    '-i', str(audio_file),
                    '-c:v', 'libx264',
                    '-tune', 'stillimage',
                    '-c:a', 'aac',  # Encode audio to AAC for MP4 compatibility
                    '-b:a', '192k',  # Audio bitrate
                    '-pix_fmt', 'yuv420p',
                    '-t', str(duration),  # Use audio duration
                    '-map', '0:v',  # Map video from first input
                    '-map', '1:a'   # Map audio from second input
                ]
                
                # Add video filters
                vf_filters = []
                vf_filters.append(f'scale={self.resolution[0]}:{self.resolution[1]}:force_original_aspect_ratio=decrease')
                vf_filters.append(f'pad={self.resolution[0]}:{self.resolution[1]}:(ow-iw)/2:(oh-ih)/2:black')
                
                # Add fade effects
                if fade_in and i == 0:
                    vf_filters.append(f'fade=in:0:{int(self.transition_duration * self.fps)}')
                if fade_out and i == len(images) - 1:
                    fade_start = int((duration - self.transition_duration) * self.fps)
                    vf_filters.append(f'fade=out:{fade_start}:{int(self.transition_duration * self.fps)}')
                
                if vf_filters:
                    cmd.extend(['-vf', ','.join(vf_filters)])
                
                cmd.append(str(segment_path))
                
                logger.debug(f"Running ffmpeg command: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.error(f"ffmpeg error for segment {i+1}: {result.stderr}")
                    raise RuntimeError(f"Failed to create segment {i+1}: {result.stderr}")
                
                # Check if segment was created successfully
                if not segment_path.exists():
                    raise RuntimeError(f"Segment {i+1} was not created")
                
                video_segments.append(segment_path)
                logger.info(f"Created video segment {i+1}: {segment_path}")
            
            # Concatenate all segments
            if progress_callback:
                progress_callback(0.9, "Concatenating video segments")
            
            # Create concat file
            concat_file = tmp_dir / "concat.txt"
            with open(concat_file, 'w') as f:
                for segment in video_segments:
                    f.write(f"file '{segment}'\n")
            
            # Concatenate with re-encoding to ensure compatibility
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_file),
                '-c:v', 'libx264',  # Re-encode video
                '-c:a', 'aac',      # Re-encode audio  
                '-b:a', '192k',     # Audio bitrate
                '-ar', '44100',     # Audio sample rate
                '-ac', '2',         # Stereo audio
                '-movflags', '+faststart',  # Optimize for streaming
                str(output_path)
            ]
            
            logger.debug(f"Running concat command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"ffmpeg concat error: {result.stderr}")
                raise RuntimeError(f"Failed to concatenate video: {result.stderr}")
        
        if progress_callback:
            progress_callback(1.0, "Complete")
        
        logger.info(f"Video saved to: {output_path}")
        return output_path
    
    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available"""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def _get_audio_duration(self, audio_file: Union[str, Path]) -> float:
        """Get duration of audio file using ffprobe"""
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(audio_file)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration = float(result.stdout.strip())
            logger.debug(f"Audio duration for {audio_file}: {duration} seconds")
            return duration
        except (subprocess.CalledProcessError, ValueError) as e:
            logger.warning(f"Could not get duration for {audio_file}: {e}")
            logger.warning(f"ffprobe stderr: {result.stderr if 'result' in locals() else 'N/A'}")
            # Try alternative method using ffmpeg
            try:
                alt_cmd = ['ffmpeg', '-i', str(audio_file), '-hide_banner', '-f', 'null', '-']
                alt_result = subprocess.run(alt_cmd, capture_output=True, text=True)
                # Parse duration from ffmpeg output
                import re
                match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', alt_result.stderr)
                if match:
                    hours, minutes, seconds = match.groups()
                    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                    logger.info(f"Got duration using ffmpeg: {duration} seconds")
                    return duration
            except Exception as e2:
                logger.error(f"Alternative duration detection also failed: {e2}")
            
            # Default to 5 seconds
            logger.warning("Using default duration of 5 seconds")
            return 5.0
    
    def _resize_pil_image(self, img: Image.Image, target_size: Tuple[int, int], background_color: str) -> Image.Image:
        """Resize PIL image to target size while maintaining aspect ratio"""
        # Convert to RGB if necessary
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Calculate scaling factor
        w, h = img.size
        target_w, target_h = target_size
        scale = min(target_w / w, target_h / h)
        
        # Calculate new size
        new_w = int(w * scale)
        new_h = int(h * scale)
        
        # Resize image
        img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        # Create background
        if background_color == "black":
            bg_color = (0, 0, 0)
        elif background_color == "white":
            bg_color = (255, 255, 255)
        else:
            bg_color = (0, 0, 0)
        
        background = Image.new('RGB', target_size, bg_color)
        
        # Paste resized image onto background
        x = (target_w - new_w) // 2
        y = (target_h - new_h) // 2
        background.paste(img_resized, (x, y))
        
        return background
    
    def create_slideshow_video(
        self,
        ppt_images: List[Union[str, Path]],
        transcripts: List[Dict[str, str]],
        voice_config: Dict,
        output_path: Union[str, Path],
        speech_synthesizer = None
    ) -> Path:
        """
        Create a complete slideshow video from PPT images and transcripts
        
        Args:
            ppt_images: List of PPT slide images
            transcripts: List of transcript dictionaries with 'transcript' key
            voice_config: Voice configuration for speech synthesis
            output_path: Output video file path
            speech_synthesizer: Optional speech synthesizer instance
            
        Returns:
            Path to generated video
        """
        if speech_synthesizer is None:
            from ..speech_generator import SpeechSynthesisPlugin
            speech_synthesizer = SpeechSynthesisPlugin()
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_dir = Path(tmp_dir)
            audio_files = []
            
            # Generate audio for each transcript
            for i, transcript_data in enumerate(transcripts):
                logger.info(f"Generating audio for slide {i+1}")
                
                audio_path = tmp_dir / f"audio_{i:03d}.wav"
                audio_bytes = speech_synthesizer.synthesize(
                    text=transcript_data['transcript'],
                    output_path=audio_path,
                    **voice_config
                )
                audio_files.append(audio_path)
            
            # Create video
            return self.synthesize(
                images=ppt_images,
                audio_files=audio_files,
                output_path=output_path,
                fade_in=True,
                fade_out=True
            )