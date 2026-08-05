import fitz  # PyMuPDF
import re

def is_heading(text: str, size: float, is_bold: bool) -> bool:
    """Heuristic to determine if a text block is a heading."""
    clean_text = text.strip()
    # Numbered heading e.g., "1. Executive Summary" or "2.3. Overview"
    if re.match(r'^(\d+\.)+\s+[A-Za-z]', clean_text) or re.match(r'^\d+\s+[A-Za-z]', clean_text):
        return True
    # All caps, short, bold
    if clean_text.isupper() and 3 < len(clean_text) < 100:
        return True
    return False

def extract_pdf_data(pdf_bytes: bytes) -> list:
    """
    Extracts text blocks from the PDF bytes and tags them with their heading.
    Returns a list of dicts: [{"text": str, "page": int, "bbox": [x0, y0, x1, y1], "heading": str}]
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    extracted_blocks = []
    
    current_heading = "Document Start"
    
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_num = page_idx + 1
        height = page.rect.height
        
        top_margin = height * 0.08
        bottom_margin = height * 0.92
        
        dict_data = page.get_text("dict")
        
        for block in dict_data.get("blocks", []):
            if block.get("type") != 0:
                continue
                
            block_text = ""
            max_size = 0.0
            is_bold = False
            bbox = block.get("bbox", [0, 0, 0, 0])
            x0, y0, x1, y1 = bbox
            
            # Reconstruct text and get style info
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    block_text += span.get("text", "") + " "
                    size = span.get("size", 0.0)
                    if size > max_size:
                        max_size = size
                    flags = span.get("flags", 0)
                    if flags & 2**4: # bit 4 is bold in PyMuPDF
                        is_bold = True
                        
            clean_text = block_text.strip()
            if not clean_text:
                continue
                
            # Filter headers/footers
            if y1 < top_margin or y0 > bottom_margin:
                if re.match(r'^\d+$', clean_text) or \
                   re.match(r'^page\s+\d+(\s+of\s+\d+)?$', clean_text, re.IGNORECASE) or \
                   len(clean_text) < 30:
                    continue
                    
            if is_heading(clean_text, max_size, is_bold):
                current_heading = clean_text
                
            extracted_blocks.append({
                "text": clean_text,
                "page": page_num,
                "bbox": [x0, y0, x1, y1],
                "heading": current_heading
            })
            
    return extracted_blocks
