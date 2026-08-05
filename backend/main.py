from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
import logging
from validator import validate_payload
from report import generate_csv_report, generate_html_report

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("validator_backend")

app = FastAPI(title="Karthera Validation Backend")

# Enable CORS for Chrome Extension origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Extension origins can vary
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/validate")
async def validate(
    dom_data: str = Form(...),
    pdf: UploadFile = File(...)
):
    """
    Main validation endpoint.
    Accepts:
    - dom_data: JSON string of extracted DOM elements
    - pdf: Uploaded FDA PDF file
    Returns:
    - Structured validation report including CSV and HTML report exports
    """
    try:
        # Parse DOM Data JSON
        dom_json = json.loads(dom_data)
    except Exception as e:
        logger.error(f"Failed to parse dom_data JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON format for dom_data")
        
    try:
        # Read PDF bytes
        pdf_bytes = await pdf.read()
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="Uploaded PDF is empty")
    except Exception as e:
        logger.error(f"Failed to read PDF bytes: {e}")
        raise HTTPException(status_code=500, detail="Failed to read uploaded PDF file")
        
    logger.info(f"Received validation request. DOM sections: {len(dom_json)}, PDF size: {len(pdf_bytes)} bytes")
    
    # Run Validation
    try:
        results = validate_payload(dom_json, pdf_bytes)
    except Exception as e:
        logger.error(f"Validation engine failure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Validation engine encountered an error: {str(e)}")
        
    # Generate Reports
    try:
        csv_report = generate_csv_report(results)
        html_report = generate_html_report(results)
    except Exception as e:
        logger.error(f"Report generation failure: {e}")
        csv_report = ""
        html_report = ""
        
    return {
        "success": True,
        "summary": results["summary"],
        "metadata_validation": results["metadata_validation"],
        "sections": results["sections"],
        "reports": {
            "csv": csv_report,
            "html": html_report
        }
    }
