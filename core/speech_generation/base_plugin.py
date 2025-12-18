from abc import ABC, abstractmethod
from typing import Optional, List, Any
from pathlib import Path


class BaseSpeechPlugin(ABC):
    """Base class for speech synthesis plugins"""
    
    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        output_path: Optional[Path] = None,
        **kwargs
    ) -> bytes:
        """
        Synthesize speech from text
        
        Args:
            text: Text to convert to speech
            voice_id: Voice identifier
            output_path: Path to save output audio
            **kwargs: Additional plugin-specific parameters
        
        Returns:
            Audio data as bytes
        """
        pass
    
    @abstractmethod
    async def synthesize_async(
        self,
        text: str,
        voice_id: Optional[str] = None,
        output_path: Optional[Path] = None,
        **kwargs
    ) -> bytes:
        """
        Asynchronously synthesize speech from text
        
        Args:
            text: Text to convert to speech
            voice_id: Voice identifier
            output_path: Path to save output audio
            **kwargs: Additional plugin-specific parameters
        
        Returns:
            Audio data as bytes
        """
        pass
    
    @abstractmethod
    def batch_synthesize(
        self,
        texts: List[str],
        voice_id: Optional[str] = None,
        output_dir: Optional[Path] = None,
        **kwargs
    ) -> List[bytes]:
        """
        Batch synthesize multiple texts
        
        Args:
            texts: List of texts to synthesize
            voice_id: Voice identifier to use for all texts
            output_dir: Directory to save output files
            **kwargs: Additional plugin-specific parameters
        
        Returns:
            List of audio bytes
        """
        pass
    
    @abstractmethod
    def get_available_voices(self) -> List[str]:
        """
        Get list of available voice IDs
        
        Returns:
            List of voice identifiers
        """
        pass
    
    def validate_text(self, text: str) -> bool:
        """
        Validate text before synthesis
        
        Args:
            text: Text to validate
        
        Returns:
            True if valid, False otherwise
        """
        if not text or not text.strip():
            return False
        
        # Add more validation logic as needed
        return True
    
    def preprocess_text(self, text: str) -> str:
        """
        Preprocess text before synthesis
        
        Args:
            text: Original text
        
        Returns:
            Preprocessed text
        """
        # Remove multiple spaces
        text = " ".join(text.split())
        
        # Trim whitespace
        text = text.strip()
        
        return text