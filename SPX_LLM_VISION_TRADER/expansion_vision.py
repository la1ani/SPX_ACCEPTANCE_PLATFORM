"""Extract closed 3-minute and 15-minute CALL/PUT candles from one chart image."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from expansion_engine import Candle, Side
from llm.llm_client import LLMClient


PROMPT = """
The screenshot contains CALL and PUT option charts. Extract facts only.
Do not identify support, resistance, zones, rejection, indicators, winners,
trade direction, or predictions.

Return JSON only:
{
  "call": {
    "3": [{"timestamp":"ISO-8601","open":0,"high":0,"low":0,"close":0}],
    "15": [{"timestamp":"ISO-8601","open":0,"high":0,"low":0,"close":0}]
  },
  "put": {
    "3": [{"timestamp":"ISO-8601","open":0,"high":0,"low":0,"close":0}],
    "15": [{"timestamp":"ISO-8601","open":0,"high":0,"low":0,"close":0}]
  }
}

Rules:
- Return the latest six CLOSED candles when visible.
- Never include the currently forming candle.
- Preserve chronological order, oldest to newest.
- Use only the 3-minute and 15-minute timeframes.
- If a timeframe is not visible or values cannot be read reliably, return [].
- Never invent OHLC values or timestamps.
""".strip()


def _json_object(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Vision response did not contain a JSON object")
    return json.loads(text[start:end + 1])


def extract_candles(client: LLMClient, screenshot: str | Path) -> dict[tuple[Side, int], list[Candle]]:
    payload = _json_object(client.send_vision_request(PROMPT, screenshot))
    streams: dict[tuple[Side, int], list[Candle]] = {}
    for side, name in ((Side.CALL, "call"), (Side.PUT, "put")):
        side_data = payload.get(name) or {}
        for timeframe in (3, 15):
            candles: list[Candle] = []
            for item in side_data.get(str(timeframe), []) or []:
                candles.append(
                    Candle(
                        side=side,
                        timeframe_minutes=timeframe,
                        timestamp=datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00")),
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                    )
                )
            streams[(side, timeframe)] = candles
    return streams
