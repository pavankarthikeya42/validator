import fitz
import re

def is_heading(text: str) -> bool:
    """Heuristic to determine if a text block is a heading based strictly on text matching."""
    clean_text = text.strip()
    if re.match(r'^(\d+\.)+\s+[A-Za-z]', clean_text) or re.match(r'^\d+\s+[A-Za-z]', clean_text):
        return True
    if clean_text.isupper() and 3 < len(clean_text) < 100:
        return True
    return False

def extract_pdf_data(pdf_bytes: bytes) -> list:
    """
    Extracts text blocks and tables from the PDF bytes and tags them with their heading.
    Returns a list of dicts: [{"text": str, "page": int, "bbox": [x0, y0, x1, y1], "heading": str}]
    """
    extracted_blocks = []
    current_heading = "Document Start"
    
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_idx, page in enumerate(doc):
            page_num = page_idx + 1
            blocks = page.get_text("blocks")
            
            # blocks is a list of tuples: (x0, y0, x1, y1, "lines in block", block_no, block_type)
            # block_type 0 is text, 1 is image.
            
            for b in blocks:
                # Ignore image blocks
                if len(b) >= 7 and b[6] != 0:
                    continue
                    
                x0, y0, x1, y1, text, block_no, block_type = b[:7]
                text = text.strip()
                if not text:
                    continue
                    
                # Exclude common pagination like "Page 1 of 5" or solitary numbers
                if re.match(r'^\d+$', text) or \
                   re.match(r'^page\s+\d+(\s+of\s+\d+)?$', text, re.IGNORECASE):
                    continue
                    
                if is_heading(text):
                    current_heading = text
                    
                extracted_blocks.append({
                    "text": text,
                    "page": page_num,
                    "bbox": [x0, y0, x1, y1],
                    "heading": current_heading
                })
                
            # Extract tables to preserve structural integrity for fuzzy matching
            try:
                tabs = page.find_tables()
                if hasattr(tabs, 'tables') and tabs.tables:
                    for tab in tabs.tables:
                        table_list = tab.extract()
                        if not table_list: continue
                        
                        table_str = ""
                        for row in table_list:
                            if not row: continue
                            clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                            table_str += " | ".join(clean_row) + "\n"
                            
                        if table_str.strip():
                            extracted_blocks.append({
                                "text": table_str.strip(),
                                "page": page_num,
                                "bbox": tab.bbox,
                                "heading": current_heading
                            })
            except Exception:
                pass
                        
    return extracted_blocks
