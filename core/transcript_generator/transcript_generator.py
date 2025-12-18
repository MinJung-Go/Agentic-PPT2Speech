import os
import base64
import json
from pathlib import Path
from typing import List, Dict, Optional, Union
import logging
from PIL import Image
import io
import httpx
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential
import asyncio

logger = logging.getLogger(__name__)


class TranscriptGenerator:
    """Generate speech transcripts for PPT slides using OpenAI Vision API"""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        max_tokens: int = 500,
        temperature: float = 0.7
    ):
        """
        Initialize transcript generator
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            model: OpenAI model to use (default: gpt-4o)
            max_tokens: Maximum tokens per response
            temperature: Model temperature for creativity
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.base_url = os.environ.get("OPENAI_API", "https://api.openai.com/v1")
        self.proxy = os.environ.get("PROXY_SERVER")
        if not self.api_key:
            raise ValueError("OpenAI API key must be provided or set in OPENAI_API_KEY environment variable")
            
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=httpx.AsyncClient(proxy=self.proxy) if self.proxy else None,
        )

        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        
    async def generate_transcript(
        self,
        images: List[Union[str, Path, Image.Image]],
        context: Optional[str] = None,
        style: str = "professional",
        language: str = "zh-CN"
    ) -> List[Dict[str, str]]:
        """
        Generate transcripts for multiple slide images
        
        Args:
            images: List of image paths, PIL Images, or base64 strings
            context: Additional context about the presentation
            style: Speaking style (professional, casual, academic, storytelling)
            language: Target language for the transcript
            
        Returns:
            List of dictionaries with slide_number and transcript
        """
        logger.info(f"Generating transcripts for {len(images)} slides in a single batch")
        
        try:
            # Convert all images to base64
            base64_images = []
            for image in images:
                base64_images.append(self._image_to_base64(image))
            
            # Generate all transcripts in one call
            transcripts_text = await self._generate_batch_transcripts(
                base64_images=base64_images,
                total_slides=len(images),
                context=context,
                style=style,
                language=language
            )
            
            # Parse the response into individual transcripts
            transcripts = self._parse_batch_response(transcripts_text, len(images))
            
            return transcripts
            
        except Exception as e:
            logger.error(f"Error generating batch transcripts: {e}")
            # Fallback to individual generation if batch fails
            return await self._generate_individual_transcripts(
                images, context, style, language
            )
    
    @retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(3))
    async def _generate_single_transcript(
        self,
        image: Union[str, Path, Image.Image],
        slide_number: int,
        total_slides: int,
        context: Optional[str],
        style: str,
        language: str
    ) -> str:
        """Generate transcript for a single slide"""
        
        # Convert image to base64
        base64_image = self._image_to_base64(image)
        
        # Prepare system prompt
        system_prompt = self._get_system_prompt(style, language)
        
        # Prepare user prompt
        user_prompt = self._get_user_prompt(
            slide_number=slide_number,
            total_slides=total_slides,
            context=context,
            language=language
        )
        
        # Call OpenAI API
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                            "quality": "low"
                        }
                    ]
                }
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature
        )
        
        return response.choices[0].message.content.strip()
    
    @retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(3))
    async def _generate_batch_transcripts(
        self,
        base64_images: List[str],
        total_slides: int,
        context: Optional[str],
        style: str,
        language: str
    ) -> str:
        """Generate transcripts for all slides in a single API call"""
        
        # Prepare system prompt
        system_prompt = self._get_batch_system_prompt(style, language)
        
        # Prepare images content
        image_contents = []
        for i, base64_image in enumerate(base64_images, 1):
            image_contents.append({
                "type": "text",
                "text": f"[第{i}页]" if language == "zh-CN" else f"[Slide {i}]"
            })
            image_contents.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            })
        
        # Prepare user prompt
        user_prompt = self._get_batch_user_prompt(
            total_slides=total_slides,
            context=context,
            language=language
        )
        
        # Add user prompt at the beginning
        all_contents = [{"type": "text", "text": user_prompt}] + image_contents
        
        # Call OpenAI API
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": all_contents}
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature
        )
        
        return response.choices[0].message.content.strip()
    
    async def _generate_individual_transcripts(
        self,
        images: List[Union[str, Path, Image.Image]],
        context: Optional[str],
        style: str,
        language: str
    ) -> List[Dict[str, str]]:
        """Fallback method to generate transcripts individually"""
        transcripts = []
        
        for i, image in enumerate(images, 1):
            logger.info(f"Generating transcript for slide {i}/{len(images)}")
            
            try:
                transcript = await self._generate_single_transcript(
                    image=image,
                    slide_number=i,
                    total_slides=len(images),
                    context=context,
                    style=style,
                    language=language
                )
                
                transcripts.append({
                    "slide_number": i,
                    "transcript": transcript
                })
                
            except Exception as e:
                logger.error(f"Error generating transcript for slide {i}: {e}")
                transcripts.append({
                    "slide_number": i,
                    "transcript": f"[错误：无法生成第{i}页的讲稿]"
                })
                
        return transcripts
    
    def _image_to_base64(self, image: Union[str, Path, Image.Image]) -> str:
        """Convert image to base64 string"""
        if isinstance(image, str) and image.startswith("data:"):
            # Already base64
            return image.split(",")[1]
            
        if isinstance(image, (str, Path)):
            # Load from file
            with open(image, "rb") as f:
                return base64.b64encode(f.read()).decode()
                
        if isinstance(image, Image.Image):
            # Convert PIL Image
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG")
            return base64.b64encode(buffered.getvalue()).decode()
            
        raise ValueError(f"Unsupported image type: {type(image)}")
    
    def _get_system_prompt(self, style: str, language: str) -> str:
        """Get system prompt based on style and language"""
        
        style_prompts = {
            "professional": "你是一位专业的演讲者，擅长清晰、简洁地传达信息。",
            "casual": "你是一位轻松友好的演讲者，喜欢用通俗易懂的语言。",
            "academic": "你是一位学术演讲者，注重准确性和深度。",
            "storytelling": "你是一位善于讲故事的演讲者，擅长用生动的叙述吸引听众。"
        }
        
        base_prompt = style_prompts.get(style, style_prompts["professional"])
        
        if language == "zh-CN":
            return f"""{base_prompt}
