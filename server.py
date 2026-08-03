"""
server.py — Local HTTP Bridge Server

Allows the Chrome Extension to communicate with the Python validation tool.
Run this before using the extension: python server.py

Endpoints:
  GET  /status      → current validation progress (reads state.json)
  GET  /logs        → last 50 lines of subprocess output (for live debugging)
  GET  /config-check → validate config.yaml has real selectors, not placeholders
  POST /start       → start validation (python main.py)
  POST /stop        → stop running validation process
  POST /resume      → resume from checkpoint (python main.py --resume)
"""
from __future__ import annotations

import collections
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# Force UTF-8 stdout/stderr encoding on Windows to prevent UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import yaml

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="Document Validator Bridge", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── State ──────────────────────────────────────────────────────────────────────
_process: subprocess.Popen | None = None
_run_started_at: float = 0.0
_log_buffer: collections.deque = collections.deque(maxlen=100)   # last 100 lines
_log_lock = threading.Lock()

STATE_FILE  = Path(__file__).parent / "state.json"
CONFIG_FILE = Path(__file__).parent / "config.yaml"
MAIN_SCRIPT = Path(__file__).parent / "main.py"
REPORTS_DIR = Path(__file__).parent / "reports"
PYTHON      = sys.executable

# Placeholder values that mean the user has not configured the field yet
_PLACEHOLDERS = {
    ".document-list", ".document-row", ".doc-id", ".doc-row-expand",
    ".doc-expanded", ".doc-row-collapse", ".ui-sections-loaded",
    ".section-1", ".section-2", ".field-label", ".field-value",
    "iframe.pdf-viewer", ".load-more-btn", "#username", "#password",
    "http://localhost:8080",
}


# ── Subprocess log reader ──────────────────────────────────────────────────────

def _read_output(proc: subprocess.Popen) -> None:
    """Background thread: drain subprocess stdout into log buffer AND stream to console."""
    try:
        for line in proc.stdout:
            cleaned = line.rstrip()
            with _log_lock:
                _log_buffer.append(cleaned)
            # Print live to terminal console so errors/logs are immediately visible
            print(cleaned, flush=True)
    except Exception as exc:
        print(f"[ERROR READING LOGS] {exc}", flush=True)
    finally:
        try:
            proc.wait()
            if proc.returncode is not None and proc.returncode != 0:
                err_msg = f"[PROCESS ERROR] Validation process exited with code {proc.returncode}"
                with _log_lock:
                    _log_buffer.append(err_msg)
                print(f"\n❌ {err_msg}\n", flush=True)
        except Exception:
            pass


def _spawn(cmd: list[str]) -> subprocess.Popen:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        cmd,
        cwd=str(MAIN_SCRIPT.parent),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )
    t = threading.Thread(target=_read_output, args=(proc,), daemon=True)
    t.start()
    return proc


# ── Helpers ────────────────────────────────────────────────────────────────────

def _read_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _is_running() -> bool:
    return _process is not None and _process.poll() is None


def _exit_code() -> int | None:
    return _process.poll() if _process else None


