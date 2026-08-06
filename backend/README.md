# Karithera Validator Backend & Chrome Extension

A production-ready Chrome Extension (Manifest V3) with a Python FastAPI backend for validating data displayed in the live Karithera application against a user-uploaded PDF.

## Project Structure

```
├── backend/
│   ├── main.py             # FastAPI App & Endpoints
│   ├── dom_parser.py       # Scraped DOM Payload Parser & Flattener
│   ├── pdf_parser.py       # PDF Text & Structure Extractor (PyMuPDF)
│   ├── normalizer.py       # Unicode, case, punctuation normalization
│   ├── matcher.py          # RapidFuzz sequence matcher & chunking engine
│   ├── validator.py        # Orchestrates validation lifecycle
│   ├── report.py           # Generates HTML and CSV validation reports
│   └── requirements.txt    # Python dependencies
│
└── chrome-extension/
    ├── manifest.json       # Chrome extension configuration (V3)
    ├── background.js       # Extension service worker
    ├── content.js          # Page extraction content script
    ├── popup.html          # Extension UI Popup
    ├── popup.css           # Premium styling for the popup
    └── popup.js            # Main extension interface logic
```

## Setup & Running Instructions

### 1. Backend Setup (FastAPI)

Ensure you have Python 3.12+ installed.

1. Navigate to the `backend/` directory:
   ```bash
   cd backend
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the FastAPI server using Uvicorn:
   ```bash
   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```
   The backend will be running on `http://127.0.0.1:8000`. You can check health at `http://127.0.0.1:8000/health`.

### 2. Chrome Extension Installation

1. Open Google Chrome.
2. Navigate to `chrome://extensions/`.
3. Enable **Developer mode** using the toggle switch in the top-right corner.
4. Click **Load unpacked** in the top-left corner.
5. Select the `chrome-extension/` directory.

### 3. Usage Workflow

1. Open the Karithera application, and navigate to any comparison page.
2. Ensure you have expanded the sections you wish to validate.
3. Open the **Karithera Validator** extension from your browser toolbar.
4. Upload the FDA review PDF corresponding to the comparison data.
5. Click the **Validate Data** button.
6. The extension will read the visible DOM, package it with the PDF, validate it against the backend, and present a detailed breakdown of PASS, PARTIAL, and FAIL sections.
7. Click **Export HTML Report** or **Export CSV Report** to download the generated files.