你需要根据PPT页面的内容生成相应的演讲稿。
要求：
1. 语言流畅自然，适合口语表达
2. 内容准确，不要编造信息
3. 适当展开，但不要过于冗长
4. 如果是标题页，简要介绍主题
5. 如果有图表，解释其含义
6. 保持与整体演讲的连贯性"""
        else:
            return f"""{base_prompt}
You need to generate a speech script based on the PPT slide content.
Requirements:
1. Use natural, fluent language suitable for speaking
2. Be accurate, don't make up information
3. Elaborate appropriately but don't be too verbose
4. For title slides, briefly introduce the topic
5. For charts/diagrams, explain their meaning
6. Maintain coherence with the overall presentation"""
    
    def _get_user_prompt(
        self,
        slide_number: int,
        total_slides: int,
        context: Optional[str],
        language: str
    ) -> str:
        """Get user prompt for specific slide"""
        
        if language == "zh-CN":
            prompt = f"这是第{slide_number}页，共{total_slides}页。"
            
            if context:
                prompt += f"\n演讲背景：{context}"
                
            prompt += "\n请为这一页生成合适的演讲稿。"
            
        else:
            prompt = f"This is slide {slide_number} of {total_slides}."
            
            if context:
                prompt += f"\nPresentation context: {context}"
                
            prompt += "\nPlease generate an appropriate speech script for this slide."
            
        return prompt
    
    def _get_batch_system_prompt(self, style: str, language: str) -> str:
        """Get system prompt for batch processing"""
        
        style_prompts = {
            "professional": "你是一位专业的演讲者，擅长清晰、简洁地传达信息。",
            "casual": "你是一位轻松友好的演讲者，喜欢用通俗易懂的语言。",
            "academic": "你是一位学术演讲者，注重准确性和深度。",
            "storytelling": "你是一位善于讲故事的演讲者，擅长用生动的叙述吸引听众。"
        }
        
        base_prompt = style_prompts.get(style, style_prompts["professional"])
        
        if language == "zh-CN":
            return f"""{base_prompt}
你需要根据提供的多页PPT内容，为每一页生成相应的演讲稿。

要求：
1. 为每一页单独生成演讲稿
2. 使用JSON格式返回，格式为：[{{"slide_number": 1, "transcript": "演讲稿内容"}}, ...]
3. 语言流畅自然，适合口语表达
4. 内容准确，不要编造信息
5. 适当展开，但不要过于冗长
6. 保持整体演讲的连贯性和逻辑性
7. 注意前后页面的内容衔接"""
        else:
            return f"""{base_prompt}
You need to generate speech scripts for multiple PPT slides.

