import os
import time
import fitz
import logging
from .models import ExtractionResult
from .extractors import extract_toc_from_pages, extract_toc_from_bookmarks, format_hierarchical_numbers

logger = logging.getLogger("OutlineMiner")

def process_pdf(pdf_path: str, root_folder: str) -> ExtractionResult:
    """
    Executes the advanced Regex layout extraction pipeline on a single PDF.
    """
    start_time = time.time()
    pdf_name = os.path.basename(pdf_path)
    relative_path = os.path.relpath(pdf_path, root_folder)
    
    result = ExtractionResult(
        pdf_name=pdf_name,
        relative_path=relative_path,
        status="Failed",
        source="None",
        confidence=0,
        processing_time=0.0
    )
    
    try:
        doc = fitz.open(pdf_path)
        
        # Priority 1: Advanced Regex Layout Parsing for Printed TOC
        toc_lines = extract_toc_from_pages(doc)
        source = "Printed TOC (Regex Layout)"
        
        # Priority 2: Fallback to Bookmarks if printed TOC is missing or too short
        if not toc_lines or len(toc_lines) < 5:
            toc_lines = extract_toc_from_bookmarks(doc)
            source = "Bookmarks (Cleaned)"
            
        # Priority 3: Heuristic Heading Detection Fallback
        if not toc_lines or len(toc_lines) < 5:
            from .extractors import generate_toc_from_headings
            toc_lines = generate_toc_from_headings(doc)
            source = "Generated TOC (Heuristic + Regex Format)"
            
        if toc_lines:
            # Format numbers intelligently
            toc_lines = format_hierarchical_numbers(toc_lines)
            
            result.status = "Success"
            result.source = source
            result.confidence = 100
            result.raw_text = "\n".join(toc_lines)
            result.processing_time = time.time() - start_time
            doc.close()
            return result

        # Final fallback if nothing found
        result.status = "Failed"
        result.source = "None"
        result.confidence = 0
        result.error_message = "No Printed TOC or Bookmarks found."
        
        doc.close()
    except Exception as e:
        logger.error(f"Error processing {pdf_name}: {e}")
        result.status = "Failed"
        result.error_message = str(e)
        
    result.processing_time = time.time() - start_time
    return result