def _check_config() -> list[str]:
    """Return a list of warnings about unconfigured fields."""
    warnings = []
    if not CONFIG_FILE.exists():
        return ["config.yaml not found"]
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        return [f"config.yaml parse error: {e}"]

    # Check app URL
    url = cfg.get("app", {}).get("url", "")
    if url in _PLACEHOLDERS or not url:
        warnings.append("app.url is still the placeholder — set it to your real app URL")

    # Check login credentials (only if not authenticated)
    if not cfg.get("app", {}).get("authenticated", False):
        login = cfg.get("app", {}).get("login", {})
        if not login.get("username") and not os.environ.get("VALIDATOR_USER"):
            warnings.append("app.login.username is empty — set credentials or VALIDATOR_USER env var")

    # Check document list selectors
    dl = cfg.get("document_list", {})
    for key in ("container_selector", "row_selector", "expand_trigger_selector"):
        val = dl.get(key, "")
        if val in _PLACEHOLDERS or not val:
            warnings.append(f"document_list.{key} is a placeholder — update it with the real CSS selector")

    # Check sections
    sections = cfg.get("ui_sections", {}).get("sections", [])
    if not sections:
        warnings.append("ui_sections.sections is empty — add your 19 sections")
    else:
        placeholder_sections = [
            s["name"] for s in sections
            if s.get("container_selector", "") in _PLACEHOLDERS
        ]
        if placeholder_sections:
            warnings.append(
                f"{len(placeholder_sections)} section(s) still have placeholder selectors: "
                + ", ".join(placeholder_sections[:3])
                + ("…" if len(placeholder_sections) > 3 else "")
            )

    # Check field mappings
    mappings = cfg.get("field_mappings", [])
    if not mappings:
        warnings.append("field_mappings is empty — add at least one UI→PDF field mapping")

    return warnings


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/status")
def get_status():
    state = _read_state()
    running = _is_running()
    exit_code = _exit_code()

    last_idx   = state.get("last_completed_index", -1)
    total      = state.get("total_documents", 0)
    completed  = last_idx + 1 if last_idx >= 0 else 0
    failed     = len(state.get("failed_indices", []))
    matches    = state.get("total_matches", 0)
    mismatches = state.get("total_mismatches", 0)
    fields     = state.get("total_fields_validated", 0)

    # Determine status label
    if running:
        status_label = "RUNNING"
    elif exit_code is not None and exit_code != 0 and completed == 0:
        status_label = "ERROR"
    elif completed > 0 and not running:
        status_label = "STOPPED" if completed < total else "COMPLETE"
    else:
        status_label = "IDLE"

    # Last log line for quick debugging
    with _log_lock:
        last_log = list(_log_buffer)[-1] if _log_buffer else ""

    return JSONResponse({
        "status": status_label,
        "running": running,
        "exit_code": exit_code,
        "completed": completed,
        "total": total,
        "failed": failed,
        "matches": matches,
        "mismatches": mismatches,
        "fields_validated": fields,
        "progress_pct": round(completed / total * 100, 1) if total > 0 else 0,
        "run_id": state.get("run_id", ""),
        "elapsed": round(time.time() - _run_started_at, 0) if running else 0,
        "last_log": last_log,
    })


@app.get("/logs")
def get_logs():
    """Return the last 50 lines of subprocess output."""
    with _log_lock:
        lines = list(_log_buffer)
    return JSONResponse({"lines": lines[-50:]})


@app.get("/reports")
def list_reports():
    """List available report files."""
    files = {
        "csv": (REPORTS_DIR / "results.csv").exists(),
        "excel": (REPORTS_DIR / "results.xlsx").exists(),
        "json": (REPORTS_DIR / "results.json").exists(),
        "html": (REPORTS_DIR / "report.html").exists(),
    }
    return JSONResponse({"ok": True, "files": files})


