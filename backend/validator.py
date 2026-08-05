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
    
    passed_count = 0
    partial_count = 0
    failed_count = 0
    
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
        status = report["status"]
        if status == "PASS": passed_count += 1
        elif status == "PARTIAL": partial_count += 1
        else: failed_count += 1
        
        metadata_validation[section_name] = {
            "status": status,
            "similarity": report["similarity"],
            "matched_text": report.get("matched_text", []),
            "missing_text": report.get("missing_text", []),
            "pdf_pages": report["pdf_pages"]
        }

    # 3b. Validate Dynamic Sections against PDF (supports EPAR dynamically)
    dynamic_sections = [k for k in flat_dom.keys() if k.lower() not in requested_general_fields_lower]
    dynamic_reports = []
    
    for section_name in dynamic_sections:
        ui_value = flat_dom.get(section_name, "")
        report = match_section(section_name, ui_value, pdf_blocks)
        section_reports.append(report)
        dynamic_reports.append(report)
        
        status = report["status"]
        if status == "PASS": passed_count += 1
        elif status == "PARTIAL": partial_count += 1
        else: failed_count += 1
        
    total_sections = len(flat_dom)
    
    # Overall Accuracy is the average similarity score across all validated sections (excluding skipped ones)
    validated_reports = [r for r in section_reports if not r.get("skipped", False)]
    overall_accuracy = (
        sum(r["similarity"] for r in validated_reports) / len(validated_reports)
        if len(validated_reports) > 0 else 100.0
    )

    processing_time = time.time() - start_time
    
    return {
        "summary": {
            "total_sections": total_sections,
            "passed": passed_count,
            "partial": partial_count,
            "failed": failed_count,
            "overall_accuracy": round(overall_accuracy, 2),
            "processing_time_seconds": round(processing_time, 3)
        },
        "metadata_validation": metadata_validation,
        "sections": dynamic_reports
    }
