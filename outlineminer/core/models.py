from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class TOCEntry:
    title: str
    page: int
    confidence: float = 0.0

@dataclass
class ExtractionResult:
    pdf_name: str
    relative_path: str
    status: str  # "Success" or "Failed"
    source: str  # "Bookmark", "TOC Page", "Heading Detection", "OCR", "None"
    confidence: int  # 0 to 100
    processing_time: float
    error_message: str = ""
    raw_text: str = ""
    toc_entries: List[TOCEntry] = field(default_factory=list)
