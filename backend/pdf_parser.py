import fitz  # PyMuPDF
import re

def extract_pdf_data(pdf_bytes: bytes) -> list:
    """
    Extracts text blocks from the PDF bytes.
    Returns a list of dicts: [{"text": str, "page": int, "rect": [x0, y0, x1, y1]}]
    Filters out typical headers, footers, page numbers.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    extracted_blocks = []
    
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_num = page_idx + 1
        width = page.rect.width
        height = page.rect.height
        
        # We define header/footer boundaries (approx 10% of height from top/bottom)
        # and ignore blocks completely inside these zones.
        top_margin = height * 0.08
        bottom_margin = height * 0.92
        
        # Get blocks of text
        # "blocks" format: (x0, y0, x1, y1, "text", block_no, block_type)
        blocks = page.get_text("blocks")
        
        for b in blocks:
            x0, y0, x1, y1, text, block_no, block_type = b
            
            # Skip image blocks
            if block_type != 0:
                continue
                
            clean_text = text.strip()
            if not clean_text:
                continue
                
            # Filter out headers and footers based on position
            # If the block is entirely above top_margin or below bottom_margin
            if y1 < top_margin or y0 > bottom_margin:
                # Also double-check if it looks like a page number or header to avoid false positives
                # e.g., "Page 1", "Page 1 of 10", "1", "CONFIDENTIAL"
                if re.match(r'^\d+$', clean_text) or \
                   re.match(r'^page\s+\d+(\s+of\s+\d+)?$', clean_text, re.IGNORECASE) or \
                   len(clean_text) < 30: # typically headers/footers are short
                    continue
            
            # Skip line numbers or standalone page numbers at bottom/top
            if re.match(r'^\d+$', clean_text) and (y0 > bottom_margin or y1 < top_margin):
                continue
                
            extracted_blocks.append({
                "text": clean_text,
                "page": page_num,
                "bbox": [x0, y0, x1, y1]
            })
            
    return extracted_blocks
