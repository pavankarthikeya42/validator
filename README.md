# Document Validation Tool

A fully automated, **read-only** Python + Playwright validation tool with a **floating Chrome extension UI**.
Navigate to any web application, click the pen button, and hit **Start** — it validates the documents on that exact page against their embedded PDFs in real time.

---

## How It Works

```
You (on any webpage)
        │  click the pen button → Start
        ▼
Chrome Extension  (floating FAB, injects on every page)
        │  sends current page URL + command
        ▼
server.py  (FastAPI bridge, localhost:8765)
        │  spawns subprocess with --url <current page>
        ▼
main.py  (Playwright automation)
        │  opens browser → navigates to YOUR page
        │  expands each document row
        │  reads 19 UI sections
        │  reads embedded PDF
        ▼
comparator.py  →  reporter.py
        │
        ▼
reports/  (JSON + CSV + Excel + HTML)
```

> **Key point:** The tool always validates the page you are currently viewing — no need to edit `config.yaml` to change the URL.

---

## Features

| Capability | Details |
|---|---|
| **Floating pen button** | Appears on every http/https page automatically |
| **Validates current page** | Clicking Start passes your current URL to the tool |
| **Start / Stop / Resume** | Full control without touching a terminal |
| **Live progress** | Animated progress bar + "Document 152 of 940" counter |
| **Fully automated** | Detects, expands, and validates every document without manual steps |
| **Infinite scroll / Load More** | Automatically loads all records before starting |
| **19 UI sections** | Waits for all sections to load before extracting |
| **PDF extraction** | PDF.js DOM scraping + download+pdfplumber (auto-selected) |
| **Heading-anchored validation** | Each UI section is anchored to its PDF heading; only text under that heading is compared |
| **Semantic sections** | Metadata / Indication matched by meaning via local sentence-transformer embeddings |
| **Smart comparison** | Match / Mismatch / Missing in PDF / Missing in UI |
| **Normalisation** | Case, whitespace, date format (DD/MM/YYYY ↔ YYYY-MM-DD), currency |
| **Resume support** | Picks up exactly where the last run stopped after any interruption |
| **Error recovery** | One failed document never stops the run; logged and skipped |
| **4 report formats** | JSON + CSV + Excel (3 sheets) + HTML dashboard |
| **Mismatch screenshots** | Screenshot captured automatically for every mismatched field |
| **Read-only** | Never writes, saves, updates, or deletes application data |

---

## Quick Start

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure selectors

Open **`config.yaml`** and fill in the CSS selectors for your app:

- `document_list.*` — container, row, expand button selectors
- `ui_sections.sections` — name and selectors for all 19 UI sections
- `pdf.*` — selector for the embedded PDF iframe
- `field_mappings` — map UI field paths to PDF regex patterns
- `app.login.*` — credentials if a login step is needed (or set env vars `VALIDATOR_USER` / `VALIDATOR_PASS`)

> **Tip:** Run `python main.py --dry-run` first to confirm the tool detects all documents safely.

### 3. Start the bridge server

Double-click **`run_server.bat`**, or in a terminal:

```bash
python server.py
```

Keep this window open while you use the extension. It listens on `http://localhost:8765`.

### 4. Load the Chrome Extension

1. Open Chrome → `chrome://extensions`
2. Enable **Developer mode** (top-right toggle)
3. Click **"Load unpacked"**
4. Select the `extension/` folder

> After loading, **reload any tabs** you want to use the button on.

### 5. Validate any page

1. Go to your web application
2. A **purple pen-in-circle** button appears at the **bottom-right**
3. The subtitle in the panel shows the hostname of the current page
4. Click **▶ Start** — the tool opens a browser, navigates to your exact page, and begins validating

| Button | Active when | Action |
|---|---|---|
| **▶ Start** | Idle / Complete | Starts a fresh run on the current page |
| **⏹ Stop** | Running | Stops the process and saves a checkpoint |
| **⏩ Resume** | Stopped | Continues from the last completed document on the current page |

---

## Alternatively — Run from the Terminal

```bash
# Full run (uses URL from config.yaml)
python main.py

# Validate a specific page URL directly
python main.py --url "http://myapp.com/documents"

# Resume from last checkpoint
python main.py --resume

# Resume on a specific page
python main.py --resume --url "http://myapp.com/documents"

# Validate only documents 50–100
python main.py --start 50 --end 100

# List all documents without validating (safe dry run)
python main.py --dry-run

# Debug mode (slow interactions, verbose output)
python main.py --debug

# Headless mode (no visible browser window)
python main.py --headless

# Use a custom config file
python main.py --config my_config.yaml

# Clear checkpoint and start fresh
python main.py --reset
```

---

## Project Structure

