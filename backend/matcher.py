import re
from rapidfuzz import fuzz, process
from normalizer import normalize_text

try:
    from sentence_transformers import SentenceTransformer
    import torch
    from torch.nn.functional import cosine_similarity
    
    semantic_model = SentenceTransformer('all-MiniLM-L6-v2')
except ImportError:
    semantic_model = None

def split_into_chunks(text: str, max_words: int = 30) -> list:
    """
    Splits text into smaller semantic chunks (sentences or small paragraphs).
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    
    for sentence in sentences:
        words = sentence.split()
        if not words:
            continue
        if len(words) > max_words:
            for i in range(0, len(words), max_words):
                chunk = " ".join(words[i:i + max_words])
                if chunk.strip():
                    chunks.append(chunk.strip())
        else:
            chunks.append(sentence.strip())
            
    return chunks

def find_anchor_heading(ui_text: str, pdf_blocks: list) -> str:
    """Finds the best matching heading in the PDF heading tree using the first line of UI text."""
    first_line = ui_text.split('\n')[0].strip()
    if not first_line:
        return "Document Start"
        
    norm_first_line = normalize_text(first_line)
    
    # Get all unique headings from PDF blocks
    headings = list(set(b.get("heading", "Document Start") for b in pdf_blocks))
    norm_headings = [normalize_text(h) for h in headings]
    
    # Try exact match first
    if norm_first_line in norm_headings:
        idx = norm_headings.index(norm_first_line)
        return headings[idx]
        
    # Fallback to fuzzy match
    if norm_headings:
        result = process.extractOne(
            norm_first_line,
            norm_headings,
            scorer=fuzz.partial_ratio,
            score_cutoff=90.0
        )
        if result:
            return headings[result[2]]
            
    return "Document Start"

def extract_nested_headings(ui_text: str) -> list:
    """Splits UI text into nested sub-blocks if further numbered headings are found."""
    # Matches numbered headings e.g. "2.3 Executive Summary" at start of line
    pattern = r'^(?:\d+\.)+\s+[A-Za-z].*$'
    lines = ui_text.split('\n')
    
    blocks = []
    current_heading = None
    current_body = []
    
    for line in lines:
        if re.match(pattern, line.strip()):
            if current_body:
                blocks.append({"heading": current_heading, "text": "\n".join(current_body)})
            current_heading = line.strip()
            current_body = [line]
        else:
            current_body.append(line)
            
    if current_body:
        blocks.append({"heading": current_heading, "text": "\n".join(current_body)})
        
    # If no nested headings found, just return one block
    if not blocks:
        blocks.append({"heading": None, "text": ui_text})
        
    return blocks

def match_section(section_name: str, ui_text: str, pdf_blocks: list) -> dict:
    """
    Validates that the ui_text for a section exists in the PDF blocks.
    Uses heading-anchored validation and semantic matching for Metadata/Indication.
    """
    norm_ui_text = normalize_text(ui_text)
    
    is_none_or_na = ui_text.strip().lower() in [
        "none", "n/a", "na", "none or n/a", "none or na", "not applicable", 
        "no data available for this section"
    ]
    is_date_field = "date" in section_name.lower()
    is_therapeutic_areas = section_name == "Therapeutic Areas"
    
    if (is_date_field or is_therapeutic_areas) and (not norm_ui_text or is_none_or_na):
        return {
            "section": section_name,
            "similarity": 0.0,
            "status": "FAIL",
            "matched_text": [],
            "missing_text": [f"{section_name} not retrieved, not addressed, or contains no data/placeholder"],
            "pdf_pages": [],
            "skipped": False
        }
        
    if not norm_ui_text or is_none_or_na:
        return {
            "section": section_name,
            "similarity": None,
            "status": "NULL",
            "matched_text": [],
            "missing_text": [ui_text.strip() if ui_text.strip() else "No data provided in UI"],
            "pdf_pages": [],
            "skipped": False
        }
        
    is_semantic = section_name in ["Metadata", "Indication"]
    
    # Handle nested headings within UI text
    ui_sub_blocks = extract_nested_headings(ui_text)
    
    matched_chunks = []
    missing_chunks = []
    matched_pages = set()
    
    for sub_block in ui_sub_blocks:
        block_text = sub_block["text"]
        
        # Determine anchor heading for this block
        if sub_block["heading"]:
            anchor_heading = find_anchor_heading(sub_block["heading"], pdf_blocks)
        else:
            anchor_heading = find_anchor_heading(block_text, pdf_blocks)
            
        # Filter PDF blocks to only those under the anchor heading
        anchored_pdf_blocks = [b for b in pdf_blocks if b.get("heading") == anchor_heading]
        # Fallback to all if anchor not found
        if not anchored_pdf_blocks:
            anchored_pdf_blocks = pdf_blocks
            
        ui_chunks = split_into_chunks(block_text)
        
        if is_semantic and semantic_model:
            # Semantic Matching via SentenceTransformers
            anchored_texts = [b["text"] for b in anchored_pdf_blocks if b.get("text")]
            if not anchored_texts:
                missing_chunks.extend(ui_chunks)
                continue
                
            pdf_embeddings = semantic_model.encode(anchored_texts, convert_to_tensor=True)
            
            for chunk in ui_chunks:
                chunk_emb = semantic_model.encode([chunk], convert_to_tensor=True)
                cosine_scores = cosine_similarity(chunk_emb, pdf_embeddings)
                
                max_score = torch.max(cosine_scores).item()
                if max_score > 0.75: # Semantic Threshold
                    matched_chunks.append(chunk)
                    # Approx page finding
                    best_idx = torch.argmax(cosine_scores).item()
                    matched_pages.add(anchored_pdf_blocks[best_idx].get("page", 1))
                else:
                    missing_chunks.append(chunk)
                    
        else:
            # Literal / Rapidfuzz Matching
            norm_pdf_blocks = []
            choices = []
            for block in anchored_pdf_blocks:
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
                
                for idx, block_text_val in enumerate(choices):
                    if norm_chunk in block_text_val:
                        found = True
                        best_page = norm_pdf_blocks[idx].get("page", 1)
                        break
                        
                if not found and choices:
                    result = process.extractOne(
                        norm_chunk, 
                        choices, 
                        scorer=fuzz.partial_ratio, 
                        score_cutoff=98.0
                    )
                    if result:
                        best_page = norm_pdf_blocks[result[2]].get("page", 1)
                        found = True
                        
                if found:
                    matched_chunks.append(chunk)
                    if best_page:
                        matched_pages.add(best_page)
                else:
                    missing_chunks.append(chunk)
                    
    total_chunks = len(matched_chunks) + len(missing_chunks)
    matched_count = len(matched_chunks)
    
    similarity = (matched_count / total_chunks * 100.0) if total_chunks > 0 else 100.0
    
    if similarity >= 85.0:
        status = "PASS"
    elif similarity >= 60.0:
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
