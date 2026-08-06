# OutlineMiner

A production-ready desktop application for Data Engineering batch processing. 
It recursively scans folders, extracts the **Table of Contents (TOC)** from PDF documents using a multi-stage extraction pipeline, and saves the extracted TOC as a `.txt` file next to the original PDF.

## Features

- **Multi-stage Pipeline**:
  - Stage 1: Native PDF Bookmarks
  - Stage 2: TOC Page Detection
  - Stage 3: Candidate Extraction
  - Stage 4: Verification via RapidFuzz
  - Stage 5: Heuristic Heading Discovery
  - Stage 6: (Simulated) OCR Fallback for scanned PDFs
- **Robust Folder Traversal**: Recursively scans all subfolders.
- **Resilient**: Processes each PDF independently. Failures don't crash the batch.
- **Reporting**: Generates a detailed `toc_extraction_summary.csv` at the root of the selected folder.
- **Responsive GUI**: Built with PySide6. PDF processing runs in background threads to keep the UI smooth.

## Prerequisites

- **Python 3.9 or higher** must be installed on your system.

## Setup Instructions

1. **Open your terminal** and navigate to the root of this repository:
   ```bash
   cd OutlineMiner
   ```

2. **Create a virtual environment** (recommended to keep dependencies isolated):
   - **Windows:**
     ```powershell
     python -m venv venv
     .\venv\Scripts\activate
     ```
   - **Mac/Linux:**
     ```bash
     python -m venv venv
     source venv/bin/activate
     ```

3. **Install the required dependencies**:
   Run the following command from the root of the repository:
   ```bash
   pip install -r outlineminer/requirements.txt
   ```
   *(Note: The OCR dependencies in the requirements file are optional fallbacks. If `pdf2image` fails to install on Windows, ensure you have [Poppler](https://github.com/oschwartz10612/poppler-windows) installed and added to your system PATH).*

## Running the Application

1. Ensure your virtual environment is activated.
2. From the **root of the repository**, launch the desktop interface by running:
   ```bash
   python main.py
   ```
3. A GUI window titled **"OutlineMiner - PDF TOC Extractor"** will appear.
4. Click **Select Root Folder** and choose the parent directory containing your PDFs.
5. Click **Start Processing**.
6. The application will scan for PDFs and process them, updating the progress bar and logs in real-time.
7. Extracted TOCs will be saved as `.txt` files directly alongside their respective PDFs.
8. Once finished, a summary CSV report (`toc_extraction_summary.csv`) will be placed in the selected root folder.