@app.get("/download/{fmt}")
def download_report(fmt: str):
    """Download report file by format: csv, excel, json, html."""
    mapping = {
        "csv": ("results.csv", "text/csv"),
        "excel": ("results.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        "xlsx": ("results.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        "json": ("results.json", "application/json"),
        "html": ("report.html", "text/html"),
    }
    fmt_key = fmt.lower()
    if fmt_key not in mapping:
        return JSONResponse({"ok": False, "message": "Invalid format. Supported: csv, excel, json, html"}, status_code=400)

    filename, media_type = mapping[fmt_key]
    file_path = REPORTS_DIR / filename

    if not file_path.exists():
        return JSONResponse({"ok": False, "message": f"Report {filename} not generated yet"}, status_code=404)

    return FileResponse(path=file_path, filename=filename, media_type=media_type)


@app.get("/config-check")
def config_check():
    warnings = _check_config()
    return JSONResponse({
        "ok": len(warnings) == 0,
        "warnings": warnings,
        "config_path": str(CONFIG_FILE),
    })


@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload a manual PDF file to compare against UI content."""
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        dest_path = REPORTS_DIR / "manual_input.pdf"
        contents = await file.read()
        with open(dest_path, "wb") as f:
            f.write(contents)
        return JSONResponse({
            "ok": True,
            "filename": file.filename,
            "path": str(dest_path.resolve()),
        })
    except Exception as exc:
        return JSONResponse({"ok": False, "message": f"Upload failed: {exc}"}, status_code=500)


@app.post("/validate-dom")
async def validate_dom(request: Request):
    """
    Direct DOM validation endpoint.
    Receives extracted UI data from extension content script,
    parses manual PDF (or saved PDF), compares fields, and generates Excel/CSV reports.
    """
    try:
        body = await request.json()
        ui_data = body.get("ui_data", {})
        target_url = body.get("url", "")
        manual_pdf = body.get("manual_pdf", "")

        if not manual_pdf or not Path(manual_pdf).exists():
            default_pdf = REPORTS_DIR / "manual_input.pdf"
            if default_pdf.exists():
                manual_pdf = str(default_pdf)

        # 1. Parse PDF text
        pdf_text = ""
        if manual_pdf and Path(manual_pdf).exists():
            import pdfplumber
            with pdfplumber.open(manual_pdf) as pdf:
                pages_text = [p.extract_text() for p in pdf.pages if p.extract_text()]
                pdf_text = "\n".join(pages_text)

        pdf_data = {"__raw__": pdf_text}

        # 2. Compare UI ↔ PDF
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}

        from comparator import Comparator
        from reporter import Reporter
        from state import RunState

        state = RunState()
        state.total_documents = 1
        state.start_time = time.time()

        cmp = Comparator(cfg)
        rep = Reporter(cfg, state)

        res = cmp.compare("current_document", 0, ui_data, pdf_data)
        rep.add_result(res)
        rep.save_all()

        state.mark_completed(0, "current_document", res.summary_dict())

        return JSONResponse({
            "ok": True,
            "status": "COMPLETE",
            "completed": 1,
            "total": 1,
            "matches": res.matches,
            "mismatches": res.mismatches,
            "missing": res.missing_in_pdf + res.missing_in_ui,
            "fields_validated": res.total_fields,
            "progress_pct": 100.0,
            "excel_report": str(rep.xlsx_file.name),
            "csv_report": str(rep.csv_file.name),
        })
    except Exception as exc:
        return JSONResponse({"ok": False, "message": f"Validation failed: {exc}"}, status_code=500)


@app.post("/start")
async def start_validation(request: Request):
    global _process, _run_started_at

    if _is_running():
        return JSONResponse({"ok": False, "message": "Already running"}, status_code=409)

    # Read parameters from extension
    target_url = ""
    manual_pdf = ""
    try:
        body = await request.json()
        target_url = body.get("url", "").strip()
        manual_pdf = body.get("manual_pdf", "").strip()
    except Exception:
        pass

    # Clear old state for a fresh run
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    with _log_lock:
        _log_buffer.clear()

    cmd = [PYTHON, str(MAIN_SCRIPT), "--headless"]
    if target_url:
        cmd += ["--url", target_url]
    if manual_pdf:
        cmd += ["--manual-pdf", manual_pdf]

    try:
        _process = _spawn(cmd)
        _run_started_at = time.time()
        return JSONResponse({
            "ok": True,
            "message": "Validation started",
            "pid": _process.pid,
            "url": target_url,
            "manual_pdf": manual_pdf,
        })
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=500)


@app.post("/stop")
def stop_validation():
    global _process

    if not _is_running():
        return JSONResponse({"ok": False, "message": "Not running"}, status_code=409)

    try:
        _process.terminate()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.kill()
        return JSONResponse({"ok": True, "message": "Validation stopped"})
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=500)


@app.post("/resume")
async def resume_validation(request: Request):
    global _process, _run_started_at

    if _is_running():
        return JSONResponse({"ok": False, "message": "Already running"}, status_code=409)

    if not STATE_FILE.exists():
        return JSONResponse(
            {"ok": False, "message": "No checkpoint found — use Start for a fresh run."},
            status_code=400,
        )

    target_url = ""
    try:
        body = await request.json()
        target_url = body.get("url", "").strip()
    except Exception:
        pass

    with _log_lock:
        _log_buffer.clear()

    cmd = [PYTHON, str(MAIN_SCRIPT), "--headless", "--resume"]
    if target_url:
        cmd += ["--url", target_url]

    try:
        _process = _spawn(cmd)
        _run_started_at = time.time()
        return JSONResponse({
            "ok": True,
            "message": "Validation resumed",
            "pid": _process.pid,
            "url": target_url,
        })
    except Exception as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=500)


@app.get("/")
def root():
    return {"service": "Document Validator Bridge", "version": "1.0.0"}


# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print("\n✅  Document Validator Bridge Server (Auto-Reload Enabled)")
    print("   Listening on http://localhost:8765")
    print("   Load the browser extension, then click the pen icon on any app.\n")
    uvicorn.run("server:app", host="127.0.0.1", port=8765, reload=True, log_level="info")
