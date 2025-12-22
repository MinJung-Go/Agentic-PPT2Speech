import json
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Union
import logging
from datetime import datetime
import shutil

from ..ppt_parser import PPTParser
from ..transcript_generator import TranscriptGenerator
from ..speech_generator import SpeechSynthesisPlugin
from ..video_generator import VideoSynthesizer

# Import from project root configs
from configs import PipelineConfig

logger = logging.getLogger(__name__)


class PPTToVideoPipeline:
    """Complete pipeline from PPT to Video with AI-generated narration"""
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """
        Initialize the pipeline
        
        Args:
            config: Pipeline configuration
        """
        self.config = config or PipelineConfig()
        self.output_dir = Path(self.config.output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Initialize components
        self.ppt_parser = PPTParser(dpi=self.config.ppt_dpi)
        self.transcript_generator = TranscriptGenerator(
            model=self.config.ai_model,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature
        )
        self.speech_synthesizer = SpeechSynthesisPlugin()
        self.video_synthesizer = VideoSynthesizer(
            fps=self.config.video_fps,
            resolution=self.config.video_resolution,
            transition_duration=self.config.transition_duration
        )
        
        # Create subdirectories
        self.images_dir = self.output_dir / "images"
        self.transcripts_dir = self.output_dir / "transcripts"
        self.audio_dir = self.output_dir / "audio"
        
        if self.config.save_intermediates:
            self.images_dir.mkdir(exist_ok=True)
            self.transcripts_dir.mkdir(exist_ok=True)
            self.audio_dir.mkdir(exist_ok=True)
    
    async def process(
        self,
        ppt_path: Union[str, Path],
        output_video_path: Optional[Union[str, Path]] = None,
        presentation_context: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> Path:
        """
        Process PPT file to create video
        
        Args:
            ppt_path: Path to PPT/PPTX file
            output_video_path: Output video path (optional)
            presentation_context: Context about the presentation
            progress_callback: Callback for progress updates
            
        Returns:
            Path to generated video
        """
        ppt_path = Path(ppt_path)
        if not ppt_path.exists():
            raise FileNotFoundError(f"PPT file not found: {ppt_path}")
        
        if output_video_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_video_path = self.output_dir / f"{ppt_path.stem}_video_{timestamp}.mp4"
        else:
            output_video_path = Path(output_video_path)
        
        logger.info(f"Starting PPT to Video conversion: {ppt_path}")
        
        try:
            # Step 1: Parse PPT
            if progress_callback:
                progress_callback(0.1, "Parsing PPT slides...")
            
            slide_images = self._parse_ppt(ppt_path)
            
            # Step 2: Generate transcripts
            if progress_callback:
                progress_callback(0.3, "Generating transcripts...")
            
            transcripts = await self._generate_transcripts(
                slide_images, 
                presentation_context
            )
            
            # Step 3: Generate speech
            if progress_callback:
                progress_callback(0.6, "Generating speech audio...")
            
            audio_files = self._generate_speech(transcripts)
            
            # Step 4: Create video
            if progress_callback:
                progress_callback(0.8, "Creating video...")
            
            video_path = self._create_video(
                slide_images[:len(audio_files)], 
                audio_files,
                output_video_path
            )
            
            if progress_callback:
                progress_callback(1.0, "Complete!")
            
            # Clean up if not saving intermediates
            if not self.config.save_intermediates:
                self._cleanup_intermediates()
            
            logger.info(f"Video created successfully: {video_path}")
            return video_path
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            raise
    
    def _parse_ppt(self, ppt_path: Path) -> List:
        """Parse PPT to images"""
        logger.info("Parsing PPT to images...")
        
        slide_images = self.ppt_parser.parse_to_pil_images(ppt_path)
        
        # Limit slides if configured
        if self.config.max_slides:
            slide_images = slide_images[:self.config.max_slides]
        
        # Save images if configured
        if self.config.save_intermediates:
            for i, img in enumerate(slide_images):
                img_path = self.images_dir / f"slide_{i+1:03d}.png"
                img.save(img_path)
                logger.debug(f"Saved slide {i+1} to {img_path}")
        
        logger.info(f"Parsed {len(slide_images)} slides")
        return slide_images
    
    async def _generate_transcripts(
        self,
        slide_images: List,
        presentation_context: Optional[str]
    ) -> List[Dict[str, str]]:
        """Generate transcripts with detailed content"""
        logger.info("Generating transcripts...")
        
        # Enhance context with instructions for longer transcripts
        enhanced_context = self._get_enhanced_context(presentation_context)
        
        # Generate transcripts in batches
        all_transcripts = []
        batch_size = self.config.batch_size
        
        for batch_start in range(0, len(slide_images), batch_size):
            batch_images = slide_images[batch_start:batch_start + batch_size]
            batch_num = batch_start // batch_size + 1
            total_batches = (len(slide_images) + batch_size - 1) // batch_size
            
            logger.info(f"Processing batch {batch_num}/{total_batches}")
            
            # Build context with previous transcripts
            batch_context = self._build_batch_context(
                enhanced_context, 
                all_transcripts, 
                batch_start,
                len(slide_images),
                batch_start + len(batch_images)
            )
            
            try:
                batch_transcripts = await self.transcript_generator.generate_transcript(
                    images=batch_images,
                    context=batch_context,
                    style=self.config.transcript_style,
                    language=self.config.transcript_language
                )
                
                # Ensure transcripts are long enough
                for j, transcript in enumerate(batch_transcripts):
                    slide_num = batch_start + j + 1
                    if len(transcript['transcript']) < self.config.min_transcript_length:
                        logger.warning(f"Transcript for slide {slide_num} is too short, enhancing...")
                        transcript['transcript'] = self._enhance_transcript(
                            transcript['transcript'],
                            slide_num,
                            len(slide_images)
                        )
                
                all_transcripts.extend(batch_transcripts)
                
            except Exception as e:
                logger.error(f"Error generating transcripts for batch {batch_num}: {e}")
                # Use fallback transcripts
                for j in range(len(batch_images)):
                    slide_num = batch_start + j + 1
                    all_transcripts.append({
                        'slide_number': slide_num,
                        'transcript': self._get_fallback_transcript(slide_num, len(slide_images))
                    })
        
        # Save transcripts if configured
        if self.config.save_intermediates:
            transcript_file = self.transcripts_dir / "transcripts.json"
            with open(transcript_file, 'w', encoding='utf-8') as f:
                json.dump(all_transcripts, f, ensure_ascii=False, indent=2)
            
            # Also save as markdown
            md_file = self.transcripts_dir / "transcripts.md"
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write("# 演讲稿\n\n")
                for t in all_transcripts:
                    f.write(f"## 第{t['slide_number']}页\n\n")
                    f.write(f"{t['transcript']}\n\n")
        
        logger.info(f"Generated {len(all_transcripts)} transcripts")
        return all_transcripts
    
    def _generate_speech(self, transcripts: List[Dict[str, str]]) -> List[Path]:
        """Generate speech audio files with optional voice cloning"""
        logger.info("Generating speech audio...")
        
        # Check voice cloning configuration
        if self.config.use_voice_clone:
            if not self.config.reference_audio_path or not self.config.reference_text:
                logger.warning("Voice cloning enabled but reference audio/text not provided")
                logger.warning("Falling back to preset voice")
                use_clone = False
            else:
                logger.info(f"Using voice cloning with reference: {self.config.reference_audio_path}")
                use_clone = True
        else:
            use_clone = False
        
        audio_files = []
        
        for i, transcript_data in enumerate(transcripts):
            slide_num = transcript_data['slide_number']
            logger.info(f"Generating audio for slide {slide_num}...")
            
            audio_path = self.audio_dir / f"audio_{slide_num:03d}.wav"
            
            try:
                if use_clone:
                    # Use voice cloning - DO NOT pass reference_id
                    self.speech_synthesizer.synthesize(
                        text=transcript_data['transcript'],
                        output_path=str(audio_path),
                        reference_audio_path=self.config.reference_audio_path,
                        reference_text=self.config.reference_text,
                        speed=self.config.speech_speed,
                        volume=self.config.speech_volume,
                        pitch=self.config.speech_pitch
                    )
                else:
                    # Use preset voice with reference_id
                    self.speech_synthesizer.synthesize(
                        text=transcript_data['transcript'],
                        output_path=str(audio_path),
                        reference_id=self.config.voice_id,
                        language=self.config.speech_language,
                        speed=self.config.speech_speed,
                        volume=self.config.speech_volume,
                        pitch=self.config.speech_pitch
                    )
                
                if audio_path.exists():
                    audio_files.append(audio_path)
                    logger.debug(f"Created audio: {audio_path}")
                else:
                    logger.error(f"Failed to create audio for slide {slide_num}")
                    
            except Exception as e:
                logger.error(f"Error generating audio for slide {slide_num}: {e}")
        
        logger.info(f"Generated {len(audio_files)} audio files")
        return audio_files
    
    def _create_video(
        self,
        slide_images: List,
        audio_files: List[Path],
        output_path: Path
    ) -> Path:
        """Create final video"""
        logger.info("Creating video...")
        
        return self.video_synthesizer.synthesize(
            images=slide_images,
            audio_files=audio_files,
            output_path=output_path,
            fade_in=self.config.fade_in,
            fade_out=self.config.fade_out,
            progress_callback=lambda p, msg: logger.info(f"Video synthesis: {msg} ({p*100:.1f}%)")
        )
    
    def _get_enhanced_context(self, base_context: Optional[str]) -> str:
        """Enhance context to generate longer transcripts"""
        context_parts = []
        
        if base_context:
            context_parts.append(base_context)
        
        context_parts.extend([
            "请为每一页PPT生成详细的演讲稿。",
            "每页的演讲稿应该：",
            "1. 至少阅读两分钟",
            "2. 详细解释页面上的所有要点",
            "3. 适当展开和补充相关信息",
            "4. 使用流畅自然的口语表达",
            "5. 包含适当的过渡语句连接前后内容",
            "6. 如果是标题页，要介绍演讲的背景和目的",
            "7. 如果有图表或数据，要详细解释其含义和重要性",
            "请确保演讲稿内容丰富、表达完整。"
        ])
        
        return "\n".join(context_parts)
    
    def _build_batch_context(
        self, 
        base_context: str, 
        previous_transcripts: List[Dict[str, str]], 
        current_batch_start: int,
        total_slides: int,
        current_batch_end: int
    ) -> str:
        """Build context for current batch including previous transcripts"""
        context_parts = [base_context]
        
        # Add position information
        context_parts.append(
            f"\n当前处理第{current_batch_start + 1}-{current_batch_end}页（共{total_slides}页）"
        )
        
        # Determine which part of presentation
        position_ratio = (current_batch_start + 1) / total_slides
        if position_ratio <= 0.3:
            context_parts.append("这是演讲的前期部分，请做好铺垫")
        elif position_ratio <= 0.7:
            context_parts.append("这是演讲的中间部分，请深入展开")
        else:
            context_parts.append("这是演讲的后期部分，请注意总结")
        
        if previous_transcripts:
            context_parts.append("\n=== 已生成的演讲稿概要 ===")
            
            # Include summary of previous transcripts
            # Limit to last 5 transcripts to avoid context being too long
            recent_transcripts = previous_transcripts[-5:] if len(previous_transcripts) > 5 else previous_transcripts
            
            for transcript in recent_transcripts:
                slide_num = transcript['slide_number']
                content = transcript['transcript']
                
                # Create a brief summary (first 100 characters)
                summary = content[:100] + "..." if len(content) > 100 else content
                context_parts.append(f"第{slide_num}页: {summary}")
            
            # Add continuation instruction
            context_parts.append(
                f"\n请继续生成演讲稿，保持连贯性。"
            )
        
        return "\n".join(context_parts)
    
    def _get_fallback_transcript(self, slide_num: int, total_slides: int) -> str:
        """Get fallback transcript for a slide"""
        if slide_num == 1:
            return """欢迎大家来到今天的技术分享会。我将为大家介绍本次演讲的主题内容。
这是一个非常有价值的话题，涉及到当前技术发展的重要方向。
在接下来的时间里，我们将一起探讨相关的概念、方法和实践经验。
希望通过这次分享，能够为大家带来新的思考和启发。"""
        
        elif slide_num == total_slides:
            return """这就是今天要分享的全部内容。通过前面的讲解，
我们系统地了解了相关的理论知识和实践方法。
希望这些内容能够帮助大家在实际工作中更好地应用这些技术。
如果大家有任何疑问或想要深入讨论的地方，欢迎随时提出。
感谢大家的时间和关注，祝大家工作顺利！"""
        
        else:
            return f"""现在我们来看第{slide_num}页的内容。这一页展示了非常重要的概念和信息。
让我们仔细分析页面上的每个要点，理解它们之间的关联和意义。
这些内容与我们之前讨论的主题紧密相关，是整体知识框架中不可或缺的一部分。
通过深入理解这些概念，我们能够更好地把握技术的本质和应用方向。
请大家注意这里的关键信息，它们将在后续的内容中发挥重要作用。"""
    
    def _enhance_transcript(self, short_transcript: str, slide_num: int, total_slides: int) -> str:
        """Enhance a short transcript to meet minimum length requirement"""
        # If transcript is already long enough, return as is
        if len(short_transcript) >= self.config.min_transcript_length:
            return short_transcript
        
        # Calculate position in presentation
        position_ratio = slide_num / total_slides
        
        if slide_num == 1:
            # Opening slide
            enhancement = f"""
{short_transcript}

各位朋友，欢迎大家参加今天的分享。在开始之前，我想先简要介绍一下今天演讲的背景和目的。
我们将深入探讨这个主题的各个方面，从基础概念到实际应用，力求为大家提供全面而深入的理解。
在接下来的内容中，我会通过具体的案例和详细的分析，帮助大家更好地掌握相关知识。
让我们一起开始这段学习之旅。
"""
        elif slide_num == total_slides:
            # Closing slide
            enhancement = f"""
{short_transcript}

到这里，我们的分享就接近尾声了。让我们回顾一下今天讨论的主要内容。
通过这次演讲，我们深入了解了相关的理论基础和实践方法，
探讨了如何将这些知识应用到实际工作中，以及未来的发展方向。
希望今天的分享能够对大家有所启发，帮助大家在各自的领域取得更好的成果。
如果大家有任何问题或想进一步交流，请随时与我联系。
再次感谢大家的参与和支持！
"""
        elif position_ratio < 0.3:
            # Early slides - introduction and context
            enhancement = f"""
{short_transcript}

在这一部分，我们将建立对这个主题的基础理解。
这些概念虽然看似简单，但它们是理解后续内容的关键基础。
让我们仔细分析每个要点，确保大家都能够充分理解。
这将为我们后面的深入讨论打下坚实的基础。
请大家注意这些关键概念之间的联系，它们共同构成了我们理解这个领域的框架。
"""
        elif position_ratio < 0.7:
            # Middle slides - main content
            enhancement = f"""
{short_transcript}

现在让我们深入探讨这个话题的核心内容。
这一页展示的信息非常关键，它直接关系到我们如何理解和应用相关技术。
我想通过几个具体的例子来说明这些概念的实际意义。
大家可以看到，这里的每个要点都有其独特的价值和应用场景。
让我们逐一分析，看看它们如何相互配合，形成一个完整的解决方案。
这种系统性的理解对于我们掌握整体框架至关重要。
"""
        else:
            # Later slides - summary and implications
            enhancement = f"""
{short_transcript}

基于前面的讨论，我们现在可以看到更完整的图景。
这些内容不仅总结了我们之前探讨的要点，还指出了未来的发展方向。
让我们思考一下这些知识在实际应用中的意义。
通过将理论与实践相结合，我们能够更好地解决实际问题。
这里展示的方法和技巧，都是经过验证的最佳实践。
希望大家能够将这些内容应用到自己的工作中。
"""
        
        return enhancement.strip()
    
    def _cleanup_intermediates(self):
        """Clean up intermediate files"""
        logger.info("Cleaning up intermediate files...")
        
        for dir_path in [self.images_dir, self.transcripts_dir, self.audio_dir]:
            if dir_path.exists():
                shutil.rmtree(dir_path)
                
    def process_sync(
        self,
        ppt_path: Union[str, Path],
        output_video_path: Optional[Union[str, Path]] = None,
        presentation_context: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> Path:
        """Synchronous wrapper for process method"""
        return asyncio.run(self.process(
            ppt_path,
            output_video_path,
            presentation_context,
            progress_callback
        ))