```
├── server.py            ← FastAPI bridge server (start this first)
├── run_server.bat       ← Double-click launcher for the server (Windows)
├── main.py              ← CLI entry point (progress bar, orchestration)
├── config.yaml          ← ALL selector + mapping configuration
├── browser.py           ← Playwright browser lifecycle + page helpers
├── document_list.py     ← Scroll, paginate, expand/collapse document rows
├── ui_extractor.py      ← Extract data from 19 UI sections
├── pdf_extractor.py     ← Extract text from embedded PDF
├── comparator.py        ← Field comparison + normalisation engine
├── section_matcher.py   ← Heading-anchored + semantic section validation
├── reporter.py          ← JSON / CSV / Excel / HTML report generation
├── state.py             ← Checkpoint file (state.json) for resume support
├── requirements.txt
│
├── extension/                    ← Chrome extension (load unpacked)
│   ├── manifest.json             ← Injects on all http/https/file pages
│   ├── content.js                ← Floating pen button + control panel
│   ├── background.js             ← Relays API calls to localhost:8765
│   └── icons/
│       └── icon.svg
│
├── tests/
│   ├── test_comparator.py        ← 15 unit tests
│   └── test_reporter.py          ← 5 unit tests
│
└── reports/                      ← Generated after each run
    ├── results.json
    ├── results.csv
    ├── results.xlsx
    ├── report.html
    └── screenshots/
```

---

## Configuration Guide

### Pagination

```yaml
document_list:
  pagination:
    type: "infinite_scroll"   # or "load_more" or "none"
    scroll_pause_ms: 1500
    stable_after_attempts: 3
```

### PDF Extraction Strategy

```yaml
pdf:
  strategy: "auto"   # "pdfjs_dom" | "iframe_src" | "auto"
```

| Strategy | When to use |
|---|---|
| `pdfjs_dom` | PDF.js viewer with a text layer in the DOM — fast, no download |
| `iframe_src` | Canvas-only PDF.js or a plain `<iframe src="...pdf">` — downloads and parses with pdfplumber |
| `auto` | Tries `pdfjs_dom` first, falls back to `iframe_src` |

### Validation (heading-anchored)

Used automatically when `field_mappings` is empty.

```yaml
validation:
  section_matching: true
  match_threshold: 0.85
  partial_threshold: 0.6
  semantic_threshold: 0.75
  semantic_model: "all-MiniLM-L6-v2"
  semantic_sections:
    - "Metadata"
    - "Indication"
```

The first heading of a UI section (e.g. `1. Executive Summary`) is its anchor: the
same heading is located in the PDF and only the sub-headings and body text under
it are compared. Any further numbered heading inside the same section (e.g.
`2.3 Executive Summary`) is anchored and compared as its own block. A heading the
UI shows but the PDF lacks is `MISSING_IN_PDF`; a PDF heading no UI section
claimed is `MISSING_IN_UI`.

A block scoring below `match_threshold` but at or above `partial_threshold` is
`PARTIAL` — the right heading with only part of its text found. Reports carry an
overall accuracy where a `PARTIAL` block counts for how much of it matched.

Sections named in `semantic_sections` skip heading anchoring and are compared by
meaning using local embeddings (`pip install sentence-transformers`; the model
downloads once, ~90 MB). If the model is unavailable the comparison falls back to
lexical similarity so a run never fails offline.

### Field Mappings

Set these to override heading-anchored validation with explicit regex mappings.

```yaml
field_mappings:
  - ui_path: "Section 1 > Document Number"
    pdf_regex: "Document\\s*(?:No\\.?|Number)[:\\s]+([\\w\\-]+)"
    normalise: true
```

- `ui_path` must match `<Section Name> > <Label>` exactly as it appears in the UI.
- `pdf_regex` must contain exactly **one capturing group** `( )` for the field value.
- `normalise: true` enables case-insensitive comparison, date normalisation, and currency stripping.

### Normalisation Rules

| Input | Normalised to |
|---|---|
| `DOC-001` / `doc-001` | match ✓ |
| `01/12/2024` / `2024-12-01` | match ✓ |
| `$1,234.56` / `1234.56` | match ✓ |
| `  Hello   World  ` / `hello world` | match ✓ |

---

## Reports

| File | Contents |
|---|---|
| `report.html` | Dark-themed interactive dashboard; per-document accordion with colour-coded field rows and inline mismatch screenshots |
| `results.json` | Full machine-readable results with all field values |
| `results.csv` | Flat spreadsheet — one row per field: `doc_id, field, ui_value, pdf_value, status` |
| `results.xlsx` | Three sheets: **Summary**, **Field Results** (all), **Mismatches only** |
| `screenshots/` | PNG screenshots for every mismatch and every failed document |

---

## Final Summary

Printed at the end of every run and available in `results.json`:

```
Total Documents:    940
Fields Validated:  17860
Matches:           17612
Mismatches:          194
Missing Fields:       54
Failed Docs:           2
Duration:         1h 23m 41s
Success Rate:      99.79%
```

---

## Running Tests

```bash
pytest tests/ -v
```

20 tests covering: normalisation (whitespace, case, dates, currency), match / mismatch / missing detection, extra-field handling, and all four report output formats.

---

## Security Notes

- Credentials can be set via environment variables (`VALIDATOR_USER`, `VALIDATOR_PASS`) instead of storing them in `config.yaml`.
- The bridge server (`server.py`) binds to `127.0.0.1` only — not accessible from other machines on the network.
- The tool is **strictly read-only**: it only clicks expand/collapse controls and reads page content. It never submits, saves, or modifies application data.
