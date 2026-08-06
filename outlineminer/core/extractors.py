import re
import fitz
from typing import List, Optional, Tuple
from collections import Counter
import logging

logger = logging.getLogger("OutlineMiner")

# Regex Patterns for TOC Start & End Boundaries
TOC_START_RE = re.compile(r'^\s*(table\s+of\s+contents|contents|index)\b', re.IGNORECASE)
STOP_SECTIONS_RE = re.compile(
    r'\b(table|list)\s+of\s+(figures|tables|illustrations|schemes|charts|maps|plates|abbreviations|acronyms|symbols|appendices)\b',
    re.IGNORECASE
)
STOP_SECTION_WITH_DOTS_RE = re.compile(
    r'\b(table|list)\s+of\s+(figures|tables|illustrations|schemes|charts|maps|plates|abbreviations|acronyms|symbols|appendices)\s*[\.·•…\-_]{2,}',
    re.IGNORECASE
)
FIGURE_TABLE_RE = re.compile(
    r'^\s*(figure|fig\.|table|tbl\.|chart|scheme|map|plate)\s+\d+[\.\:]?|^\s*applicant\s+(table|figure)\b',
    re.IGNORECASE
)

# Standalone section numbers (e.g. '1', '1.', '2.', '8.', '12.', '3.1')
SECTION_NUM_RE = re.compile(r'^\s*(\d+(\.\d+)*\.?|[A-Z](\.\d+)*\.?)\s*$')

# Dot leader & page number regex patterns
DOT_LEADER_RE = re.compile(r'(\s*[\.·•…\-_]{2,}\s*|\s{3,})(\d+|[ivxlcdmIVXLCDM]+|[A-Za-z]?[\-\.]?\d+)?\s*$')
TRAILING_PAGE_RE = re.compile(r'\s+([0-9]+|[ivxlcdmIVXLCDM]+)\s*$')
TRAILING_DOTS_RE = re.compile(r'[\.·•…\-_]+\s*$')

# Header, footer, and disclaimer noise patterns
NOISE_RE = re.compile(
    r'^\s*([\(\{\[].*|reference\s+id\s*:\s*\d+|page\s+\d+|disclaimer\s*:?|version\s+date\b|nda\s+(\d+\s+)?multi-disciplinary.*|nda\s+\d+.*ectd|cder\s*\/|division\s+of\s+.*review)',
    re.IGNORECASE
)

# Noise bookmark filter patterns (template names, date stamps, file names, signature pages, cover/version metadata)
BOOKMARK_NOISE_RE = re.compile(
    r'^\s*(cover\s+sheet|multi|integrated|integrated\s+review|page\s+\d+|\d{1,2}[\.\-\/]\d{1,2}[\.\-\/]\d{2,4}(\s+.*|_.*)?|(nda|bla)\s+\d+.*|.*assessment\s+aid.*|.*template.*|.*\.pdf|.*\.docx?|.*signature.*|signatures|use\s+this\s+version.*|final\.\d.*|nda\/bla\s+multi-disciplinary\s+review.*)\s*$',
    re.IGNORECASE
)

# Attached sub-document date stamp pattern (e.g. "3.20.25 Stat", "11.1.24", "5.28.26_pharm", "5.27.26 - AA_final_sig")
ATTACHED_DOC_RE = re.compile(
    r'^\s*(\d{1,2}[\.\-\/]\d{1,2}[\.\-\/](2[4-9]|202[4-9])(\s+.*|_.*|-.*)?|.*signature\s+page.*|signatures|.*assessment\s+aid\s+signatures.*)\s*$',
    re.IGNORECASE
)

# Signature page pattern at end of document
SIG_PAGE_RE = re.compile(r'^\s*(.*signature.*|signatures)\s*$', re.IGNORECASE)


def clean_toc_line(line: str, is_bookmark: bool = False) -> Optional[str]:
    """Cleans a line by removing dot leaders, dashes, and trailing page numbers via Regex."""
    if not line or not line.strip():
        return None

    cleaned = line.strip()

    if NOISE_RE.search(cleaned):
        return None

    if not is_bookmark and FIGURE_TABLE_RE.search(cleaned):
        return None

    # Apply Regex cleaning pipeline
    cleaned = re.sub(r'\{[^\}]*\}', '', cleaned)
    if not is_bookmark:
        cleaned = DOT_LEADER_RE.sub('', cleaned)
        cleaned = TRAILING_PAGE_RE.sub('', cleaned)
        cleaned = TRAILING_DOTS_RE.sub('', cleaned).strip()

    if not cleaned:
        return None

    if not is_bookmark and FIGURE_TABLE_RE.search(cleaned):
        return None

    return cleaned


