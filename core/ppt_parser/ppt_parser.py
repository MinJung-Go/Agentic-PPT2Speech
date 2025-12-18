from pathlib import Path
from typing import List, Optional, Union
import logging
from PIL import Image
import fitz  # PyMuPDF
import tempfile
import subprocess

logger = logging.getLogger(__name__)


class PPTParser:
    """PPT/PPTX parser that converts PowerPoint files to images"""
    
    def __init__(self, dpi: int = 200):
        """
        Initialize PPT Parser
        
        Args:
            dpi: DPI for image conversion (default: 200)
        """
        self.dpi = dpi
        
    def parse(
        self, 
        ppt_path: Union[str, Path], 
        output_dir: Union[str, Path],
        image_format: str = "png",
        prefix: str = "slide"
    ) -> List[Path]:
        """
        Parse PPT/PPTX file and convert each slide to an image
        
        Args:
            ppt_path: Path to PPT/PPTX file
            output_dir: Directory to save images
            image_format: Image format (png, jpg, jpeg)
            prefix: Prefix for image filenames
            
        Returns:
            List of paths to generated images
        """
        ppt_path = Path(ppt_path)
        output_dir = Path(output_dir)
        
        if not ppt_path.exists():
            raise FileNotFoundError(f"PPT file not found: {ppt_path}")
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Check file extension
        if ppt_path.suffix.lower() == '.pptx':
            return self._parse_pptx(ppt_path, output_dir, image_format, prefix)
        elif ppt_path.suffix.lower() == '.ppt':
            return self._parse_ppt(ppt_path, output_dir, image_format, prefix)
        else:
            raise ValueError(f"Unsupported file format: {ppt_path.suffix}")
            
    def _parse_pptx(
        self,
        pptx_path: Path,
        output_dir: Path,
        image_format: str,
        prefix: str
    ) -> List[Path]:
        """Parse PPTX file using python-pptx and convert to PDF then images"""
        try:
            # First convert PPTX to PDF using LibreOffice
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
                pdf_path = Path(tmp_pdf.name)
                
            # Convert PPTX to PDF
            self._convert_to_pdf(pptx_path, pdf_path)
            
            # Convert PDF to images
            images = self._pdf_to_images(pdf_path, output_dir, image_format, prefix)
            
            # Clean up temporary PDF
            pdf_path.unlink()
            
            return images
            
        except Exception as e:
            logger.error(f"Error parsing PPTX: {e}")
            raise
            
    def _parse_ppt(
        self,
        ppt_path: Path,
        output_dir: Path,
        image_format: str,
        prefix: str
    ) -> List[Path]:
        """Parse PPT file by converting to PDF first"""
        try:
            # Convert PPT to PDF using LibreOffice
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
                pdf_path = Path(tmp_pdf.name)
                
            self._convert_to_pdf(ppt_path, pdf_path)
            
            # Convert PDF to images
            images = self._pdf_to_images(pdf_path, output_dir, image_format, prefix)
            
            # Clean up temporary PDF
            pdf_path.unlink()
            
            return images
            
        except Exception as e:
            logger.error(f"Error parsing PPT: {e}")
            raise
            
    def _convert_to_pdf(self, input_path: Path, output_path: Path):
        """Convert PPT/PPTX to PDF using LibreOffice"""
        cmd = [
            'libreoffice',
            '--headless',
            '--convert-to', 'pdf',
            '--outdir', str(output_path.parent),
            str(input_path)
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # LibreOffice creates PDF with same name as input
            temp_pdf = output_path.parent / f"{input_path.stem}.pdf"
            if temp_pdf != output_path:
                temp_pdf.rename(output_path)
                
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to convert to PDF: {e.stderr}")
        except FileNotFoundError:
            raise Exception("LibreOffice not found. Please install it to convert PPT files.")
            
    def _pdf_to_images(
        self,
        pdf_path: Path,
        output_dir: Path,
        image_format: str,
        prefix: str
    ) -> List[Path]:
        """Convert PDF pages to images using PyMuPDF"""
        images = []
        
        try:
            pdf_document = fitz.open(str(pdf_path))
            
            for page_num in range(pdf_document.page_count):
                page = pdf_document[page_num]
                
                # Render page to image
                mat = fitz.Matrix(self.dpi/72, self.dpi/72)
                pix = page.get_pixmap(matrix=mat)
                
                # Save image
                image_path = output_dir / f"{prefix}_{page_num + 1:03d}.{image_format}"
                pix.save(str(image_path))
                
                images.append(image_path)
                logger.info(f"Saved slide {page_num + 1} as {image_path}")
                
            pdf_document.close()
            
        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}")
            raise
            
        return images
    
    def parse_to_pil_images(
        self,
        ppt_path: Union[str, Path]
    ) -> List[Image.Image]:
        """
        Parse PPT/PPTX and return PIL Image objects instead of saving to disk
        
        Args:
            ppt_path: Path to PPT/PPTX file
            
        Returns:
            List of PIL Image objects
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            image_paths = self.parse(ppt_path, tmp_dir)
            
            images = []
            for path in image_paths:
                img = Image.open(path)
                images.append(img.copy())  # Copy to keep in memory
                
            return images