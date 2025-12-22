import base64
import logging
import os
from typing import Optional, Dict, List
from pathlib import Path

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from .base_plugin import BaseSpeechPlugin

logger = logging.getLogger(__name__)


class ReferenceAudio(BaseModel):
    """Reference audio model for voice cloning"""
    audio: str = Field(..., description="Base64 encoded audio data")
    text: str = Field(..., description="Text corresponding to the audio")


class SpeechSynthesisRequest(BaseModel):
    """Request model for speech synthesis"""
    text: str = Field(..., description="Text to convert to speech")
    references: Optional[List[ReferenceAudio]] = Field(None, description="Reference audio and text for voice cloning")
    reference_id: Optional[str] = Field(None, description="Preset voice ID: 中文女, 中文男, 英文男, 英文女")
    max_new_tokens: Optional[int] = Field(512, description="Maximum new tokens for generation")
    chunk_length: Optional[int] = Field(150, description="Text chunk length for synthesis")
    temperature: Optional[float] = Field(0.7, description="Sampling temperature (0-1)")
    top_p: Optional[float] = Field(0.7, description="Top-p sampling value (0-1)")
    repetition_penalty: Optional[float] = Field(1.2, description="Repetition penalty (1-2)")


class SpeechSynthesisResponse(BaseModel):
    """Response model for speech synthesis"""
    success: int
    code: int
    msg: str
    data: Dict[str, str]


