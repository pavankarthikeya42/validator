"""
main.py — Entry Point for the Document Validation Tool

Usage:
    python main.py                          # Full run (uses URL from config.yaml)
    python main.py --url http://app/docs    # Override the target page URL at runtime
    python main.py --resume                 # Resume from last checkpoint
    python main.py --start 50              # Start from index 50
    python main.py --end 100               # Stop after index 100
    python main.py --dry-run               # Detect documents, do not validate
    python main.py --config my.yaml        # Use a custom config file
    python main.py --headless              # Override: run browser headlessly
    python main.py --debug                 # Verbose output + slow_mo=200ms
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

# Force UTF-8 encoding on Windows stdout/stderr to prevent cp1252 charmap errors
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import yaml
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from browser import managed_browser
from comparator import Comparator
from document_list import DocumentListNavigator
from pdf_extractor import PDFExtractor
from reporter import Reporter
from state import RunState
from ui_extractor import UIExtractor

console = Console(force_terminal=False, legacy_windows=False)


# ======================================================================
# Config Loader
# ======================================================================
def load_config(path: str) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        console.print(f"[red]Config file not found: {path}[/red]")
        sys.exit(1)
    with open(config_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    return cfg or {}


# ======================================================================
# CLI Arguments
# ======================================================================
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Document Validation Tool — read-only automated UI ↔ PDF comparison"
    )
    parser.add_argument(
        "--config", default="config.yaml", help="Path to config YAML file (default: config.yaml)"
    )
    parser.add_argument(
        "--resume", action="store_true", help="Resume from last checkpoint"
    )
    parser.add_argument(
        "--start", type=int, default=None, help="Start from this document index (0-based)"
    )
    parser.add_argument(
        "--end", type=int, default=None, help="Stop after this document index (inclusive)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Detect and list documents without validating"
    )
    parser.add_argument(
        "--headless", action="store_true", help="Run browser in headless mode"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Verbose output + slow interactions (slow_mo=200ms)"
    )
    parser.add_argument(
        "--reset", action="store_true", help="Clear the checkpoint and start fresh"
    )
    parser.add_argument(
        "--url", default=None,
        help="Override the app URL from config.yaml (used by the Chrome extension to validate the current page)"
    )
    parser.add_argument(
        "--manual-pdf", default=None,
        help="Path to a manually provided local PDF file to compare against the UI content"
    )
    return parser.parse_args()


# ======================================================================
# Screenshot helpers
# ======================================================================
def _mismatch_screenshot_path(output_cfg: dict, doc_id: str, field_path: str) -> str:
    screenshots_dir = Path(output_cfg.get("screenshots_dir", "./reports/screenshots"))
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in doc_id)
    safe_field = "".join(c if c.isalnum() or c in "-_" else "_" for c in field_path)[:50]
    return str(screenshots_dir / f"{safe_id}__{safe_field}.png")


# ======================================================================
# Per-document validation
# ======================================================================
async def validate_document(
    doc: dict,
    navigator: DocumentListNavigator,
    ui_extractor: UIExtractor,
    pdf_extractor: PDFExtractor,
    comparator: Comparator,
    reporter: Reporter,
    config: dict,
) -> dict:
    """
    Full validation pipeline for a single document.
    Returns a summary dict for state tracking.
    Raises on unrecoverable errors — caller logs and continues.
    """
    from comparator import FieldStatus

    is_single_page = doc.get("is_single_page", False)

    # 1. Expand document row (skip if already on single page view)
    if not is_single_page:
        await navigator.expand_document(doc)

    # 2. Wait for all 19 sections to load
    await navigator.wait_for_all_sections()

    # 3. Extract UI data
    ui_data = await ui_extractor.extract_all_sections()
    ui_tables = await ui_extractor.extract_tables()

    # 4. Extract PDF data
    pdf_data = await pdf_extractor.extract()
    pdf_tables = await pdf_extractor.extract_tables()

    # 5. Compare fields
    result = comparator.compare(
        doc_id=doc["id"],
        doc_index=doc["index"],
        ui_data=ui_data,
        pdf_data=pdf_data,
        ui_tables=ui_tables,
        pdf_tables=pdf_tables,
    )

    # 6. Capture screenshots for mismatched fields
    output_cfg = config.get("output", {})
    browser = navigator.browser
    for fr in result.fields:
        if fr.status in (FieldStatus.MISMATCH, FieldStatus.MISSING_IN_PDF, FieldStatus.MISSING_IN_UI):
            screenshot_path = _mismatch_screenshot_path(output_cfg, doc["id"], fr.field_path)
            try:
                await browser.screenshot(screenshot_path)
                fr.screenshot_path = screenshot_path
            except Exception:
                pass

    # 7. Capture full-page screenshot if any mismatch exists
    if result.has_mismatches:
        screenshots_dir = Path(output_cfg.get("screenshots_dir", "./reports/screenshots"))
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in doc["id"])
        full_path = str(screenshots_dir / f"{safe_id}__full_page.png")
        try:
            await browser.screenshot(full_path)
            result.screenshot_path = full_path
        except Exception:
            pass

    reporter.add_result(result)

    # 8. Collapse document row (skip if single page view)
    if not is_single_page:
        await navigator.collapse_document(doc)

    return {
        "fields_validated": result.total_fields,
        "matches": result.matches,
        "partials": result.partials,
        "mismatches": result.mismatches,
        "missing": result.missing_in_pdf + result.missing_in_ui,
    }


# ======================================================================
# Main async runner
# ======================================================================
async def run(args: argparse.Namespace) -> None:
    # Load config
    config = load_config(args.config)

    # Apply CLI overrides
    if args.headless:
        config.setdefault("browser", {})["headless"] = True
    if args.debug:
        config.setdefault("browser", {})["slow_mo"] = 200
        config.setdefault("browser", {})["headless"] = False
    if args.url:
        # Override the target URL — used by the Chrome extension to validate
        # whichever page the user is currently viewing.
        config.setdefault("app", {})["url"] = args.url
        console.print(f"[cyan]Target URL (from extension): {args.url}[/cyan]")
    if args.manual_pdf:
        config.setdefault("pdf", {})["manual_pdf_path"] = args.manual_pdf
        console.print(f"[cyan]Manual PDF path: {args.manual_pdf}[/cyan]")

    # Load / reset state
    state = RunState.load()
    if args.reset:
        state.reset()
        state = RunState.load()
        console.print("[yellow]Checkpoint cleared. Starting fresh run.[/yellow]")

    start_index = 0
    if args.resume and state.is_resumable():
        start_index = state.last_completed_index + 1
        console.print(
            f"[cyan]Resuming from document index {start_index} "
            f"(last completed: {state.last_completed_doc_id})[/cyan]"
        )
    elif args.start is not None:
        start_index = args.start

    comparator = Comparator(config)
    reporter = Reporter(config, state)

    async with managed_browser(config) as browser:
        # Navigate and login
        await browser.navigate_to_app()
        if not config.get("app", {}).get("authenticated", False):
            try:
                await browser.login()
            except ValueError as exc:
                console.print(f"[red]Login error: {exc}[/red]")
                # Continue — maybe the page doesn't need login

        navigator = DocumentListNavigator(browser)
        ui_extractor = UIExtractor(browser)
        pdf_extractor = PDFExtractor(browser)

        # Discover all documents
        console.print("[bold cyan]Discovering documents on page...[/bold cyan]")
        documents = await navigator.discover_all_documents()
        total = len(documents)

        if total == 0:
            console.print("[yellow]No table/list rows detected. Validating active page directly as single document...[/yellow]")
            documents = [{"index": 0, "id": "current_document", "row_locator_index": 0, "is_single_page": True}]
            total = 1

        state.total_documents = total
        state.start_time = time.time()

        console.print(
            f"[green]Found {total} documents.[/green] "
            f"Processing from index {start_index}"
            + (f" to {args.end}" if args.end is not None else "") + "."
        )

        if args.dry_run:
            console.print("\n[bold yellow]DRY RUN — listing documents:[/bold yellow]")
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Index", style="dim", width=8)
            table.add_column("Document ID")
            for doc in documents:
                table.add_row(str(doc["index"]), doc["id"])
            console.print(table)
            console.print(f"\n[green]Total: {total} documents (dry run, no validation performed).[/green]")
            return

        # Filter range
        end_index = args.end if args.end is not None else total - 1
        documents_to_process = [
            d for d in documents if start_index <= d["index"] <= end_index
        ]

        # Progress bar
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Validating"),
            BarColumn(bar_width=40),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TextColumn("[green]✓{task.fields[matches]}[/green] [red]✗{task.fields[mismatches]}[/red] [yellow]⚠{task.fields[missing]}[/yellow] [red]💥{task.fields[failed]}[/red]"),
            console=console,
        )
        task_id = progress.add_task(
            "docs",
            total=len(documents_to_process),
            matches=0, mismatches=0, missing=0, failed=0,
        )

        agg = {"matches": 0, "mismatches": 0, "missing": 0, "failed": 0}

        with progress:
            for doc in documents_to_process:
                progress.update(
                    task_id,
                    description=f"[bold blue]Doc {doc['index'] + 1}/{total} [{doc['id']}]",
                )

                try:
                    summary = await validate_document(
                        doc=doc,
                        navigator=navigator,
                        ui_extractor=ui_extractor,
                        pdf_extractor=pdf_extractor,
                        comparator=comparator,
                        reporter=reporter,
                        config=config,
                    )
                    agg["matches"] += summary.get("matches", 0)
                    agg["mismatches"] += summary.get("mismatches", 0)
                    agg["missing"] += summary.get("missing", 0)
                    state.mark_completed(doc["index"], doc["id"], summary)

                except Exception as exc:
                    error_msg = f"{type(exc).__name__}: {exc}"
                    if args.debug:
                        traceback.print_exc()
                    console.print(
                        f"\n[red]⚠ Document [{doc['id']}] failed: {error_msg}[/red]"
                    )
                    # Capture failure screenshot
                    try:
                        screenshots_dir = Path(
                            config.get("output", {}).get("screenshots_dir", "./reports/screenshots")
                        )
                        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in doc["id"])
                        fail_path = str(screenshots_dir / f"{safe_id}__FAILED.png")
                        await browser.screenshot(fail_path)
                    except Exception:
                        fail_path = None

                    # Add error result
                    from comparator import ComparisonResult
                    err_result = ComparisonResult(
                        doc_id=doc["id"],
                        doc_index=doc["index"],
                        error=error_msg,
                        screenshot_path=fail_path,
                    )
                    reporter.add_result(err_result)
                    state.mark_failed(doc["index"])
                    agg["failed"] += 1

                    # Try to collapse in case it's still open
                    try:
                        await navigator.collapse_document(doc)
                    except Exception:
                        pass

                finally:
                    progress.update(
                        task_id,
                        advance=1,
                        matches=agg["matches"],
                        mismatches=agg["mismatches"],
                        missing=agg["missing"],
                        failed=agg["failed"],
                    )
                    # Save intermediate reports every 10 documents
                    if (doc["index"] + 1) % 10 == 0:
                        reporter.save_all()

        # Final report save
        reporter.save_all()
        _print_final_summary(reporter.build_summary(), config)


def _print_final_summary(summary: dict, config: dict) -> None:
    out_dir = config.get("output", {}).get("directory", "./reports")
    console.print()
    console.print(Panel.fit(
        f"""[bold]Validation Complete[/bold]

[cyan]Total Documents:[/cyan]    {summary['total_documents_processed']}
[green]Fields Validated:[/green]  {summary['total_fields_validated']}
[green]Matches:[/green]           {summary['total_matches']}
[yellow]Partial:[/yellow]           {summary['total_partials']}
[red]Mismatches:[/red]         {summary['total_mismatches']}
[cyan]Accuracy:[/cyan]          {summary['overall_accuracy']}%
[yellow]Missing Fields:[/yellow]    {summary['total_missing_fields']}
[red]Failed Docs:[/red]        {summary['total_failed_documents']}
[blue]Duration:[/blue]           {summary['processing_time_human']}
[bold green]Success Rate:[/bold green]      {summary['success_rate_percent']}%

[dim]Reports saved to: {out_dir}/[/dim]""",
        title="📋 Summary",
        border_style="cyan",
    ))


# ======================================================================
# Entry
# ======================================================================
if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args))
