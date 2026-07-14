"""
Production reference: the ONE place an LLM is called in this entire system.

This module is not wired into the demo (run_demo.py uses DerivedChartConnector
instead, which builds the same ChartExtraction shape directly from OHLCV data
so the reasoning pipeline can be demonstrated without a live screenshot or an
API key). This file documents exactly what the real integration should do:

  1. Playwright takes a screenshot of the TradingView chart (call side, then
     put side).
  2. The screenshot is sent to a vision-capable model with the extraction
     prompt below.
  3. The model returns ONLY the structured facts below — no judgment, no
     "this looks bullish", nothing beyond what is literally visible on the
     chart. All reasoning happens afterward in chart_agent.py.

Keeping the LLM's role this narrow is deliberate (see the project notes):
extraction only, at every timeframe visible on the chart. This keeps the
system's per-call cost small and its reasoning legible and swappable —
any vision-capable model can fill this role since the job is mechanical
extraction, not judgment.
"""

from __future__ import annotations

EXTRACTION_PROMPT = """
You are looking at a screenshot of a TradingView options price chart with
support/resistance and candle indicators overlaid.

Return ONLY a JSON object with this exact shape — no other text:

{
  "support_levels": [{"price": <number>, "timeframe_minutes": <number>}, ...],
  "resistance_levels": [{"price": <number>, "timeframe_minutes": <number>}, ...],
  "recent_candles": [
    {"open": <number>, "high": <number>, "low": <number>, "close": <number>,
     "volume": <number>, "timeframe_minutes": <number>},
    ...
  ],
  "indicator_notes": "<brief factual description of any buy/sell markers or
                       indicator signals visible on the chart, no interpretation>"
}

Rules:
- Report only what is visibly on the chart. Do not infer levels that are
  not drawn or marked.
- Report levels and candles at every timeframe visible on the chart (the
  chart may show multiple overlaid timeframes).
- Do NOT include any judgment about whether the market is bullish, bearish,
  or about to move. That reasoning is not your job — only extract the
  visible facts.
""".strip()


# Example of how this plugs into a real ChartConnector implementation:
#
#   from anthropic import Anthropic
#   import base64, json
#
#   class PlaywrightChartConnector(ChartConnector):
#       def __init__(self, page, client: Anthropic):
#           self.page = page
#           self.client = client
#
#       def read_chart(self, side: Side, as_of: datetime) -> ChartExtraction:
#           screenshot_bytes = self.page.screenshot()
#           image_b64 = base64.b64encode(screenshot_bytes).decode()
#
#           response = self.client.messages.create(
#               model="claude-haiku-4-5-20251001",
#               max_tokens=1024,
#               messages=[{
#                   "role": "user",
#                   "content": [
#                       {"type": "image", "source": {
#                           "type": "base64", "media_type": "image/png", "data": image_b64
#                       }},
#                       {"type": "text", "text": EXTRACTION_PROMPT},
#                   ],
#               }],
#           )
#           data = json.loads(response.content[0].text)
#           return _to_chart_extraction(data, side, as_of)