class SpeechSynthesisPlugin(BaseSpeechPlugin):
    """Speech synthesis plugin using the Speech Generation Service API"""
    
    def __init__(
        self,
        api_url: Optional[str] = "http://fosp-gateway.vemic.com/speech_generation_service",
        developer_secret: Optional[str] = None,
        open_id: Optional[str] = None,
        service_code: Optional[str] = None,
        timeout: float = 300.0
    ):
        """
        Initialize the speech synthesis plugin
        
        Args:
            api_url: API endpoint URL (defaults to env var SPEECH_API_URL)
            developer_secret: Developer secret for authentication (defaults to env var SPEECH_DEVELOPER_SECRET)
            open_id: Open ID for authentication (defaults to env var SPEECH_OPEN_ID)
            service_code: Service code identifier (defaults to env var SPEECH_SERVICE_CODE)
            timeout: Request timeout in seconds
        """
        # Get from environment variables if not provided
        self.api_url = api_url or os.getenv("SPEECH_API_URL")
        self.timeout = timeout
        
        # Get authentication credentials from environment variables
        developer_secret = developer_secret or os.getenv("SPEECH_DEVELOPER_SECRET")
        open_id = open_id or os.getenv("SPEECH_OPEN_ID")
        service_code = service_code or os.getenv("SPEECH_SERVICE_CODE", "speech_generation_service")
        
        # Log configuration (without sensitive data)
        logger.info(f"Initializing SpeechSynthesisPlugin with API URL: {self.api_url}")
        logger.debug(f"Developer Secret configured: {'Yes' if developer_secret else 'No'}")
        logger.debug(f"Open ID configured: {'Yes' if open_id else 'No'}")
        logger.debug(f"Service Code: {service_code}")
        
        self.headers = {
            "Content-Type": "application/json"
        }
        
        # Add authentication headers if provided
        if developer_secret:
            self.headers["Developer-Secret"] = developer_secret
        else:
            logger.warning("No Developer-Secret provided. Set SPEECH_DEVELOPER_SECRET environment variable.")
            
        if open_id:
            self.headers["Open-ID"] = open_id
        else:
            logger.warning("No Open-ID provided. Set SPEECH_OPEN_ID environment variable.")
            
        if service_code:
            self.headers["Service-Code"] = service_code
        
        self.client = httpx.Client(timeout=timeout)
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
    
    def close(self):
        """Close the HTTP client"""
        self.client.close()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    async def synthesize_async(
        self,
        text: str,
        reference_audio_path: Optional[Path] = None,
        reference_text: Optional[str] = None,
        reference_id: Optional[str] = None,
        output_path: Optional[Path] = None,
        **kwargs
    ) -> bytes:
        """
        Asynchronously synthesize speech from text
        
        Args:
            text: Text to convert to speech
            reference_audio_path: Path to reference audio file for voice cloning
            reference_text: Text corresponding to reference audio
            reference_id: Preset voice ID (中文女, 中文男, 英文男, 英文女)
            output_path: Path to save output audio file
            **kwargs: Additional parameters (max_new_tokens, chunk_length, temperature, top_p, repetition_penalty)
        
        Returns:
            Audio data as bytes
        
        Raises:
            ValueError: If neither reference audio nor reference ID is provided
            Exception: If API call fails
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            request_data = self._prepare_request(
                text, reference_audio_path, reference_text, reference_id, **kwargs
            )
            
            logger.info(f"Sending speech synthesis request for text: '{text[:50]}...'")
            
            response = await client.post(
                self.api_url,
                json=request_data.model_dump(exclude_none=True),
                headers=self.headers
            )
            
            return self._process_response(response, output_path)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def synthesize(
        self,
        text: str,
        reference_audio_path: Optional[Path] = None,
        reference_text: Optional[str] = None,
        reference_id: Optional[str] = None,
        output_path: Optional[Path] = None,
        **kwargs
    ) -> bytes:
        """
        Synchronously synthesize speech from text
        
        Args:
            text: Text to convert to speech
            reference_audio_path: Path to reference audio file for voice cloning
            reference_text: Text corresponding to reference audio
            reference_id: Preset voice ID (中文女, 中文男, 英文男, 英文女)
            output_path: Path to save output audio file
            **kwargs: Additional parameters (max_new_tokens, chunk_length, temperature, top_p, repetition_penalty)
        
        Returns:
            Audio data as bytes
        
        Raises:
            ValueError: If neither reference audio nor reference ID is provided
            Exception: If API call fails
        """
        request_data = self._prepare_request(
            text, reference_audio_path, reference_text, reference_id, **kwargs
        )
        
        logger.info(f"Sending speech synthesis request for text: '{text[:50]}...'")
        
        response = self.client.post(
            self.api_url,
            json=request_data.model_dump(exclude_none=True),
            headers=self.headers
        )
        
        return self._process_response(response, output_path)
    
    def _prepare_request(
        self,
        text: str,
        reference_audio_path: Optional[Path] = None,
        reference_text: Optional[str] = None,
        reference_id: Optional[str] = None,
        **kwargs
    ) -> SpeechSynthesisRequest:
        """Prepare the request data"""
        if not reference_id and not (reference_audio_path and reference_text):
            raise ValueError(
                "Either reference_id or both reference_audio_path and reference_text must be provided"
            )
        
        request_data = SpeechSynthesisRequest(text=text, **kwargs)
        
        if reference_audio_path and reference_text:
            audio_path = Path(reference_audio_path) if isinstance(reference_audio_path, str) else reference_audio_path
            audio_base64 = self._encode_audio(audio_path)
            request_data.references = [
                ReferenceAudio(audio=audio_base64, text=reference_text)
            ]
        elif reference_id:
            if reference_id not in ["中文女", "中文男", "英文男", "英文女"]:
                raise ValueError(
                    f"Invalid reference_id: {reference_id}. "
                    "Must be one of: 中文女, 中文男, 英文男, 英文女"
                )
            request_data.reference_id = reference_id
        
        return request_data
    
    def _encode_audio(self, audio_path: Path) -> str:
        """Encode audio file to base64"""
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
        
        return base64.b64encode(audio_bytes).decode("utf-8")
    
    def _process_response(self, response: httpx.Response, output_path: Optional[Path]) -> bytes:
        """Process API response and return audio bytes"""
        if response.status_code != 200:
            raise Exception(
                f"API call failed with status {response.status_code}: {response.text}"
            )
        
        response_data = SpeechSynthesisResponse(**response.json())
        
        if response_data.success != 1:
            raise Exception(f"Speech synthesis failed: {response_data.msg}")
        
        audio_base64 = response_data.data.get("audio_base64", "")
        if not audio_base64:
            raise Exception("No audio data in response")
        
        audio_bytes = base64.b64decode(audio_base64)
        
        if output_path:
            # Convert string to Path if necessary
            if isinstance(output_path, str):
                output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(audio_bytes)
            logger.info(f"Audio saved to: {output_path}")
        
        return audio_bytes
    
    def batch_synthesize(
        self,
        texts: List[str],
        reference_id: str = "中文女",
        output_dir: Optional[Path] = None,
        **kwargs
    ) -> List[bytes]:
        """
        Batch synthesize multiple texts
        
        Args:
            texts: List of texts to synthesize
            reference_id: Preset voice ID to use for all texts
            output_dir: Directory to save output files
            **kwargs: Additional synthesis parameters
        
        Returns:
            List of audio bytes
        """
        results = []
        
        for i, text in enumerate(texts):
            try:
                output_path = None
                if output_dir:
                    output_path = output_dir / f"audio_{i:03d}.wav"
                
                audio_bytes = self.synthesize(
                    text=text,
                    reference_id=reference_id,
                    output_path=output_path,
                    **kwargs
                )
                results.append(audio_bytes)
                
            except Exception as e:
                logger.error(f"Failed to synthesize text {i}: {e}")
                results.append(b"")
        
        return results
    
    def get_available_voices(self) -> List[str]:
        """
        Get list of available voice IDs
        
        Returns:
            List of voice identifiers
        """
        return ["中文女", "中文男", "英文男", "英文女"]