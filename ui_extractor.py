"""
ui_extractor.py — Extract Data from 19 UI Sections

For each configured section, reads label→value pairs from the DOM.
Returns a flat dict keyed as "<Section Name> > <Label>".
"""
from __future__ import annotations

import re
from typing import Optional

from playwright.async_api import Page

from browser import BrowserManager


class UIExtractor:
    """Reads all configured UI sections and returns a flat field dictionary."""

    def __init__(self, browser: BrowserManager) -> None:
        self.browser = browser
        self.page: Page = browser.page
        self.cfg = browser.cfg
        self._ui_cfg = browser.cfg.get("ui_sections", {})

    async def extract_all_sections(self) -> dict[str, str]:
        """
        Iterate configured sections and extract label→value pairs.
        If config is missing or returns empty data, run smart auto-extraction.
        """
        sections = self._ui_cfg.get("sections", [])
        flat: dict[str, str] = {}
        errors: list[str] = []

        for section in sections:
            name = section.get("name", "Unknown")
            # Skip placeholders unless it's a real configured selector
            container_sel = section.get("container_selector", "")
            if not container_sel or container_sel in (".section-1", ".section-2"):
                continue

            try:
                section_data = await self._extract_section(section)
                for label, value in section_data.items():
                    if not label.startswith("__"):
                        key = f"{name} > {label}"
                        flat[key] = value
            except Exception as exc:
                errors.append(f"[{name}] extraction failed: {exc}")

        # If configured sections didn't find data, run SMART AUTO-EXTRACTION
        if not flat:
            flat = await self._smart_auto_extract()

        return flat

    async def extract_tables(self) -> list[dict]:
        """
        Extract tables from the UI based on configured table_mappings.
        Returns a list of dicts with mapping info and extracted ui_data.
        """
        table_mappings = self.cfg.get("table_mappings", [])
        if not table_mappings:
            return []
            
        results = []
        for mapping in table_mappings:
            ui_sel = mapping.get("ui_selector")
            if not ui_sel:
                continue
                
            ui_data = []
            try:
                table_loc = self.page.locator(ui_sel).first
                if await table_loc.is_visible():
                    rows = table_loc.locator("tr")
                    row_count = await rows.count()
                    for r_idx in range(row_count):
                        cells = rows.nth(r_idx).locator("td, th")
                        cell_count = await cells.count()
                        row_data = []
                        for c_idx in range(cell_count):
                            text = await cells.nth(c_idx).inner_text()
                            row_data.append(_clean(text))
                        if any(row_data):
                            ui_data.append(row_data)
            except Exception as exc:
                print(f"Failed to extract UI table for {mapping.get('name')}: {exc}")
                
            results.append({
                "name": mapping.get("name", "Unknown Table"),
                "pdf_table_index": mapping.get("pdf_table_index", 0),
                "normalise": mapping.get("normalise", True),
                "ui_data": ui_data
            })
            
        return results

    async def _smart_auto_extract(self) -> dict[str, str]:
        """Auto-detect all visible sections and key-value pairs on the page."""
        result: dict[str, str] = {}
        
        # 0. Karithera <table class="cmp-table"> (Accordion sections)
        try:
            cmp_tables = self.page.locator("table.cmp-table")
            if await cmp_tables.count() > 0 and await cmp_tables.first.is_visible():
                tbodies = cmp_tables.first.locator("tbody")
                tbody_count = await tbodies.count()
                for i in range(tbody_count):
                    tbody = tbodies.nth(i)
                    class_attr = await tbody.get_attribute("class") or ""
                    
                    if "cmp-section-group" in class_attr:
                        # It's an accordion section
                        sec_row = tbody.locator(".cmp-sec-row").first
                        if await sec_row.count() > 0:
                            sec_name_el = sec_row.locator(".cmp-sec-text").first
                            if await sec_name_el.count() > 0:
                                sec_name = _clean(await sec_name_el.inner_text())
                                
                                # Expand if closed
                                row_class = await sec_row.get_attribute("class") or ""
                                if "cmp-sec-open" not in row_class:
                                    try:
                                        await sec_row.click()
                                        await self.page.wait_for_timeout(300)
                                    except Exception:
                                        pass
                                
                                # Read content
                                content_el = tbody.locator(".cmp-content-inner, .cmp-content-cell").first
                                if await content_el.count() > 0 and await content_el.is_visible():
                                    
                                    # Extract inner tables
                                    inner_tables = content_el.locator("table")
                                    has_table = await inner_tables.count() > 0
                                    if has_table:
                                        cells = inner_tables.locator("td, th, .cmp-td, .cmp-th")
                                        cell_cnt = await cells.count()
                                        for c_idx in range(cell_cnt):
                                            c_val = _clean(await cells.nth(c_idx).inner_text())
                                            if c_val:
                                                result[f"{sec_name} > Table Cell {c_idx+1}"] = c_val

                                    # Extract inputs and dropdowns
                                    inputs = content_el.locator("input, select, textarea, mat-select, .mat-select-value")
                                    input_cnt = await inputs.count()
                                    for i_idx in range(input_cnt):
                                        inp = inputs.nth(i_idx)
                                        tag = await inp.evaluate("el => el.tagName.toLowerCase()")
                                        if tag == "select":
                                            val = await inp.evaluate("el => el.options[el.selectedIndex]?.text || ''")
                                        elif tag in ("input", "textarea"):
                                            val = await inp.evaluate("el => el.value || ''")
                                        else:
                                            val = await inp.inner_text()
                                            
                                        val = _clean(val)
                                        if val:
                                            result[f"{sec_name} > Dropdown/Input {i_idx+1}"] = val

                                    # If no table, extract the plain text content too
                                    if not has_table:
                                        text_content = _clean(await content_el.inner_text())
                                        if text_content:
                                            result[f"{sec_name} > Content"] = text_content
                    else:
                        # Basic top-level rows
                        rows = tbody.locator("tr")
                        row_count = await rows.count()
                        for r_i in range(row_count):
                            row = rows.nth(r_i)
                            label_el = row.locator(".cmp-td-label").first
                            val_el = row.locator(".cmp-td-value").first
                            if await label_el.count() > 0 and await val_el.count() > 0:
                                k = _clean(await label_el.inner_text())
                                v = _clean(await val_el.inner_text())
                                if k and v:
                                    result[f"Overview > {k}"] = v
                if result:
                    return result
        except Exception:
            pass

        # 0.5 Karithera <app-comparison> Custom Web Component Tag (Image 2)
        try:
            app_comp = self.page.locator("app-comparison")
            if await app_comp.count() > 0 and await app_comp.first.is_visible():
                rows = app_comp.locator("tr, div[class*='row'], div[class*='grid'] > div, div[class*='item']")
                row_count = await rows.count()
                for i in range(row_count):
                    row = rows.nth(i)
                    if not await row.is_visible():
                        continue
                    cells = row.locator("td, th, div[class*='col'], div[class*='label'], span")
                    cell_count = await cells.count()
                    if cell_count >= 2:
                        k = _clean(await cells.nth(0).inner_text())
                        v = _clean(await cells.nth(1).inner_text())
                        if k and v and len(k) <= 80 and k.lower() != v.lower():
                            result[f"Clinical Review > {k}"] = v

            # Fallback Karithera row matching
            if not result:
                comp_rows = self.page.locator("table tr, div[class*='grid'] > div, div[class*='row']")
                count = await comp_rows.count()
                for i in range(count):
                    row = comp_rows.nth(i)
                    if not await row.is_visible():
                        continue
                    cells = row.locator("td, th, div[class*='col'], div[class*='label'], span")
                    cell_count = await cells.count()
                    if cell_count >= 2:
                        k = _clean(await cells.nth(0).inner_text())
                        v = _clean(await cells.nth(1).inner_text())
                        if k and v and len(k) <= 60 and (
                            k.isupper() or any(term in k.upper() for term in [
                                "PRIORITY", "APPLICATION", "DIVISION", "THERAPEUTIC", "DOSAGE",
                                "DOSING", "PHARMACOLOGIC", "APPROVAL", "SUBMIT", "RECEIVED", "REVIEW"
                            ])
                        ):
                            result[f"Clinical Review > {k}"] = v
        except Exception:
            pass

        # 1. Extract from all visible <table> elements
        try:
            tables = self.page.locator("table")
            table_count = await tables.count()
            for t_idx in range(table_count):
                tbl = tables.nth(t_idx)
                if not await tbl.is_visible():
                    continue
                
                # Check for caption or preceding heading
                caption = f"Table {t_idx+1}"
                try:
                    cap_el = tbl.locator("caption, preceding-sibling::h1, preceding-sibling::h2, preceding-sibling::h3, preceding-sibling::h4").last
                    if await cap_el.count() > 0:
                        caption = _clean(await cap_el.inner_text())
                except Exception:
                    pass

                rows = tbl.locator("tr")
                row_count = await rows.count()
                for r_idx in range(row_count):
                    cells = rows.nth(r_idx).locator("td, th")
                    cell_count = await cells.count()
                    if cell_count >= 2:
                        k = _clean(await cells.nth(0).inner_text())
                        v = _clean(await cells.nth(1).inner_text())
                        if k and v and len(k) < 80:
                            result[f"{caption} > {k}"] = v
        except Exception:
            pass

        # 2. Extract from definition lists <dl>, <dt>, <dd>
        try:
            dls = self.page.locator("dl")
            dl_count = await dls.count()
            for d_idx in range(dl_count):
                dl = dls.nth(d_idx)
                if not await dl.is_visible():
                    continue
                dts = await dl.locator("dt").all_inner_texts()
                dds = await dl.locator("dd").all_inner_texts()
                for dt_text, dd_text in zip(dts, dds):
                    k = _clean(dt_text)
                    v = _clean(dd_text)
                    if k and v:
                        result[f"Details > {k}"] = v
        except Exception:
            pass

        # 3. Extract label/input or label/span pairs
        try:
            labels = self.page.locator("label")
            label_count = await labels.count()
            for l_idx in range(min(label_count, 50)):
                lbl = labels.nth(l_idx)
                if not await lbl.is_visible():
                    continue
                k = _clean(await lbl.inner_text())
                if not k or len(k) > 60:
                    continue

                # Find associated input or sibling text
                v = ""
                for_id = await lbl.get_attribute("for")
                if for_id:
                    input_el = self.page.locator(f"#{for_id}").first
                    if await input_el.count() > 0:
                        v = await input_el.input_value() if await input_el.evaluate("el => 'value' in el") else await input_el.inner_text()
                
                if not v:
                    # Next sibling or child text
                    try:
                        next_el = lbl.locator("+ input, + select, + textarea, + span, + div").first
                        if await next_el.count() > 0:
                            v = await next_el.inner_text()
                    except Exception:
                        pass

                v = _clean(v)
                if k and v:
                    result[f"Document Details > {k}"] = v
        except Exception:
            pass

        # 4. Extract colon-separated text lines (e.g. "Invoice #: 12345")
        if not result:
            try:
                body_text = await self.page.inner_text("body")
                for line in body_text.split("\n"):
                    if ":" in line:
                        parts = line.split(":", 1)
                        k = _clean(parts[0])
                        v = _clean(parts[1])
                        if k and v and 2 <= len(k) <= 40 and len(v) <= 100:
                            result[f"General > {k}"] = v
            except Exception:
                pass

        return result

    async def _extract_section(self, section_cfg: dict) -> dict[str, str]:
        """
        Extract label→value pairs from a single section.

        Strategy (in order of priority):
        1. label_selector + value_selector siblings
        2. table rows (tr > td pairs)
        3. definition list (dt / dd pairs)
        4. Fallback: capture all visible text
        """
        container_sel = section_cfg.get("container_selector", "")
        label_sel = section_cfg.get("label_selector", "")
        value_sel = section_cfg.get("value_selector", "")

        if not container_sel:
            return {}

        # Confirm the container is visible
        try:
            await self.page.wait_for_selector(container_sel, state="visible", timeout=5000)
        except Exception:
            return {"__status__": "container_not_visible"}

        # Try configured label/value selectors
        if label_sel and value_sel:
            result = await self._extract_by_label_value(container_sel, label_sel, value_sel)
            if result:
                return result

        # Try table rows (th/td or td/td)
        result = await self._extract_table_rows(container_sel)
        if result:
            return result

        # Try definition list
        result = await self._extract_definition_list(container_sel)
        if result:
            return result

        # Last resort: raw text
        raw = await self._extract_raw_text(container_sel)
        return {"__raw__": raw} if raw else {}

    async def _extract_by_label_value(
        self, container: str, label_sel: str, value_sel: str
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        try:
            labels = await self.page.locator(f"{container} {label_sel}").all_inner_texts()
            values = await self.page.locator(f"{container} {value_sel}").all_inner_texts()
        except Exception:
            return result

        for label, value in zip(labels, values):
            label_clean = _clean(label)
            value_clean = _clean(value)
            if label_clean:
                result[label_clean] = value_clean
        return result

    async def _extract_table_rows(self, container: str) -> dict[str, str]:
        result: dict[str, str] = {}
        try:
            rows = self.page.locator(f"{container} tr")
            count = await rows.count()
            for i in range(count):
                cells = rows.nth(i).locator("td, th")
                cell_count = await cells.count()
                if cell_count >= 2:
                    label = _clean(await cells.nth(0).inner_text())
                    value = _clean(await cells.nth(1).inner_text())
                    if label:
                        result[label] = value
        except Exception:
            pass
        return result

    async def _extract_definition_list(self, container: str) -> dict[str, str]:
        result: dict[str, str] = {}
        try:
            terms = await self.page.locator(f"{container} dt").all_inner_texts()
            defs = await self.page.locator(f"{container} dd").all_inner_texts()
            for term, definition in zip(terms, defs):
                label = _clean(term)
                if label:
                    result[label] = _clean(definition)
        except Exception:
            pass
        return result

    async def _extract_raw_text(self, container: str) -> str:
        try:
            return _clean(await self.page.inner_text(container))
        except Exception:
            return ""


def _clean(text: str) -> str:
    """Normalise whitespace and strip punctuation used as separators."""
    text = re.sub(r"\s+", " ", text).strip()
    text = text.rstrip(":").strip()
    return text