def is_fake_bookmark_list(toc: List[Tuple]) -> bool:
    """Detects if PDF bookmarks are generic 'Page 1', 'Page 2' place-holders."""
    if not toc:
        return True
    fake_count = sum(1 for item in toc if BOOKMARK_NOISE_RE.match(item[1].strip()))
    return (fake_count / len(toc)) > 0.3


def extract_toc_from_bookmarks(doc: fitz.Document) -> List[str]:
    """Extracts TOC from PDF bookmarks (outline) with normalized level indents."""
    toc = doc.get_toc(simple=False)
    if not toc or is_fake_bookmark_list(toc):
        return []

    root_level = toc[0][0]
    valid_items = []
    hit_appendices = False

    for item in toc:
        level, title = item[0], item[1].strip()

        cleaned_title = clean_toc_line(title, is_bookmark=True)
        if not cleaned_title:
            continue

        if re.search(r'\b(appendices|appendix|references)\b', cleaned_title, re.IGNORECASE):
            hit_appendices = True

        # Stop condition (checked BEFORE filtering bookmark noise):
        # 1. New attached sub-document (date stamp title with year 24-29 at root level) after extracting main sections
        if len(valid_items) > 5 and level <= root_level and ATTACHED_DOC_RE.match(cleaned_title):
            if not re.match(r'^\d+(\.\d+)+\.?:?\s+[A-Z]', cleaned_title, re.IGNORECASE):
                break

        # 2. Signature page at end of document after Appendices/References
        if hit_appendices and SIG_PAGE_RE.match(cleaned_title):
            break

        # Filter noise bookmarks (cover sheet, file names, date stamps at start)
        if BOOKMARK_NOISE_RE.match(title) or NOISE_RE.search(title):
            continue

        valid_items.append((level, cleaned_title))

    if not valid_items or len(valid_items) < 5:
        return []

    min_level = min(item[0] for item in valid_items)
    lines = []

    for level, cleaned_title in valid_items:
        rel_level = max(0, level - min_level)
        indent = "  " * rel_level
        lines.append(f"{indent}{cleaned_title}")

    return lines


