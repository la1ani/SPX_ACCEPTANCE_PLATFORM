from __future__ import annotations

from datetime import datetime
from pathlib import Path
from playwright.async_api import Page


class ChartCapture:
    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.screenshot_dir = self.output_dir / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    async def capture(self, page: Page, prefix: str = "chart") -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = self.screenshot_dir / f"{prefix}_{ts}.png"
        await page.screenshot(path=str(path), full_page=True)
        return str(path)
