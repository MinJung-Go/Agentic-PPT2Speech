from .ppt_parser import PPTParser
from .transcript_generator import TranscriptGenerator  
from .speech_generation import SpeechSynthesisPlugin
from .video_generation import VideoSynthesizer
from .pipeline import PPTToVideoPipeline

__all__ = [
    "PPTParser",
    "TranscriptGenerator", 
    "SpeechSynthesisPlugin",
    "VideoSynthesizer",
    "PPTToVideoPipeline"
]