def extract_toc_from_pages(
    doc: fitz.Document,
    top_margin_pct: float = 0.05,
    bottom_margin_pct: float = 0.05
) -> List[str]:
    """
    Regex + Coordinate-driven page extractor.
    Extracts ONLY the Table of Contents entries printed on the document's TOC pages,
    using span-level line coordinates for precise indentation.
    """
    extracted_items = []
    in_toc_region = False
    toc_finished = False

    for page_num in range(len(doc)):
        if toc_finished:
            break

        page = doc[page_num]
        rect = page.rect
        page_height = rect.height

        header_cutoff = page_height * top_margin_pct
        footer_cutoff = page_height * (1.0 - bottom_margin_pct)

        page_dict = page.get_text("dict")
        y_lines = []

        for block in page_dict.get("blocks", []):
            if "lines" not in block:
                continue
            for line in block["lines"]:
                ly0 = line["bbox"][1]
                if not (header_cutoff <= ly0 <= footer_cutoff):
                    continue

                spans_info = []
                for span in line["spans"]:
                    txt = span["text"]
                    if txt.strip():
                        spans_info.append((span["bbox"][0], txt))

                if not spans_info:
                    continue

                merged = False
                for prev_y0, prev_spans in y_lines:
                    if abs(ly0 - prev_y0) < 3:
                        prev_spans.extend(spans_info)
                        merged = True
                        break
                if not merged:
                    y_lines.append((ly0, spans_info))

        y_lines.sort(key=lambda item: item[0])

        raw_page_lines = []
        for y0, spans in y_lines:
            spans.sort(key=lambda x: x[0])
            line_x0 = spans[0][0]
            line_str = " ".join(t.strip() for _, t in spans if t.strip())
            line_str = re.sub(r'\s+', ' ', line_str).strip()

            if line_str and not NOISE_RE.search(line_str):
                raw_page_lines.append((line_x0, line_str))

        # Smart multi-line combiner: merges standalone section numbers or split title lines
        combined_page_lines = []
        idx = 0
        while idx < len(raw_page_lines):
            curr_x0, curr_str = raw_page_lines[idx]

            # Section headers should never be combined with following lines
            if TOC_START_RE.search(curr_str) or STOP_SECTIONS_RE.search(curr_str):
                combined_page_lines.append((curr_x0, curr_str))
                idx += 1
                continue

            has_page_num = bool(re.search(r'[\.·•…\-_]{2,}|\s+(\d+|[ivxlcdm]+|[A-Za-z]?[\-\.]?\d+)\s*$', curr_str))

            if not has_page_num and (idx + 1 < len(raw_page_lines)):
                accumulated_parts = [curr_str]
                min_x0 = curr_x0
                next_idx = idx + 1
                found_ending = False

                while next_idx < len(raw_page_lines):
                    nx0, nstr = raw_page_lines[next_idx]
                    if TOC_START_RE.search(nstr) or STOP_SECTIONS_RE.search(nstr):
                        break
                    accumulated_parts.append(nstr)
                    if nx0 < min_x0:
                        min_x0 = nx0
                    nhas_page = bool(re.search(r'[\.·•…\-_]{2,}|\s+(\d+|[ivxlcdm]+|[A-Za-z]?[\-\.]?\d+)\s*$', nstr))
                    if nhas_page:
                        found_ending = True
                        next_idx += 1
                        break
                    next_idx += 1

                if found_ending:
                    combined_str = " ".join(accumulated_parts)
                    combined_page_lines.append((min_x0, combined_str))
                    idx = next_idx
                    continue

            combined_page_lines.append((curr_x0, curr_str))
            idx += 1

        page_toc_count = 0
        page_items = []

        for line_x0, line_str in combined_page_lines:
            if not in_toc_region:
                if TOC_START_RE.search(line_str):
                    in_toc_region = True
                    extracted_items.append((line_x0, "Table of Contents"))
                    continue
                else:
                    continue

            has_dot_or_page = bool(
                re.search(r'[\.·•…\-_]{2,}|\s+(\d+|[ivxlcdm]+|[A-Za-z]?[\-\.]?\d+)\s*$', line_str)
            )

            if STOP_SECTIONS_RE.search(line_str) and not STOP_SECTION_WITH_DOTS_RE.search(line_str):
                toc_finished = True
                break

            if not has_dot_or_page:
                continue

            cleaned = clean_toc_line(line_str)
            if cleaned and cleaned.lower() not in ["table of contents", "contents"]:
                page_items.append((line_x0, cleaned))
                page_toc_count += 1

        if in_toc_region:
            if page_toc_count >= 3 or (page_toc_count > 0 and len(extracted_items) < 5):
                extracted_items.extend(page_items)
            elif page_toc_count < 3 and len(extracted_items) >= 5:
                toc_finished = True

        if toc_finished:
            break

    if not extracted_items:
        return []

    non_header_x0s = [x for x, text in extracted_items if text.lower() not in ["table of contents", "contents"]]
    if not non_header_x0s:
        return [text for _, text in extracted_items]

    sorted_x0s = sorted(non_header_x0s)
    clusters = []
    for x in sorted_x0s:
        found = False
        for c in clusters:
            if abs(sum(c)/len(c) - x) < 10:
                c.append(x)
                found = True
                break
        if not found:
            clusters.append([x])

    cluster_means = sorted([sum(c)/len(c) for c in clusters])

    formatted_lines = []
    for x0, text in extracted_items:
        if text.lower() in ["table of contents", "contents"]:
            formatted_lines.append(text)
            continue

        level = 0
        for idx, mean in enumerate(cluster_means):
            if abs(x0 - mean) < 10:
                level = idx
                break

        indent = "  " * level
        formatted_lines.append(f"{indent}{text}")

    return formatted_lines


