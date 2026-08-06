import logging
import re
from typing import Tuple

logger = logging.getLogger("OutlineMiner")

def is_toc_heading(text: str) -> bool:
    clean = text.strip().lower()
    return clean in ["table of contents", "contents", "index"]

def extract_toc_via_ocr(pdf_path: str) -> Tuple[str, float]:
    """
    Stage 3: Converts PDF to images, runs PaddleOCR, and extracts raw TOC text.
    """
    try:
        from pdf2image import convert_from_path
        from paddleocr import PaddleOCR
        import numpy as np
    except ImportError as e:
        logger.error(f"OCR dependencies missing: {e}")
        return "", 0.0

    try:
        logger.info(f"Starting OCR fallback for {pdf_path}")
        images = convert_from_path(pdf_path, first_page=1, last_page=30)
        
        ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
        
        toc_start_page = -1
        pages_lines = []
        
        for i, img in enumerate(images):
            img_arr = np.array(img)
            result = ocr.ocr(img_arr, cls=True)
            
            page_lines = []
            if result and result[0]:
                for line in result[0]:
                    text = line[1][0]
                    page_lines.append(text)
            
            pages_lines.append(page_lines)
            
            if toc_start_page == -1:
                for t in page_lines:
                    if is_toc_heading(t):
                        toc_start_page = i
                        break
                        
        if toc_start_page == -1:
            return "", 0.0
            
        extracted_text = []
        end_page = min(toc_start_page + 5, len(pages_lines))
        
        for i in range(toc_start_page, end_page):
            lines = pages_lines[i]
            lines_with_numbers = sum(1 for l in lines if re.search(r'\d+\s*$', l.strip()))
            
            if i > toc_start_page and len(lines) > 10 and (lines_with_numbers / len(lines)) < 0.1:
                break
                
            extracted_text.append("\n".join(lines))
            
        return "\n".join(extracted_text), 70.0
        
    except Exception as e:
        logger.error(f"OCR Extraction failed: {e}")
        return "", 0.0
