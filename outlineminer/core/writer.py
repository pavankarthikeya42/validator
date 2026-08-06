import os
import pandas as pd
from typing import List
from .models import ExtractionResult, TOCEntry

def format_toc_txt(result: ExtractionResult) -> str:
    body = []
    if result.status == "Failed" or not result.raw_text:
        body = [
            f"Status : TOC Not Found\n",
            "No printed TOC or valid bookmarks detected.",
            "Manual review required.",
            result.error_message if result.error_message else ""
        ]
    elif result.raw_text:
        # Text is already perfectly cleaned by the new extractor
        body.append(result.raw_text)
            
    return "\n".join(body)

def write_txt_output(pdf_path: str, result: ExtractionResult):
    """Writes the formatted TOC to a .txt file next to the PDF."""
    txt_path = os.path.splitext(pdf_path)[0] + ".txt"
    try:
        content = format_toc_txt(result)
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        import logging
        logging.getLogger("OutlineMiner").error(f"Failed to write txt for {pdf_path}: {e}")

def write_csv_summary(root_folder: str, results: List[ExtractionResult]):
    """Generates a CSV report summarizing the extraction run."""
    csv_path = os.path.join(root_folder, "toc_extraction_summary.csv")
    
    data = []
    for r in results:
        data.append({
            "PDF Name": r.pdf_name,
            "Relative Path": r.relative_path,
            "Status": r.status,
            "Extraction Source": r.source,
            "Confidence": r.confidence,
            "Processing Time (seconds)": round(r.processing_time, 2),
            "Error Message": r.error_message
        })
        
    df = pd.DataFrame(data)
    try:
        df.to_csv(csv_path, index=False)
    except Exception as e:
        import logging
        logging.getLogger("OutlineMiner").error(f"Failed to write CSV summary: {e}")
