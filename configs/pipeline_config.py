from dataclasses import dataclass, field
from typing import Optional, Tuple
import json
from pathlib import Path


@dataclass
class PipelineConfig:
    """Configuration for PPT to Video Pipeline"""
    
    # PPT parsing configuration
    ppt_dpi: int = 300
    """DPI for extracting images from PPT"""
    
    # Transcript generation configuration
    ai_model: str = "gpt-4.1"
    """AI model to use for transcript generation"""
    
    max_tokens: int = 3000
    """Maximum tokens for transcript generation (increased for longer transcripts)"""
    
    temperature: float = 0.8
    """Temperature for AI model (0-1, higher = more creative)"""
    
    transcript_style: str = "professional"
    """Style of transcripts: professional, casual, academic, storytelling"""
    
    transcript_language: str = "zh-CN"
    """Language for transcript generation"""
    
    min_transcript_length: int = 200
    """Minimum number of characters per transcript"""
    
    # Speech synthesis configuration
    voice_id: str = "中文女"
    """Voice ID for speech synthesis: 中文女, 中文男, 英文女, 英文男"""
    
    speech_language: str = "zh-cn"
    """Language code for speech synthesis"""
    
    speech_speed: float = 1.0
    """Speech speed multiplier (0.5-2.0)"""
    
    speech_volume: float = 1.0
    """Speech volume multiplier (0-2.0)"""
    
    speech_pitch: int = 0
    """Speech pitch adjustment (-20 to 20)"""
    
    # Voice cloning configuration
    use_voice_clone: bool = False
    """Whether to use voice cloning"""
    
    reference_audio_path: Optional[str] = None
    """Path to reference audio file for voice cloning"""
    
    reference_text: Optional[str] = None
    """Text content of the reference audio"""
    
    # Video synthesis configuration
    video_fps: int = 30
    """Frames per second for output video"""
    
    video_resolution: Tuple[int, int] = (1920, 1080)
    """Output video resolution (width, height)"""
    
    transition_duration: float = 0.5
    """Duration of fade transition between slides in seconds"""
    
    fade_in: bool = True
    """Whether to fade in the first slide"""
    
    fade_out: bool = True
    """Whether to fade out the last slide"""
    
    # Output configuration
    output_dir: str = "output"
    """Directory for output files"""
    
    save_intermediates: bool = True
    """Whether to save intermediate files (images, transcripts, audio)"""
    
    # Processing configuration
    max_slides: Optional[int] = None
    """Maximum number of slides to process (None = all slides)"""
    
    batch_size: int = 5
    """Number of slides to process in one batch for transcript generation"""
    
    # API configuration
    api_retry_attempts: int = 3
    """Number of retry attempts for API calls"""
    
    api_timeout: int = 60
    """Timeout for API calls in seconds"""
    
    def save(self, path: str):
        """Save configuration to JSON file"""
        config_path = Path(path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(self.__dict__, f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, path: str) -> 'PipelineConfig':
        """Load configuration from JSON file"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle tuple conversion for video_resolution
        if 'video_resolution' in data and isinstance(data['video_resolution'], list):
            data['video_resolution'] = tuple(data['video_resolution'])
        
        return cls(**data)
    
    def validate(self) -> bool:
        """Validate configuration values"""
        errors = []
        
        # Validate DPI
        if self.ppt_dpi < 72 or self.ppt_dpi > 600:
            errors.append(f"ppt_dpi must be between 72 and 600, got {self.ppt_dpi}")
        
        # Validate tokens
        if self.max_tokens < 100 or self.max_tokens > 640000:
            errors.append(f"max_tokens must be between 100 and 10000, got {self.max_tokens}")
        
        # Validate temperature
        if self.temperature < 0 or self.temperature > 1:
            errors.append(f"temperature must be between 0 and 1, got {self.temperature}")
        
        # Validate transcript style
        valid_styles = ["professional", "casual", "academic", "storytelling"]
        if self.transcript_style not in valid_styles:
            errors.append(f"transcript_style must be one of {valid_styles}, got {self.transcript_style}")
        
        # Validate voice ID
        valid_voices = ["中文女", "中文男", "英文女", "英文男"]
        if self.voice_id not in valid_voices:
            errors.append(f"voice_id must be one of {valid_voices}, got {self.voice_id}")
        
        # Validate speech parameters
        if self.speech_speed < 0.5 or self.speech_speed > 2.0:
            errors.append(f"speech_speed must be between 0.5 and 2.0, got {self.speech_speed}")
        
        if self.speech_volume < 0 or self.speech_volume > 2.0:
            errors.append(f"speech_volume must be between 0 and 2.0, got {self.speech_volume}")
        
        if self.speech_pitch < -20 or self.speech_pitch > 20:
            errors.append(f"speech_pitch must be between -20 and 20, got {self.speech_pitch}")
        
        # Validate video parameters
        if self.video_fps < 1 or self.video_fps > 60:
            errors.append(f"video_fps must be between 1 and 60, got {self.video_fps}")
        
        if self.video_resolution[0] < 320 or self.video_resolution[1] < 240:
            errors.append(f"video_resolution too small: {self.video_resolution}")
        
        if self.transition_duration < 0 or self.transition_duration > 5:
            errors.append(f"transition_duration must be between 0 and 5, got {self.transition_duration}")
        
        # Validate batch size
        if self.batch_size < 1 or self.batch_size > 50:
            errors.append(f"batch_size must be between 1 and 50, got {self.batch_size}")
        
        if errors:
            for error in errors:
                print(f"Config validation error: {error}")
            return False
        
        return True


# Preset configurations
class ConfigPresets:
    """Preset configurations for common use cases"""
    
    @staticmethod
    def high_quality() -> PipelineConfig:
        """High quality configuration for final presentations"""
        return PipelineConfig(
            ppt_dpi=400,
            max_tokens=4000,
            temperature=0.7,
            transcript_style="professional",
            min_transcript_length=300,
            video_fps=30,
            video_resolution=(1920, 1080),
            speech_speed=0.95,
            save_intermediates=True
        )
    
    @staticmethod
    def fast_preview() -> PipelineConfig:
        """Fast configuration for quick previews"""
        return PipelineConfig(
            ppt_dpi=200,
            max_tokens=2000,
            temperature=0.8,
            min_transcript_length=150,
            video_fps=24,
            video_resolution=(1280, 720),
            batch_size=10,
            save_intermediates=False
        )
    
    @staticmethod
    def english_presentation() -> PipelineConfig:
        """Configuration for English presentations"""
        return PipelineConfig(
            transcript_language="en-US",
            voice_id="英文女",
            speech_language="en-us",
            transcript_style="professional",
            min_transcript_length=250
        )
    
    @staticmethod
    def academic_lecture() -> PipelineConfig:
        """Configuration for academic lectures"""
        return PipelineConfig(
            ppt_dpi=350,
            max_tokens=5000,
            temperature=0.6,
            transcript_style="academic",
            min_transcript_length=400,
            speech_speed=0.9,
            voice_id="中文男",
            save_intermediates=True
        )
    
    @staticmethod
    def storytelling() -> PipelineConfig:
        """Configuration for engaging storytelling style"""
        return PipelineConfig(
            max_tokens=4000,
            temperature=0.9,
            transcript_style="storytelling",
            min_transcript_length=350,
            speech_speed=0.95,
            voice_id="中文女",
            transition_duration=1.0
        )
    
    @staticmethod
    def voice_clone() -> PipelineConfig:
        """Configuration template for voice cloning"""
        return PipelineConfig(
            use_voice_clone=True,
            reference_audio_path=None,  # User needs to provide
            reference_text=None,        # User needs to provide
            speech_speed=1.0,
            min_transcript_length=250,
            save_intermediates=True
        )