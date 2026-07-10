from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright


class TradingViewSession:
    def __init__(self, tradingview_url: str, profile_dir: str | Path, headless: bool = False):
        self.tradingview_url = tradingview_url
        self.profile_dir = Path(profile_dir)
        self.headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._using_cdp = False
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def _windows_chrome_candidates(self) -> list[Path]:
        explicit = os.getenv("CHROME_EXE", "").strip()
        candidates: list[Path] = []
        if explicit:
            candidates.append(Path(explicit))
        candidates.extend(
            [
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            ]
        )
        return candidates

    def _start_debug_chrome_if_needed(self) -> None:
        if os.name != "nt":
            return

        profile = os.getenv(
            "CHROME_DEBUG_PROFILE",
            r"C:\chrome-debug-profile",
        ).strip()
        port = os.getenv("CHROME_DEBUG_PORT", "9222").strip() or "9222"

        for chrome_exe in self._windows_chrome_candidates():
            if not chrome_exe.exists():
                continue
            print(f"Starting Chrome debug session: {chrome_exe}")
            subprocess.Popen(
                [
                    str(chrome_exe),
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={profile}",
                    "--start-maximized",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            return

    async def _connect_over_cdp_with_retry(self, cdp_url: str) -> Browser:
        attempts = int(os.getenv("CDP_CONNECT_ATTEMPTS", "12"))
        delay_seconds = float(os.getenv("CDP_CONNECT_RETRY_SECONDS", "2"))
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                if attempt > 1:
                    print(f"Retrying Chrome CDP connection ({attempt}/{attempts})...")
                return await self._playwright.chromium.connect_over_cdp(cdp_url)  # type: ignore[union-attr]
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt == 1:
                    print(f"Chrome CDP connection failed once: {exc}")
                    print("Trying to start/recover the Chrome debug session automatically...")
                    self._start_debug_chrome_if_needed()
                if attempt < attempts:
                    await asyncio.sleep(delay_seconds)

        raise RuntimeError(
            f"Could not connect to Chrome CDP at {cdp_url} after {attempts} attempts. "
            f"Last error: {last_error}"
        ) from last_error

    async def start(self) -> Page:
        if not self.tradingview_url:
            raise RuntimeError("TRADINGVIEW_URL is missing in .env")
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()

        cdp_url = os.getenv("BROWSER_CDP_URL", "").strip()
        if cdp_url:
            # Best path for Google sign-in: user opens normal Chrome manually,
            # signs into TradingView with Google, then the bot attaches to that
            # already-open Chrome instead of launching an automation browser.
            print(f"Connecting to existing Chrome: {cdp_url}")
            self._using_cdp = True
            self._browser = await self._connect_over_cdp_with_retry(cdp_url)
            self.context = self._browser.contexts[0] if self._browser.contexts else await self._browser.new_context()
            pages = self.context.pages
            self.page = next((p for p in pages if "tradingview.com" in p.url.lower()), pages[0] if pages else await self.context.new_page())
            await self.page.goto(self.tradingview_url, wait_until="domcontentloaded", timeout=90000)
            await self.page.wait_for_timeout(3000)
            return self.page

        launch_kwargs = {
            "user_data_dir": str(self.profile_dir),
            "headless": self.headless,
            "viewport": {"width": 1600, "height": 1000},
            "args": [
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
        }

        # Prefer the installed normal Google Chrome browser. Google sign-in is often
        # blocked in Playwright's bundled "Chrome for Testing" browser. Use .env
        # BROWSER_CHANNEL=msedge if you want Edge instead, or BROWSER_CHANNEL=chromium
        # to force Playwright's bundled browser.
        env_channel = os.getenv("BROWSER_CHANNEL", "chrome").strip().lower()
        if env_channel in {"", "chrome"}:
            channel_candidates: list[str | None] = ["chrome", "msedge", None]
        elif env_channel in {"chromium", "bundled", "playwright"}:
            channel_candidates = [None, "chrome", "msedge"]
        else:
            channel_candidates = [env_channel, "chrome", "msedge", None]

        # Remove duplicates while preserving order.
        unique_candidates: list[str | None] = []
        for channel in channel_candidates:
            if channel not in unique_candidates:
                unique_candidates.append(channel)

        errors: list[str] = []
        for channel in unique_candidates:
            try:
                kwargs = dict(launch_kwargs)
                if channel:
                    kwargs["channel"] = channel
                self.context = await self._playwright.chromium.launch_persistent_context(**kwargs)
                label = channel or "bundled chromium"
                print(f"Browser started with: {label}")
                break
            except Exception as exc:  # noqa: BLE001 - collect all browser fallback errors
                label = channel or "bundled chromium"
                errors.append(f"{label}: {exc}")
        else:
            raise RuntimeError(
                "Could not start a browser. Install Google Chrome / Microsoft Edge, "
                "or set BROWSER_CHANNEL=chromium and run: python -m playwright install chromium\n\n"
                + "\n\n".join(errors[-3:])
            )

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.page.goto(self.tradingview_url, wait_until="domcontentloaded", timeout=90000)
        await self.page.wait_for_timeout(3000)
        return self.page

    async def stop(self) -> None:
        # If attached to manually-opened Chrome via BROWSER_CDP_URL, do not close
        # that Chrome window. Just stop Playwright control.
        if self.context and not self._using_cdp:
            await self.context.close()
        if self._playwright:
            await self._playwright.stop()
