import fitz
import io
import re

def is_heading(text: str) -> bool:
    """Heuristic to determine if a text block is a heading based strictly on text matching."""
    clean_text = text.strip()
    if re.match(r'^(\d+\.)+\s+[A-Za-z]', clean_text) or re.match(r'^\d+\s+[A-Za-z]', clean_text):
        return True
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
    
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_num = page_idx + 1
            rect = page.rect
            height = rect.height
            width = rect.width
            
            top_margin = height * 0.08
            bottom_margin = height * 0.92
            

            text_lines = page.get_text("dict").get("blocks", [])
            if text_lines:
                for block in text_lines:
                    if block.get("type") != 0:
                        continue
                    for line_obj in block.get("lines", []):
                        text = "".join(span.get("text", "") for span in line_obj.get("spans", [])).strip()
                        bbox = line_obj.get("bbox", [0, 0, width, height])
                        top = bbox[1]
                        bottom = bbox[3]

                        if not text:
                            continue

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
                            "bbox": [bbox[0], top, bbox[2], bottom],
                            "heading": current_heading
                        })
            
           
            # PyMuPDF does not provide a direct high-level extract_tables API in the same way,
            # so we preserve only text blocks for now.
            # If table extraction is required, add a custom layout parser or use a dedicated tool.
                        
    return extracted_blocks
