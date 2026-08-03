"""
document_list.py — Document List Navigation

Responsibilities:
  - Detect all document rows (handles infinite scroll and load-more pagination)
  - Expand a specific row and wait until all content is loaded
  - Collapse a row after processing
  - Return stable document IDs for checkpointing
"""
from __future__ import annotations

import asyncio
from typing import Optional

from playwright.async_api import Page

from browser import BrowserManager


class DocumentListNavigator:
    """Navigates and controls the collapsed document list."""

    def __init__(self, browser: BrowserManager) -> None:
        self.browser = browser
        self.page: Page = browser.page
        self.cfg = browser.cfg
        self._list_cfg = browser.cfg.get("document_list", {})
        self._timeouts = browser.cfg.get("app", {}).get("timeouts", {})

    # ------------------------------------------------------------------
    # Discovery: find all document rows
    # ------------------------------------------------------------------
    async def discover_all_documents(self) -> list[dict]:
        """
        Load the complete document list (handling pagination / infinite scroll)
        and return metadata for every row.

        Returns a list of dicts:
            { "index": int, "id": str, "row_locator_index": int }
        """
        pagination = self._list_cfg.get("pagination", {})
        ptype = pagination.get("type", "none")

        if ptype == "infinite_scroll":
            await self._load_all_via_scroll(pagination)
        elif ptype == "load_more":
            await self._load_all_via_load_more(pagination)
        # else: all rows already present in DOM

        return await self._collect_row_metadata()

    async def _load_all_via_scroll(self, pagination: dict) -> None:
        container_sel = self._list_cfg.get("container_selector", "body")
        pause_ms = pagination.get("scroll_pause_ms", 1500)
        stable_threshold = pagination.get("stable_after_attempts", 3)
        stable_count = 0
        previous_count = -1

        while stable_count < stable_threshold:
            await self.browser.scroll_element_to_bottom(container_sel)
            await asyncio.sleep(pause_ms / 1000)
            current_count = await self._count_rows()
            if current_count == previous_count:
                stable_count += 1
            else:
                stable_count = 0
            previous_count = current_count

    async def _load_all_via_load_more(self, pagination: dict) -> None:
        load_more_sel = pagination.get("load_more_selector", ".load-more-btn")
        pause_ms = pagination.get("scroll_pause_ms", 1500)

        while True:
            try:
                btn = self.page.locator(load_more_sel)
                if not await btn.is_visible(timeout=2000):
                    break
                await btn.click()
                await asyncio.sleep(pause_ms / 1000)
            except Exception:
                break  # button gone — list fully loaded

    async def _get_active_row_selector(self) -> str:
        """Return configured row selector if it matches elements, else auto-detect."""
        configured = self._list_cfg.get("row_selector", ".document-row")
        try:
            if await self.page.locator(configured).count() > 0:
                return configured
        except Exception:
            pass

        # Auto-detection fallbacks
        fallbacks = [
            "tbody tr",
            "table tr",
            "[role='row']",
            ".document-row",
            ".doc-row",
            "tr.row",
            "div.row",
            ".table-row",
            ".data-row",
            ".item-row",
            "li.list-group-item",
            ".card",
            "article",
            ".item",
        ]
        for sel in fallbacks:
            try:
                count = await self.page.locator(sel).count()
                if count > 0:
                    return sel
            except Exception:
                continue

        return configured

    async def _count_rows(self) -> int:
        row_sel = await self._get_active_row_selector()
        return await self.page.locator(row_sel).count()

    async def _collect_row_metadata(self) -> list[dict]:
        row_sel = await self._get_active_row_selector()
        id_sel = self._list_cfg.get("row_id_selector", "")
        count = await self.page.locator(row_sel).count()
        docs: list[dict] = []
        for i in range(count):
            row = self.page.locator(row_sel).nth(i)
            doc_id = ""
            if id_sel:
                try:
                    id_el = row.locator(id_sel).first
                    doc_id = (await id_el.inner_text()).strip()
                except Exception:
                    pass
            
            if not doc_id:
                # Auto-detect ID from row text or first cell/link
                try:
                    first_cell = row.locator("td, th, a, .id, [class*='id'], [class*='number'], [class*='code']").first
                    doc_id = (await first_cell.inner_text()).strip()
                    doc_id = doc_id.split("\n")[0].strip()
                except Exception:
                    pass

            if not doc_id:
                doc_id = f"doc_{i+1}"
            docs.append({"index": i, "id": doc_id, "row_locator_index": i})
        return docs

    # ------------------------------------------------------------------
    # Expand / Collapse
    # ------------------------------------------------------------------
    async def expand_document(self, doc: dict) -> None:
        """
        Scroll the row into view and click its expand trigger.
        Waits for the expanded indicator to appear before returning.
        """
        row_sel = await self._get_active_row_selector()
        expand_sel = self._list_cfg.get("expand_trigger_selector", "")
        expanded_indicator = self._list_cfg.get("expanded_indicator_selector", "")
        timeout = self._timeouts.get("section_load", 20000)

        row_locator = self.page.locator(row_sel).nth(doc["row_locator_index"])
        await row_locator.scroll_into_view_if_needed()

        clicked = False
        if expand_sel:
            try:
                trigger = row_locator.locator(expand_sel).first
                if await trigger.is_visible():
                    await trigger.click()
                    clicked = True
            except Exception:
                pass

        if not clicked:
            # Auto-detect expand trigger inside row
            trigger_candidates = [
                "button",
                "a",
                "[role='button']",
                "[data-toggle]",
                ".expand",
                ".toggle",
                ".arrow",
                ".chevron",
                "svg",
                "td:first-child",
            ]
            for candidate in trigger_candidates:
                try:
                    el = row_locator.locator(candidate).first
                    if await el.is_visible():
                        await el.click()
                        clicked = True
                        break
                except Exception:
                    continue

        if not clicked:
            # Fallback: click anywhere on the row
            try:
                await row_locator.click()
            except Exception:
                pass

        if expanded_indicator:
            try:
                await row_locator.locator(expanded_indicator).wait_for(
                    state="visible", timeout=timeout
                )
            except Exception:
                await asyncio.sleep(1.0)
        else:
            await asyncio.sleep(1.0)

    async def collapse_document(self, doc: dict) -> None:
        """Collapse or close the currently expanded document detail view / modal."""
        row_sel = await self._get_active_row_selector()
        collapse_sel = self._list_cfg.get("collapse_trigger_selector", "")

        # 1. Try explicit configured collapse selector
        if collapse_sel:
            try:
                row_locator = self.page.locator(row_sel).nth(doc["row_locator_index"])
                trigger = row_locator.locator(collapse_sel).first
                if await trigger.is_visible():
                    await trigger.click()
                    await asyncio.sleep(0.5)
                    return
            except Exception:
                pass

        # 2. Check for open modal, drawer, or detail overlay close buttons
        close_candidates = [
            ".modal .close",
            ".modal .btn-close",
            "[aria-label='Close']",
            "button:has-text('Close')",
            "button:has-text('Back')",
            "a:has-text('Back')",
            ".drawer-close",
            ".side-panel-close",
            ".icon-close",
            "button.close",
        ]
        for sel in close_candidates:
            try:
                btn = self.page.locator(sel).first
                if await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(0.5)
                    return
            except Exception:
                continue

        # 3. Fallback: click document row again (accordion toggle)
        try:
            row_locator = self.page.locator(row_sel).nth(doc["row_locator_index"])
            await row_locator.click()
            await asyncio.sleep(0.5)
        except Exception:
            pass

    async def wait_for_all_sections(self) -> None:
        """Wait until all 19 UI sections signal they are loaded."""
        ui_cfg = self.browser.cfg.get("ui_sections", {})
        indicator = ui_cfg.get("all_loaded_indicator", "")
        timeout = self._timeouts.get("section_load", 20000)

        if indicator:
            await self.page.wait_for_selector(
                indicator, state="visible", timeout=timeout
            )
        else:
            # Fall back: wait for each section container to be visible
            sections = ui_cfg.get("sections", [])
            for section in sections:
                sel = section.get("container_selector", "")
                if sel:
                    try:
                        await self.page.wait_for_selector(
                            sel, state="visible", timeout=timeout
                        )
                    except Exception:
                        pass  # section might not always be present — don't abort