Requirements:
1. Generate a separate script for each slide
2. Return in JSON format: [{{"slide_number": 1, "transcript": "speech content"}}, ...]
3. Use natural, fluent language suitable for speaking
4. Be accurate, don't make up information
5. Elaborate appropriately but don't be too verbose
6. Maintain coherence and logic throughout the presentation
7. Ensure smooth transitions between slides"""
    
    def _get_batch_user_prompt(
        self,
        total_slides: int,
        context: Optional[str],
        language: str
    ) -> str:
        """Get user prompt for batch processing"""
        
        if language == "zh-CN":
            prompt = f"以下是{total_slides}页PPT的内容。"
            
            if context:
                prompt += f"\n演讲背景：{context}"
                
            prompt += "\n请为每一页生成合适的演讲稿，以JSON格式返回。"
            
        else:
            prompt = f"Here are {total_slides} PPT slides."
            
            if context:
                prompt += f"\nPresentation context: {context}"
                
            prompt += "\nPlease generate appropriate speech scripts for each slide and return in JSON format."
            
        return prompt
    
    def _parse_batch_response(self, response_text: str, expected_count: int) -> List[Dict[str, str]]:
        """Parse the batch response into individual transcripts"""
        try:
            # Try to parse as JSON
            transcripts = json.loads(response_text)
            
            # Validate the response
            if not isinstance(transcripts, list):
                raise ValueError("Response is not a list")
            
            # Ensure we have the right structure
            validated_transcripts = []
            for item in transcripts:
                if isinstance(item, dict) and "slide_number" in item and "transcript" in item:
                    validated_transcripts.append({
                        "slide_number": item["slide_number"],
                        "transcript": item["transcript"]
                    })
            
            # If we got fewer transcripts than expected, pad with error messages
            while len(validated_transcripts) < expected_count:
                slide_num = len(validated_transcripts) + 1
                validated_transcripts.append({
                    "slide_number": slide_num,
                    "transcript": f"[错误：未能生成第{slide_num}页的讲稿]"
                })
            
            return validated_transcripts[:expected_count]
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse batch response: {e}")
            logger.debug(f"Response text: {response_text[:500]}...")
            
            # Fallback: try to extract content manually
            transcripts = []
            
            # Try to split by slide markers
            if "第1页" in response_text or "Slide 1" in response_text:
                # Simple parsing based on slide markers
                for i in range(1, expected_count + 1):
                    marker = f"第{i}页" if "第1页" in response_text else f"Slide {i}"
                    next_marker = f"第{i+1}页" if "第1页" in response_text else f"Slide {i+1}"
                    
                    start = response_text.find(marker)
                    if start != -1:
                        end = response_text.find(next_marker, start)
                        content = response_text[start:end] if end != -1 else response_text[start:]
                        # Clean up the content
                        content = content.replace(marker, "").strip()
                        content = content.split("\n")[0].strip() if "\n" in content else content
                        
                        transcripts.append({
                            "slide_number": i,
                            "transcript": content[:500]  # Limit length
                        })
                    else:
                        transcripts.append({
                            "slide_number": i,
                            "transcript": f"[错误：未能解析第{i}页的讲稿]"
                        })
            else:
                # Complete fallback
                for i in range(1, expected_count + 1):
                    transcripts.append({
                        "slide_number": i,
                        "transcript": "[错误：批量生成失败，请尝试单独生成]"
                    })
            
            return transcripts
    
    def save_transcripts(
        self,
        transcripts: List[Dict[str, str]],
        output_path: Union[str, Path],
        format: str = "json"
    ):
        """
        Save transcripts to file
        
        Args:
            transcripts: List of transcript dictionaries
            output_path: Output file path
            format: Output format (json, txt, md)
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if format == "json":
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(transcripts, f, ensure_ascii=False, indent=2)
                
        elif format == "txt":
            with open(output_path, "w", encoding="utf-8") as f:
                for item in transcripts:
                    f.write(f"=== 第{item['slide_number']}页 ===\n")
                    f.write(f"{item['transcript']}\n\n")
                    
        elif format == "md":
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("# PPT演讲稿\n\n")
                for item in transcripts:
                    f.write(f"## 第{item['slide_number']}页\n\n")
                    f.write(f"{item['transcript']}\n\n")
                    
        else:
            raise ValueError(f"Unsupported format: {format}")
            
        logger.info(f"Saved transcripts to {output_path}")
    
    async def generate_from_ppt(
        self,
        ppt_path: Union[str, Path],
        output_path: Optional[Union[str, Path]] = None,
        context: Optional[str] = None,
        style: str = "professional",
        language: str = "zh-CN",
        format: str = "json"
    ) -> List[Dict[str, str]]:
        """
        Generate transcripts directly from PPT file
        
        Args:
            ppt_path: Path to PPT/PPTX file
            output_path: Optional path to save transcripts
            context: Additional context
            style: Speaking style
            language: Target language
            format: Output format if saving
            
        Returns:
            List of transcript dictionaries
        """
        from ..ppt_parser import PPTParser
        
        # Parse PPT to images
        parser = PPTParser()
        images = parser.parse_to_pil_images(ppt_path)
        
        # Generate transcripts
        transcripts = await self.generate_transcript(
            images=images,
            context=context,
            style=style,
            language=language
        )
        
        # Save if output path provided
        if output_path:
            self.save_transcripts(transcripts, output_path, format)
            
        return transcripts
    
    # Synchronous wrapper methods for backwards compatibility
    def generate_transcript_sync(self, *args, **kwargs):
        """Synchronous wrapper for generate_transcript"""
        return asyncio.run(self.generate_transcript(*args, **kwargs))
    
    def generate_from_ppt_sync(self, *args, **kwargs):
        """Synchronous wrapper for generate_from_ppt"""
        return asyncio.run(self.generate_from_ppt(*args, **kwargs))