#!/usr/bin/env python
"""
Run PPT to Video Pipeline

Simple script to convert PPT to video using configuration files.
"""

import argparse
import asyncio
from pathlib import Path
from core.pipeline import PPTToVideoPipeline
from configs import PipelineConfig

async def main():
    parser = argparse.ArgumentParser(description='Convert PPT to Video')
    parser.add_argument('--ppt_file', help='Path to PPT/PPTX file')
    parser.add_argument('--config', default='configs/default.json', help='Configuration file path')
    parser.add_argument('--output', help='Output video path (optional)')
    parser.add_argument('--context', help='Presentation context (optional)')
    parser.add_argument('--max-slides', type=int, help='Maximum slides to process')
    
    # Voice cloning arguments
    parser.add_argument('--voice-clone', action='store_true', help='Enable voice cloning')
    parser.add_argument('--reference-audio', help='Path to reference audio file for voice cloning')
    parser.add_argument('--reference-text', help='Text content of the reference audio')
    
    args = parser.parse_args()
    
    # Load configuration
    print(f"Loading configuration from: {args.config}")
    config = PipelineConfig.load(args.config)
    
    # Override max_slides if specified
    if args.max_slides:
        config.max_slides = args.max_slides
    
    # Handle voice cloning arguments
    if args.voice_clone:
        config.use_voice_clone = True
        if args.reference_audio:
            config.reference_audio_path = args.reference_audio
        if args.reference_text:
            config.reference_text = args.reference_text
        
        # Validate voice cloning config
        if not config.reference_audio_path or not config.reference_text:
            print("Error: Voice cloning requires both --reference-audio and --reference-text")
            return
    
    # Validate configuration
    if not config.validate():
        print("Configuration validation failed!")
        return
    
    # Create pipeline
    pipeline = PPTToVideoPipeline(config)
    
    # Process PPT
    print(f"\nProcessing: {args.ppt_file}")
    print(f"Output directory: {config.output_dir}")
    print(f"Video resolution: {config.video_resolution[0]}x{config.video_resolution[1]}")
    
    if config.use_voice_clone:
        print(f"Voice: Cloned from {config.reference_audio_path}")
    else:
        print(f"Voice: {config.voice_id}")
    
    print(f"Min transcript length: {config.min_transcript_length} characters")
    
    if config.max_slides:
        print(f"Processing first {config.max_slides} slides only")
    
    print("\nStarting conversion...\n")
    
    try:
        video_path = await pipeline.process(
            ppt_path=args.ppt_file,
            output_video_path=args.output,
            presentation_context=args.context,
            progress_callback=lambda p, msg: print(f"[{p*100:5.1f}%] {msg}")
        )
        
        print(f"\n✓ Success! Video created: {video_path}")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Example usage:
    # python run_pipeline.py presentation.pptx
    # python run_pipeline.py presentation.pptx --config configs/high_quality.json
    # python run_pipeline.py presentation.pptx --config configs/english.json --output my_video.mp4
    # python run_pipeline.py presentation.pptx --max-slides 5 --context "AI技术分享"
    
    # Voice cloning examples:
    # python run_pipeline.py presentation.pptx --voice-clone --reference-audio voice.wav --reference-text "参考音频文本"
    # python run_pipeline.py presentation.pptx --config configs/voice_clone.json
    
    asyncio.run(main())