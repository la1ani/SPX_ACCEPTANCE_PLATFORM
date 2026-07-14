"""
Live ChartConnector: Playwright screenshots the TradingView chart, the
screenshot is sent to Claude for structured extraction ONLY (no judgment —
see llm_chart_extraction.py in the main package for why the scope is this
narrow), and the JSON response is mapped into a ChartExtraction.

Requires:
    pip install playwright anthropic
    playwright install chromium

Usage:
    connector = PlaywrightChartConnector(
        call_chart_url="https://www.tradingview.com/chart/....",
        put_chart_url="https://www.tradingview.com/chart/....",
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        storage_state_path="tradingview_session.json",  # see setup.sh / SETUP.md
    )
    extraction = connector.read_chart(Side.CALL, datetime.utcnow())
"""

from __future__ import annotations

import base64
import json
from datetime import datetime

from anthropic import Anthropic
from playwright.sync_api import sync_playwright

from spx_agent.connectors import ChartConnector
from spx_agent.llm_chart_extraction import EXTRACTION_PROMPT
from spx_agent.models import Candle, ChartExtraction, LevelRead, LevelType, Side

MODEL = "claude-haiku-4-5-20251001"


class PlaywrightChartConnector(ChartConnector):
    def __init__(
        self,
        call_chart_url: str,
        put_chart_url: str,
        anthropic_api_key: str,
        storage_state_path: str = "tradingview_session.json",
        screenshot_wait_ms: int = 1500,
    ):
        self.urls = {Side.CALL: call_chart_url, Side.PUT: put_chart_url}
        self.storage_state_path = storage_state_path
        self.screenshot_wait_ms = screenshot_wait_ms
        self.client = Anthropic(api_key=anthropic_api_key)

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._contexts = {}
        self._pages = {}
        for side, url in self.urls.items():
            context = self._browser.new_context(storage_state=storage_state_path)
            page = context.new_page()
            page.goto(url)
            self._contexts[side] = context
            self._pages[side] = page

    def close(self):
        for context in self._contexts.values():
            context.close()
        self._browser.close()
        self._playwright.stop()

    def read_chart(self, side: Side, as_of: datetime) -> ChartExtraction:
        page = self._pages[side]
        page.wait_for_timeout(self.screenshot_wait_ms)  # let the chart finish rendering
        screenshot_bytes = page.screenshot()
        image_b64 = base64.b64encode(screenshot_bytes).decode()

        response = self.client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/png", "data": image_b64
                    }},
                    {"type": "text", "text": EXTRACTION_PROMPT},
                ],
            }],
        )

        raw_text = response.content[0].text.strip()
        raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw_text)

        return _to_chart_extraction(data, side, as_of)


def _to_chart_extraction(data: dict, side: Side, as_of: datetime) -> ChartExtraction:
    levels = []
    for lv in data.get("support_levels", []):
        levels.append(LevelRead(
            level_type=LevelType.SUPPORT,
            price=float(lv["price"]),
            timeframe_seconds=int(lv["timeframe_minutes"]) * 60,
        ))
    for lv in data.get("resistance_levels", []):
        levels.append(LevelRead(
            level_type=LevelType.RESISTANCE,
            price=float(lv["price"]),
            timeframe_seconds=int(lv["timeframe_minutes"]) * 60,
        ))

    candles_by_timeframe: dict[int, list[Candle]] = {}
    for c in data.get("recent_candles", []):
        tf_seconds = int(c["timeframe_minutes"]) * 60
        candles_by_timeframe.setdefault(tf_seconds, []).append(
            Candle(
                timestamp=as_of,
                open=float(c["open"]),
                high=float(c["high"]),
                low=float(c["low"]),
                close=float(c["close"]),
                volume=float(c.get("volume", 0)),
                timeframe_seconds=tf_seconds,
            )
        )

    return ChartExtraction(
        timestamp=as_of,
        side=side,
        levels=levels,
        candles_by_timeframe=candles_by_timeframe,
        indicator_notes=data.get("indicator_notes", ""),
    )
