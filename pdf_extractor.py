"""
pdf_extractor.py — Extract Text and Fields from Embedded PDF

Supports two strategies (configured in config.yaml → pdf.strategy):
  - "pdfjs_dom"   : Reads text directly from the PDF.js .textLayer spans in the DOM
  - "iframe_src"  : Downloads the PDF via its <iframe src="..."> URL and parses with pdfplumber
  - "auto"        : Tries pdfjs_dom first; falls back to iframe_src
"""
from __future__ import annotations

import io
import re
from typing import Optional

import pdfplumber
from playwright.async_api import Page

from browser import BrowserManager


class PDFExtractor:
    """Reads the embedded PDF viewer and extracts fields via configured regexes."""

    def __init__(self, browser: BrowserManager) -> None:
        self.browser = browser
        self.page: Page = browser.page
        self.cfg = browser.cfg
        self._pdf_cfg = browser.cfg.get("pdf", {})
        self._timeouts = browser.cfg.get("app", {}).get("timeouts", {})

    async def extract(self) -> dict[str, str]:
        """
        Main entry point. Returns a dict of field values extracted from the PDF.
        Supports:
          0. Manually provided local PDF file
          1. PDFs opened in a new tab via a PDF button/link
          2. Embedded PDF.js DOM viewers
          3. Embedded PDF iframe downloads
        """
        strategy = self._pdf_cfg.get("strategy", "auto")
        raw_text = ""

        # 0. Check for manually uploaded local PDF file
        manual_path = self._pdf_cfg.get("manual_pdf_path", "")
        if manual_path and Path(manual_path).exists():
            try:
                with pdfplumber.open(manual_path) as pdf:
                    pages_text = [p.extract_text() for p in pdf.pages if p.extract_text()]
                    raw_text = "\n".join(pages_text)
            except Exception as e:
                return {"__pdf_error__": f"Failed to read manual PDF: {e}"}

        # 1. Try New Tab / Popup PDF button if no manual PDF
        if not raw_text.strip():
            raw_text = await self._extract_new_tab_pdf()

        # 2. Fall back to embedded PDF strategies if no new tab PDF
        if not raw_text.strip():
            if strategy == "pdfjs_dom":
                raw_text = await self._extract_pdfjs_dom()
            elif strategy == "iframe_src":
                raw_text = await self._extract_iframe_src()
            else:  # auto
                raw_text = await self._extract_pdfjs_dom()
                if not raw_text.strip():
                    raw_text = await self._extract_iframe_src()

        if not raw_text.strip():
            return {"__pdf_error__": "No text extracted from PDF"}

        result = self._apply_field_mappings(raw_text)
        result["__raw__"] = raw_text
        return result

    async def get_raw_text(self) -> str:
        """Return all raw text from the PDF (useful for debugging selectors)."""
        strategy = self._pdf_cfg.get("strategy", "auto")
        if strategy == "pdfjs_dom":
            return await self._extract_pdfjs_dom()
        elif strategy == "iframe_src":
            return await self._extract_iframe_src()
        text = await self._extract_pdfjs_dom()
        if not text.strip():
            text = await self._extract_iframe_src()
        return text

    # ------------------------------------------------------------------
    # Strategy 0: PDF button opening a NEW TAB / Popup
    # ------------------------------------------------------------------
    async def _extract_new_tab_pdf(self) -> str:
        pdf_button_candidates = [
            "a[href*='.pdf']",
            "button:has-text('PDF')",
            "a:has-text('PDF')",
            "a[target='_blank']",
            "[title*='PDF']",
            "[aria-label*='PDF']",
            ".pdf-btn",
            ".pdf-link",
            ".icon-pdf",
            "[class*='pdf']",
        ]

        for sel in pdf_button_candidates:
            try:
                btn = self.page.locator(sel).first
                if await btn.count() == 0 or not await btn.is_visible():
                    continue

                # Check if href is a direct PDF link
                href = await btn.get_attribute("href")
                if href and href.lower().endswith(".pdf"):
                    full_url = href if href.startswith("http") else f"{self.page.url.rsplit('/', 1)[0]}/{href.lstrip('/')}"
                    res = await self.page.request.get(full_url)
                    if res.ok:
                        parsed = _parse_pdf_bytes(await res.body())
                        if parsed and not parsed.startswith("__"):
                            return parsed

                # Otherwise click and capture the new tab / popup
                try:
                    async with self.page.context.expect_page(timeout=5000) as page_info:
                        await btn.click()
                    new_page: Page = await page_info.value
                    await new_page.wait_for_load_state("domcontentloaded")
                    await asyncio.sleep(1.0)

                    raw_text = ""
                    # Check if new tab has direct PDF bytes or PDF.js spans
                    new_url = new_page.url
                    if new_url.lower().endswith(".pdf") or "pdf" in new_url.lower():
                        res = await new_page.request.get(new_url)
                        if res.ok:
                            raw_text = _parse_pdf_bytes(await res.body())

                    if not raw_text or raw_text.startswith("__"):
                        # Extract DOM text spans from new page
                        try:
                            spans = await new_page.locator(".textLayer span, .page span, span, body").all_inner_texts()
                            raw_text = " ".join(s.strip() for s in spans if s.strip())
                        except Exception:
                            pass

                    # Close the new tab and switch back
                    await new_page.close()
                    if raw_text.strip():
                        return raw_text
                except Exception:
                    pass
            except Exception:
                continue

        return ""
    async def _extract_pdfjs_dom(self) -> str:
        iframe_sel = self._pdf_cfg.get("iframe_selector", "")
        text_sel = self._pdf_cfg.get("pdfjs_text_selector", ".page .textLayer span, .textLayer span, span")
        pdf_loaded = self._pdf_cfg.get("pdf_loaded_indicator", ".page, canvas")
        timeout = self._timeouts.get("pdf_load", 10000)

        # Candidate iframe selectors if configured selector fails or is placeholder
        iframe_candidates = [iframe_sel] if iframe_sel and iframe_sel != "iframe.pdf-viewer" else []
        iframe_candidates.extend(["iframe", "embed", "object", "[src*='pdf']", "[data*='pdf']"])

        for candidate in iframe_candidates:
            if not candidate:
                continue
            try:
                iframe_el = self.page.locator(candidate).first
                if await iframe_el.count() == 0:
                    continue
                frame = await iframe_el.content_frame()
                if frame is None:
                    continue
                spans = await frame.locator(text_sel).all_inner_texts()
                text = " ".join(s.strip() for s in spans if s.strip())
                if text.strip():
                    return text
            except Exception:
                continue

        # Try main page PDF.js spans directly
        try:
            spans = await self.page.locator(".textLayer span, .page span").all_inner_texts()
            text = " ".join(s.strip() for s in spans if s.strip())
            if text.strip():
                return text
        except Exception:
            pass

        return ""

    # ------------------------------------------------------------------
    # Strategy 2: Download PDF via iframe src + pdfplumber
    # ------------------------------------------------------------------
    async def _extract_iframe_src(self) -> str:
        iframe_sel = self._pdf_cfg.get("iframe_selector", "iframe")
        timeout = self._timeouts.get("pdf_load", 10000)

        candidates = [iframe_sel] if iframe_sel and iframe_sel != "iframe.pdf-viewer" else []
        candidates.extend(["iframe[src*='pdf']", "iframe", "embed", "object"])

        for candidate in candidates:
            try:
                iframe_el = self.page.locator(candidate).first
                if await iframe_el.count() == 0:
                    continue
                src = await iframe_el.get_attribute("src") or await iframe_el.get_attribute("data")
                if not src:
                    continue

                if not src.startswith("http"):
                    base = self.page.url.rsplit("/", 1)[0]
                    src = f"{base}/{src.lstrip('/')}"

                response = await self.page.request.get(src)
                if not response.ok:
                    continue

                pdf_bytes = await response.body()
                parsed = _parse_pdf_bytes(pdf_bytes)
                if parsed and not parsed.startswith("__"):
                    return parsed
            except Exception:
                continue

        return ""

    # ------------------------------------------------------------------
    # Field extraction via regex mappings
    # ------------------------------------------------------------------
    def _apply_field_mappings(self, raw_text: str) -> dict[str, str]:
        """Apply all configured regex patterns to the raw PDF text."""
        mappings = self.cfg.get("field_mappings", [])
        result: dict[str, str] = {}

        for mapping in mappings:
            ui_path = mapping.get("ui_path", "")
            pattern = mapping.get("pdf_regex", "")
            if not ui_path or not pattern:
                continue
            try:
                match = re.search(pattern, raw_text, re.IGNORECASE | re.DOTALL)
                if match:
                    result[ui_path] = match.group(1).strip()
                else:
                    result[ui_path] = ""  # field not found in PDF
            except re.error as exc:
                result[ui_path] = f"__regex_error__{exc}"

        return result

    async def extract_tables(self) -> list[list[list[str]]]:
        """Extract all tables from the PDF using pdfplumber."""
        pdf_bytes = None
        
        # 1. Manual PDF
        manual_path = self._pdf_cfg.get("manual_pdf_path", "")
        if manual_path and Path(manual_path).exists():
            with open(manual_path, "rb") as f:
                pdf_bytes = f.read()
                
        # 2. Iframe src fallback
        if not pdf_bytes:
            iframe_sel = self._pdf_cfg.get("iframe_selector", "iframe")
            candidates = [iframe_sel] if iframe_sel and iframe_sel != "iframe.pdf-viewer" else []
            candidates.extend(["iframe[src*='pdf']", "iframe", "embed", "object"])
            
            for candidate in candidates:
                try:
                    iframe_el = self.page.locator(candidate).first
                    if await iframe_el.count() == 0:
                        continue
                    src = await iframe_el.get_attribute("src") or await iframe_el.get_attribute("data")
                    if not src:
                        continue
                    if not src.startswith("http"):
                        base = self.page.url.rsplit("/", 1)[0]
                        src = f"{base}/{src.lstrip('/')}"
                    response = await self.page.request.get(src)
                    if response.ok:
                        pdf_bytes = await response.body()
                        break
                except Exception:
                    continue
                    
        if pdf_bytes:
            return _parse_pdf_bytes_for_tables(pdf_bytes)
        return []

def _parse_pdf_bytes(pdf_bytes: bytes) -> str:
    """Use pdfplumber to extract all text from PDF bytes."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            return "\n".join(pages_text)
    except Exception as exc:
        return f"__pdfplumber_error__{exc}"

def _parse_pdf_bytes_for_tables(pdf_bytes: bytes) -> list[list[list[str]]]:
    """Use pdfplumber to extract all tables from PDF bytes. Returns a list of tables (list of rows (list of cells))."""
    tables = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                for table in page_tables:
                    # Clean up the table (replace None with empty string, strip whitespace)
                    cleaned_table = []
                    for row in table:
                        cleaned_row = [str(cell).strip() if cell is not None else "" for cell in row]
                        # skip completely empty rows
                        if any(cleaned_row):
                            cleaned_table.append(cleaned_row)
                    if cleaned_table:
                        tables.append(cleaned_table)
    except Exception:
        pass
    return tables
