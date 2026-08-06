import time
from dom_parser import parse_dom_payload
from pdf_parser import extract_pdf_data
from matcher import match_section

def validate_payload(dom_data: dict, pdf_bytes: bytes) -> dict:
    """
    Validates dynamic DOM UI data against PDF content.
    Returns a unified validation report.
    """
    start_time = time.time()
    
    requested_general_fields = [
        # Clinical Review fields
        "Generic Name", "Review Type", "Priority / Standard", "Application #",
        "Division / Office", "Therapeutic Areas", "Dosage Form", "Dosing Regimen",
        "Pharmacologic Class", "Approval Date", "Submit Date", "Received Date",
        "Review Completion", "Review Name",
        # EPAR fields
        "Product Name", "Marketing Authorisation Holder", "Date Of First Authorisation",
        "Date Of Revision", "Variations", "Initial Documents", "Outcome", "Source",
        "Initial Approval", "Approval Type", "Revised Date"
    ]

    # 1. Parse/Flatten DOM Data
    flat_dom = parse_dom_payload(dom_data)
    
    # 2. Extract PDF Data
    pdf_blocks = extract_pdf_data(pdf_bytes)
    
    # 3. Perform Validation
    section_reports = []
    metadata_validation = {}
    
    meta_passed_count = 0
    meta_partial_count = 0
    meta_failed_count = 0
    
    sec_passed_count = 0
    sec_partial_count = 0
    sec_failed_count = 0
    
    # 3a. Validate Metadata against Excel
    try:
        from excel_validator import ExcelValidator
        excel_val = ExcelValidator()
        excel_results = excel_val.validate_metadata(flat_dom)
    except Exception as e:
        import logging
        logging.getLogger("validator_backend").error(f"Excel validation failed: {e}")
        excel_results = {"error": str(e)}
        
    flat_dom_lower = {k.lower(): k for k in flat_dom.keys()}
    requested_general_fields_lower = [f.lower() for f in requested_general_fields]
    
    # Only validate metadata fields that are actually present in the UI
    present_metadata_fields = [f for f in requested_general_fields if f.lower() in flat_dom_lower]
    
    for section_name in present_metadata_fields:
        if "error" in excel_results:
            report = {
                "section": section_name,
                "status": "FAIL",
                "similarity": 0.0,
                "matched_text": [],
                "missing_text": [f"Excel Error: {excel_results['error']}"],
                "pdf_pages": [],
                "skipped": False
            }
        elif section_name in excel_results:
            report = excel_results[section_name]
        else:
            report = {
                "section": section_name,
                "status": "PASS",
                "similarity": 100.0,
                "matched_text": [],
                "missing_text": [],
                "pdf_pages": [],
                "skipped": True
            }
            
        section_reports.append(report)
        status = report.get("status", "NULL")
        if status == "PASS": meta_passed_count += 1
        elif status == "PARTIAL": meta_partial_count += 1
        elif status == "FAIL": meta_failed_count += 1
        
        metadata_validation[section_name] = {
            "status": status,
            "similarity": report.get("similarity"),
            "matched_text": report.get("matched_text", []),
            "missing_text": report.get("missing_text", []),
            "pdf_pages": report.get("pdf_pages", [])
        }

    # 3b. Validate Dynamic Sections against PDF (supports EPAR dynamically)
    dynamic_sections = [k for k in flat_dom.keys() if k.lower() not in requested_general_fields_lower]
    dynamic_reports = []
    
    for section_name in dynamic_sections:
        ui_value = flat_dom.get(section_name, "")
        report = match_section(section_name, ui_value, pdf_blocks)
        section_reports.append(report)
        dynamic_reports.append(report)
        
        status = report.get("status", "NULL")
        if status == "PASS": sec_passed_count += 1
        elif status == "PARTIAL": sec_partial_count += 1
        elif status == "FAIL": sec_failed_count += 1
        
    # Calculate separate accuracies
    meta_validated = [r for r in section_reports[:len(present_metadata_fields)] if not r.get("skipped", False) and r.get("status") != "NULL" and r.get("similarity") is not None]
    meta_accuracy = (
        sum(r["similarity"] for r in meta_validated) / len(meta_validated)
        if len(meta_validated) > 0 else 100.0
    )
    
    sec_validated = [r for r in dynamic_reports if not r.get("skipped", False) and r.get("status") != "NULL" and r.get("similarity") is not None]
    sec_accuracy = (
        sum(r["similarity"] for r in sec_validated) / len(sec_validated)
        if len(sec_validated) > 0 else 100.0
    )

    processing_time = time.time() - start_time
    
    return {
        "summary": {
            "metadata": {
                "total": len(present_metadata_fields),
                "passed": meta_passed_count,
                "partial": meta_partial_count,
                "failed": meta_failed_count,
                "accuracy": round(meta_accuracy, 2)
            },
            "sections": {
                "total": len(dynamic_sections),
                "passed": sec_passed_count,
                "partial": sec_partial_count,
                "failed": sec_failed_count,
                "accuracy": round(sec_accuracy, 2)
            },
            # Top-level fields prioritized for sections only (maintains report compatibility)
            "total_sections": len(dynamic_sections),
            "passed": sec_passed_count,
            "partial": sec_partial_count,
            "failed": sec_failed_count,
            "overall_accuracy": round(sec_accuracy, 2),
            "processing_time_seconds": round(processing_time, 3)
        },
        "metadata_validation": metadata_validation,
        "sections": dynamic_reports
    }
