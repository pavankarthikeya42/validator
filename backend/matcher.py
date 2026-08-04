from rapidfuzz import fuzz, process
from normalizer import normalize_text
import re

def split_into_chunks(text: str, max_words: int = 30) -> list:
    """
    Splits text into smaller semantic chunks (sentences or small paragraphs)
    to facilitate granular validation.
    """
    # Split by sentence boundaries, keeping separators
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    
    for sentence in sentences:
        words = sentence.split()
        if not words:
            continue
        # If a sentence is too long, chunk it further by word count
        if len(words) > max_words:
            for i in range(0, len(words), max_words):
                chunk = " ".join(words[i:i + max_words])
                if chunk.strip():
                    chunks.append(chunk.strip())
        else:
            chunks.append(sentence.strip())
            
    return chunks

def match_section(section_name: str, ui_text: str, pdf_blocks: list) -> dict:
    """
    Validates that the ui_text for a section exists in the PDF blocks.
    Splits ui_text into chunks and searches for each chunk in the PDF.
    """
    # Normalize inputs
    norm_ui_text = normalize_text(ui_text)
    
    # If the section is "Therapeutic Areas" and the value is none/na/empty, treat it as PASS (i.e. not needing to present/validate)
    is_none_or_na = ui_text.strip().lower() in ["none", "n/a", "na", "none or n/a", "none or na", "not applicable"]
    if not norm_ui_text or (section_name == "Therapeutic Areas" and is_none_or_na):
        return {
            "section": section_name,
            "similarity": 100.0,
            "status": "PASS",
            "matched_text": [],
            "missing_text": [],
            "pdf_pages": [],
            "skipped": True
        }
        
    # Split the original ui_text into readable chunks for tracking
    ui_chunks = split_into_chunks(ui_text)
    matched_chunks = []
    missing_chunks = []
    matched_pages = set()
    
    # Pre-normalize all PDF blocks to save time
    norm_pdf_blocks = []
    choices = []
    for block in pdf_blocks:
        norm_block_text = normalize_text(block["text"])
        if norm_block_text:
            norm_pdf_blocks.append(block)
            choices.append(norm_block_text)
            
    for chunk in ui_chunks:
        norm_chunk = normalize_text(chunk)
        if not norm_chunk:
            continue
            
        found = False
        best_page = None
        
        # 1. Fast exact search first: check if chunk is in any block
        for idx, block_text in enumerate(choices):
            if norm_chunk in block_text:
                found = True
                best_page = norm_pdf_blocks[idx]["page"]
                break
                
        # 2. Optimized fuzzy search fallback using RapidFuzz C++ extractOne
        if not found and choices:
            result = process.extractOne(
                norm_chunk, 
                choices, 
                scorer=fuzz.partial_ratio, 
                score_cutoff=95.0
            )
            if result:
                # result is (match_text, score, index)
                best_page = norm_pdf_blocks[result[2]]["page"]
                found = True
                
        if found:
            matched_chunks.append(chunk)
            matched_pages.add(best_page)
        else:
            missing_chunks.append(chunk)
            
    total_chunks = len(ui_chunks)
    matched_count = len(matched_chunks)
    
    similarity = (matched_count / total_chunks * 100.0) if total_chunks > 0 else 100.0
    
    if similarity >= 99.9:
        status = "PASS"
    elif similarity > 0.0:
        status = "PARTIAL"
    else:
        status = "FAIL"
        
    return {
        "section": section_name,
        "similarity": round(similarity, 2),
        "status": status,
        "matched_text": matched_chunks,
        "missing_text": missing_chunks,
        "pdf_pages": sorted(list(matched_pages)),
        "skipped": False
    }