def format_hierarchical_numbers(lines: List[str]) -> List[str]:
    """
    Ensures every section heading and subheading in the extracted TOC
    has a clear hierarchical section number (e.g. 1., 1.1, 1.1.1).
    Preserves existing section numbers and keeps front-matter unnumbered.
    """
    formatted_lines = []

    non_title_lines = [
        l for l in lines
        if l and l.strip() and l.strip().lower() not in ["table of contents", "contents", "glossary"]
    ]
    if not non_title_lines: return lines
    
    indent_set = sorted(set(len(line) - len(line.lstrip()) for line in non_title_lines))
    indent_map = {ind: idx for idx, ind in enumerate(indent_set)}

    section_counters = [0] * 8
    active_depth = 0
    started_numbered_sections = False

    for line in lines:
        if not line or not line.strip() or line.strip().lower() in ["table of contents", "contents", "glossary"]:
            formatted_lines.append(line)
            continue

        indent_spaces = len(line) - len(line.lstrip())
        raw_level = indent_map.get(indent_spaces, 0)
        raw = line.strip()

        # Check if line already starts with an explicit section number like '1.', '1.1', '17.3.1', 'I.', 'II.'
        num_match = re.match(r'^(\d+(\.\d+)*\.?)\s+(.*)$', raw)
        if num_match:
            started_numbered_sections = True
            existing_num = num_match.group(1).rstrip('.')
            title = num_match.group(3)

            parts = [int(p) for p in existing_num.split('.') if p.isdigit()]
            active_depth = len(parts)
            for idx, val in enumerate(parts):
                if idx < len(section_counters):
                    section_counters[idx] = val
            for idx in range(len(parts), len(section_counters)):
                section_counters[idx] = 0

            indent_str = "  " * (len(parts) - 1)
            formatted_lines.append(f"{indent_str}{existing_num}. {title}")
        elif not started_numbered_sections:
            # Front-matter items before Section 1 (Table of Tables, Table of Figures, Reviewers, etc.)
            indent_str = "  " * raw_level
            formatted_lines.append(f"{indent_str}{raw}")
        else:
            # Auto-generate section number prefix for unnumbered subheadings
            target_depth = min(raw_level + 1, active_depth + 1)
            if target_depth < 1:
                target_depth = 1

            level_idx = target_depth - 1
            section_counters[level_idx] += 1
            for idx in range(level_idx + 1, len(section_counters)):
                section_counters[idx] = 0

            valid_parts = []
            for i in range(target_depth):
                val = section_counters[i]
                if val == 0:
                    val = 1
                    section_counters[i] = 1
                valid_parts.append(str(val))

            num_prefix = ".".join(valid_parts)
            active_depth = target_depth
            indent_str = "  " * (target_depth - 1)
            formatted_lines.append(f"{indent_str}{num_prefix}. {raw}")

    return formatted_lines

def generate_toc_from_headings(doc: fitz.Document) -> List[str]:
    """
    Generates a TOC by scanning for bold text and numbered headings.
    Used as a fallback when printed TOCs and bookmarks are absent.
    """
    extracted_items = []
    
    # Pass 1: Find the global left margin of the document (rounded to nearest 10)
    x0_coords = []
    for page_num in range(min(30, len(doc))):
        page = doc[page_num]
        for block in page.get_text("dict").get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        if span["text"].strip():
                            x0_coords.append(round(span["bbox"][0], -1))
                            
    global_margin = 70
    if x0_coords:
        global_margin = Counter(x0_coords).most_common(1)[0][0]
        
    # Pass 2: Extract headings
    for page_num in range(min(30, len(doc))):
        page = doc[page_num]
        page_dict = page.get_text("dict")
        
        for block in page_dict.get("blocks", []):
            if "lines" not in block:
                continue
            
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if not text:
                        continue
                        
                    is_bold = "bold" in span["font"].lower() or "black" in span["font"].lower()
                    
                    # Check if it looks like a numbered heading (e.g. "1. Introduction")
                    is_numbered = bool(re.match(r'^(\d+(\.\d+)*\.|\d+(\.\d+)+|[IVX]+\.)\s+[A-Z].{2,100}$', text))
                    
                    # It's a heading if it's explicitly numbered, OR (bold AND near the left margin)
                    # This prevents extracting bold table headers from middle columns
                    is_near_margin = span["bbox"][0] <= (global_margin + 50)
                    is_heading = is_numbered or (is_bold and is_near_margin)
                    
                    if is_heading and 3 < len(text) < 100 and not text.isdigit():
                        text_without_section = re.sub(r'^(\d+(\.\d+)*\.?|[IVX]+\.)\s*', '', text).strip()
                        
                        words = text_without_section.split()
                        if len(words) > 8:
                            continue
                            
                        # A heading rarely has multiple sentences
                        if ". " in text_without_section or "? " in text_without_section:
                            continue
                            
                        # A heading rarely ends in a period, unless it's just a section number
                        if text.endswith(".") and not re.match(r'^\d+(\.\d+)*\.$', text):
                            continue
                            
                        # Reject blocks that start with lowercase
                        if text_without_section and text_without_section[0].islower():
                            continue
                            
                        # Reject table/figure captions
                        if FIGURE_TABLE_RE.match(text):
                            continue
                            
                        # Reject table data/statistical rows (high digit/symbol density)
                        non_alpha = len(re.findall(r'[^a-zA-Z\s]', text_without_section))
                        if len(text_without_section) > 0 and (non_alpha / len(text_without_section)) > 0.25:
                            continue
                            
                        # Reject common clinical table keywords and symbols (+, =, %, /)
                        if re.search(r'(\b[nN]\s*=|p-value|95%?\s*ci|hazard ratio|confidence interval|odds ratio|study \d+|[\%\+\=\/])', text, re.IGNORECASE):
                            continue
                            
                        extracted_items.append(text)
                        
    # Remove duplicates while preserving order
    seen = set()
    final_items = []
    for item in extracted_items:
        if item not in seen:
            seen.add(item)
            final_items.append(item)
            
    return final_items
