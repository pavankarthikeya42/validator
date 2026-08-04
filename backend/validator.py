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
        "Generic Name", "Review Type", "Priority / Standard", "Application #",
        "Division / Office", "Therapeutic Areas", "Dosage Form", "Dosing Regimen",
        "Pharmacologic Class", "Approval Date", "Submit Date", "Received Date",
        "Review Completion", "Review Name"
    ]

    requested_sections = [
        "Indication", "Executive / Product / Summary Review", "Background / Therapeutic Context",
        "Regulatory Background / History / Considerations", "CMC / Product Quality",
        "Nonclinical Pharmacology / Toxicology", "Clinical Pharmacology", "Clinical Filing Checklist",
        "Clinical Data and Review Strategy", "Efficacy", "Safety", "Risk Assessments / Risk Evaluation and Mitigation",
        "Postmarketing Requirements", "Labeling Recommendations", "Advisory Committee Review",
        "Ethics and Good Clinical Practices", "Other Significant Issues Identified", "Appendices"
    ]
    
    # 1. Parse/Flatten DOM Data
    flat_dom = parse_dom_payload(dom_data)
    
    # Filter flat_dom to ONLY include the 14 metadata fields and 18 sections
    filtered_dom = {}
    for key in requested_general_fields + requested_sections:
        filtered_dom[key] = flat_dom.get(key, "")

    # 2. Extract PDF Data
    pdf_blocks = extract_pdf_data(pdf_bytes)
    
    # 3. Perform Validation for each section
    section_reports = []
    metadata_validation = {}
    
    passed_count = 0
    partial_count = 0
    failed_count = 0
    
    for section_name, ui_value in filtered_dom.items():
        report = match_section(section_name, ui_value, pdf_blocks)
        section_reports.append(report)
        
        status = report["status"]
        if status == "PASS":
            passed_count += 1
        elif status == "PARTIAL":
            partial_count += 1
        else:
            failed_count += 1
            
        # Distinguish between General Information (metadata) and dynamic sections
        if section_name in requested_general_fields:
            metadata_validation[section_name] = {
                "status": status,
                "similarity": report["similarity"],
                "pdf_pages": report["pdf_pages"]
            }
            
    total_sections = len(filtered_dom)
    
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
        "sections": section_reports
    }
