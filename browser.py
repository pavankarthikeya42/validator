"""
browser.py — Playwright Browser Lifecycle and Login Helper

Provides:
  - async context manager that launches/closes the browser
  - login() helper that handles the username/password flow
  - reusable page helpers (wait_for, safe_click, scroll_to_bottom, etc.)
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)


class BrowserManager:
    """Manages a single Playwright browser instance for the validation run."""

    def __init__(self, config: dict) -> None:
        self.cfg = config
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def start(self) -> "BrowserManager":
        app_cfg = self.cfg.get("app", {})
        browser_cfg = self.cfg.get("browser", {})
        timeouts = app_cfg.get("timeouts", {})

        self._playwright = await async_playwright().start()
        launch_opts: dict = {
            "headless": browser_cfg.get("headless", False),
            "slow_mo": browser_cfg.get("slow_mo", 0),
        }

        user_data_dir = browser_cfg.get("user_data_dir", "").strip()
        if user_data_dir:
            # Persistent context reuses cookies/session from an existing Chrome profile
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir,
                **launch_opts,
                viewport={
                    "width": browser_cfg.get("viewport_width", 1920),
                    "height": browser_cfg.get("viewport_height", 1080),
                },
            )
            self.page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        else:
            self._browser = await self._playwright.chromium.launch(**launch_opts)
            self._context = await self._browser.new_context(
                viewport={
                    "width": browser_cfg.get("viewport_width", 1920),
                    "height": browser_cfg.get("viewport_height", 1080),
                },
            )
            self.page = await self._context.new_page()

        self.page.set_default_timeout(timeouts.get("element_visible", 15000))
        return self

    async def stop(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    # ------------------------------------------------------------------
    # Navigation & Login
    # ------------------------------------------------------------------
    async def navigate_to_app(self) -> None:
        app_cfg = self.cfg.get("app", {})
        url = app_cfg.get("url", "")
        if not url:
            raise ValueError("config.yaml: app.url is empty — please set it.")
        await self.page.goto(url, wait_until="domcontentloaded")
        title_fragment = app_cfg.get("title_contains", "")
        if title_fragment:
            title = await self.page.title()
            if title_fragment.lower() not in title.lower():
                raise RuntimeError(
                    f"Page title '{title}' does not contain '{title_fragment}'. "
                    "Wrong page or login redirect."
                )

    async def login(self) -> None:
        """Perform username/password login if not already authenticated."""
        app_cfg = self.cfg.get("app", {})
        if app_cfg.get("authenticated", False):
            return  # trust that existing session is valid

        login_cfg = app_cfg.get("login", {})
        username = login_cfg.get("username") or os.environ.get("VALIDATOR_USER", "")
        password = login_cfg.get("password") or os.environ.get("VALIDATOR_PASS", "")

        if not username or not password:
            raise ValueError(
                "Credentials missing. Set app.login.username/password in config.yaml "
                "or VALIDATOR_USER / VALIDATOR_PASS environment variables."
            )

        await self.page.fill(login_cfg["username_selector"], username)
        await self.page.fill(login_cfg["password_selector"], password)
        await self.page.click(login_cfg["submit_selector"])

        success_sel = login_cfg.get("success_selector", "")
        if success_sel:
            await self.page.wait_for_selector(success_sel, state="visible")

    # ------------------------------------------------------------------
    # Page helpers
    # ------------------------------------------------------------------
    async def wait_for(self, selector: str, timeout: Optional[int] = None) -> None:
        opts = {"state": "visible"}
        if timeout is not None:
            opts["timeout"] = timeout
        await self.page.wait_for_selector(selector, **opts)

    async def safe_click(self, selector: str, timeout: Optional[int] = None) -> None:
        """Click an element; scroll it into view first."""
        locator = self.page.locator(selector).first
        await locator.scroll_into_view_if_needed()
        await locator.click(timeout=timeout)

    async def scroll_to_bottom(self) -> None:
        """Scroll the page to the very bottom."""
        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

    async def scroll_element_to_bottom(self, container_selector: str) -> None:
        """Scroll a specific scrollable element to its bottom."""
        await self.page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (el) el.scrollTop = el.scrollHeight;
            }""",
            container_selector,
        )

    async def get_text(self, selector: str) -> str:
        try:
            return (await self.page.inner_text(selector)).strip()
        except Exception:
            return ""

    async def screenshot(self, path: str) -> None:
        await self.page.screenshot(path=path, full_page=False)

    async def screenshot_element(self, selector: str, path: str) -> None:
        try:
            el = self.page.locator(selector).first
            await el.screenshot(path=path)
        except Exception:
            await self.screenshot(path)


@asynccontextmanager
async def managed_browser(config: dict) -> AsyncGenerator[BrowserManager, None]:
    """Async context manager for the browser lifecycle."""
    mgr = BrowserManager(config)
    await mgr.start()
    try:
        yield mgr
    finally:
        await mgr.stop()
