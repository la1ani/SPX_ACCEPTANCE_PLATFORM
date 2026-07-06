from __future__ import annotations

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
        self.context = await self._playwright.chromium.launch_persistent_context(user_data_dir=str(self.profile_dir), headless=self.headless, viewport={"width": 1600, "height": 1000}, args=["--start-maximized"])
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.page.goto(self.tradingview_url, wait_until="domcontentloaded", timeout=90000)
        await self.page.wait_for_timeout(3000)
        return self.page

    async def stop(self) -> None:
        if self.context:
            await self.context.close()
        if self._playwright:
            await self._playwright.stop()
