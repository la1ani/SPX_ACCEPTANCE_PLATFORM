"""
Live SheetConnector: polls the Google Sheet's published CSV export.

Matches the endpoint format already confirmed working in the project notes:
/export?format=csv&gid=<sheet_id> — NOT the /edit URL, which returns 401
regardless of sharing settings.

Usage:
    connector = GoogleSheetConnector(
        call_sheet_url="https://docs.google.com/spreadsheets/d/XXXX/export?format=csv&gid=0",
        put_sheet_url="https://docs.google.com/spreadsheets/d/XXXX/export?format=csv&gid=123456",
    )
    ticks = connector.get_ticks()   # call this on your poll loop

Expected sheet columns (same as the TradingView CSV export format used
throughout this project): time, open, high, low, close, Volume. Adjust
COLUMN_MAP below if your live sheet uses different header names.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

import requests

from spx_agent.connectors import SheetConnector
from spx_agent.models import SheetTick

COLUMN_MAP = {
    "time": "time",
    "close": "close",
    "volume": "Volume",
}


class GoogleSheetConnector(SheetConnector):
    def __init__(self, call_sheet_url: str, put_sheet_url: str, timeout_seconds: int = 10):
        self.call_sheet_url = call_sheet_url
        self.put_sheet_url = put_sheet_url
        self.timeout_seconds = timeout_seconds
        self._last_seen_ts: datetime | None = None

    def get_ticks(self, since: datetime | None = None) -> list[SheetTick]:
        since = since or self._last_seen_ts
        call_rows = self._fetch(self.call_sheet_url)
        put_rows = self._fetch(self.put_sheet_url)

        common_times = sorted(set(call_rows) & set(put_rows))
        ticks = []
        for ts in common_times:
            if since is not None and ts <= since:
                continue
            c, p = call_rows[ts], put_rows[ts]
            ticks.append(
                SheetTick(
                    timestamp=ts,
                    call_price=c["close"],
                    put_price=p["close"],
                    call_volume=c["volume"],
                    put_volume=p["volume"],
                )
            )

        if ticks:
            self._last_seen_ts = ticks[-1].timestamp
        return ticks

    def _fetch(self, url: str) -> dict[datetime, dict]:
        response = requests.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        reader = csv.DictReader(io.StringIO(response.text))
        rows: dict[datetime, dict] = {}
        for row in reader:
            ts = datetime.fromisoformat(row[COLUMN_MAP["time"]])
            rows[ts] = {
                "close": float(row[COLUMN_MAP["close"]]),
                "volume": float(row[COLUMN_MAP["volume"]]),
            }
        return rows
