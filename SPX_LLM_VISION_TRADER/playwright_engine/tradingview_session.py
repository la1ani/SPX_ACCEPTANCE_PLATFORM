from __future__ import annotations

import os
from pathlib import Path
from playwright.async_api import async_playwright, BrowserContext, Page, Playwright


class TradingViewSession:
    def __init__(self, tradingview_url: str, profile_dir: str | Path, headless: bool = False):
        self.tradingview_url = tradingview_url
        self.profile_dir = Path(profile_dir)
        self.headless = headless
        self._playwright: Playwright | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self) -> Page:
        if not self.tradingview_url:
            raise RuntimeError("TRADINGVIEW_URL is missing in .env")
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()

        launch_kwargs = {
            "user_data_dir": str(self.profile_dir),
            "headless": self.headless,
            "viewport": {"width": 1600, "height": 1000},
            "args": ["--start-maximized"],
        }

        # First try Playwright's bundled Chromium. If the browser download failed
        # because of CDN timeout, fall back to installed Chrome or Edge on Windows.
        channel_candidates: list[str | None] = [None]
        env_channel = os.getenv("BROWSER_CHANNEL", "").strip()
        if env_channel:
            channel_candidates.append(env_channel)
        channel_candidates.extend(["chrome", "msedge"])

        errors: list[str] = []
        for channel in channel_candidates:
            try:
                kwargs = dict(launch_kwargs)
                if channel:
                    kwargs["channel"] = channel
                self.context = await self._playwright.chromium.launch_persistent_context(**kwargs)
                break
            except Exception as exc:  # noqa: BLE001 - collect all browser fallback errors
                label = channel or "bundled chromium"
                errors.append(f"{label}: {exc}")
        else:
            raise RuntimeError(
                "Could not start a browser. Either install Google Chrome / Microsoft Edge, "
                "or run: python -m playwright install chromium\n\n"
                + "\n\n".join(errors[-3:])
            )

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.page.goto(self.tradingview_url, wait_until="domcontentloaded", timeout=90000)
        await self.page.wait_for_timeout(3000)
        return self.page

    async def stop(self) -> None:
        if self.context:
            await self.context.close()
        if self._playwright:
            await self._playwright.stop()
