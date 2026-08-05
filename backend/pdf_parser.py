import pdfplumber
import io
import re

def is_heading(text: str) -> bool:
    """Heuristic to determine if a text block is a heading based strictly on text matching."""
    clean_text = text.strip()
    # Numbered heading e.g., "1. Executive Summary" or "2.3. Overview"
    if re.match(r'^(\d+\.)+\s+[A-Za-z]', clean_text) or re.match(r'^\d+\s+[A-Za-z]', clean_text):
        return True
    # All caps, short
    if clean_text.isupper() and 3 < len(clean_text) < 100:
        return True
    return False

def format_table(table) -> str:
    """Formats a nested list table into a markdown string."""
    if not table: return ""
    lines = []
    for row in table:
        clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
        lines.append(" | ".join(clean_row))
    return "\n".join(lines)

def extract_pdf_data(pdf_bytes: bytes) -> list:
    """
    Extracts text blocks and tables from the PDF bytes and tags them with their heading.
    Returns a list of dicts: [{"text": str, "page": int, "bbox": [x0, y0, x1, y1], "heading": str}]
    """
    extracted_blocks = []
    current_heading = "Document Start"
    
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as doc:
        for page_idx, page in enumerate(doc.pages):
            page_num = page_idx + 1
            height = page.height
            width = page.width
            
            top_margin = height * 0.08
            bottom_margin = height * 0.92
            
            # 1. Extract Text Layout
            # We use extract_text_lines to get text blocks with bounding boxes
            text_lines = page.extract_text_lines()
            if text_lines:
                for line_obj in text_lines:
                    text = line_obj.get("text", "").strip()
                    top = line_obj.get("top", 0)
                    bottom = line_obj.get("bottom", height)
                    
                    if not text:
                        continue
                        
                    # Filter headers/footers
                    if bottom < top_margin or top > bottom_margin:
                        if re.match(r'^\d+$', text) or \
                           re.match(r'^page\s+\d+(\s+of\s+\d+)?$', text, re.IGNORECASE) or \
                           len(text) < 30:
                            continue
                            
                    if is_heading(text):
                        current_heading = text
                        
                    extracted_blocks.append({
                        "text": text,
                        "page": page_num,
                        "bbox": [line_obj.get("x0", 0), top, line_obj.get("x1", width), bottom],
                        "heading": current_heading
                    })
            
            # 2. Extract Tables
            # Extract tables exactly as they appear and treat each table as a special block.
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    table_str = format_table(table)
                    if table_str.strip():
                        extracted_blocks.append({
                            "text": table_str,
                            "page": page_num,
                            "bbox": [0, 0, width, height],
                            "heading": current_heading
                        })
                        
    return extracted_blocks
