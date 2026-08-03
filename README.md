# Karthera PDF Verification Tool

A production-ready Chrome Extension (Manifest V3) and Python FastAPI backend for validating data displayed in the live Karthera application against a user-uploaded PDF.

The extension reads the visible DOM elements dynamically (metadata table and section groups), normalizes the text, and validates it against the uploaded FDA review PDF on a local FastAPI server, producing detailed HTML/CSV reports.

---

## How It Works

```
You (on Karthera App) 
       │
       ▼ [Upload PDF & Click Validate]
Chrome Extension (Manifest V3 Popup)
       │  Scrapes visible DOM
       │  Sends PDF File + DOM JSON
       ▼
FastAPI Backend (localhost:8000/validate)
       │  Parses PDF Text (PyMuPDF)
       │  Runs Exact + RapidFuzz Matcher (95% threshold)
       │  Generates HTML/CSV Validation Reports
       ▼
Chrome Extension
       │  Displays status badges (PASS / PARTIAL / FAIL)
       │  Triggers local download of reports
```

---

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
│   ├── requirements.txt    # Python dependencies
│   └── README.md           # Backend specific setup guide
│
└── chrome-extension/
    ├── manifest.json       # Chrome extension configuration (V3)
    ├── background.js       # Extension service worker
    ├── content.js          # Page extraction content script
    ├── popup.html          # Extension UI Popup
    ├── popup.css           # Premium styling for the popup
    └── popup.js            # Main extension interface logic
```

---

## Setup & Running Instructions

### 1. Start FastAPI Backend

Ensure you have Python 3.12+ installed.

1. Navigate to the `backend/` directory:
   ```bash
   cd backend
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the FastAPI server:
   ```bash
   python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```
   The backend will start running on `http://127.0.0.1:8000`. You can check health at `http://127.0.0.1:8000/health`.

### 2. Install the Chrome Extension

1. Open Google Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer mode** using the toggle switch in the top-right corner.
3. Click **Load unpacked** in the top-left corner.
4. Select the `chrome-extension/` directory.

### 3. Verification Workflow

1. Navigate to your Karthera application, and open a document comparison page.
2. Expand whichever sections you want to validate.
3. Open the **Karthera Validator** extension from your Chrome toolbar.
4. Upload the FDA review PDF corresponding to the comparison page.
5. Click **Validate Data**.
6. The extension will scrape the visible DOM, run validation against the backend, display a summary breakdown of PASSED, PARTIAL, and FAILED sections, and enable report download buttons.
7. Click **Export HTML Report** or **Export CSV Report** to download the generated files locally.
