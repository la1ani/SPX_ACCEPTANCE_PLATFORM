"""
Connectors — the ONLY code in this package allowed to touch the outside
world (Google Sheet, chart image, LLM). Everything else in this package
(chart_agent, data_agent, boss, learning, commentary) is pure reasoning
over plain Python objects and has no knowledge of where the data came from.

Two connector interfaces:

  SheetConnector  -> yields SheetTick objects (call/put price + volume)
  ChartConnector  -> yields ChartExtraction objects (support/resistance,
                     candle stacking, from the LLM/vision read of the chart)

Each has a CSV-backed implementation here, built from the same export
format TradingView produces (the files used earlier in this conversation),
so the whole system can run end-to-end against real historical data
without needing live credentials. A production deployment swaps these for:

  - GoogleSheetConnector: pulls the live /export?format=csv&gid=... feed
  - PlaywrightChartConnector: screenshots the TradingView chart via
    Playwright, sends the image to an LLM (see llm_chart_extraction.py
    for the extraction prompt), and returns a ChartExtraction

Nothing downstream needs to change when that swap happens.
"""

from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import Candle, ChartExtraction, LevelRead, LevelType, Side, SheetTick


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------

class SheetConnector(ABC):
    @abstractmethod
    def get_ticks(self, since: datetime | None = None) -> list[SheetTick]:
        """Return ticks (ordered oldest -> newest), optionally filtered to after `since`."""


class ChartConnector(ABC):
    @abstractmethod
    def read_chart(self, side: Side, as_of: datetime) -> ChartExtraction:
        """
        Return the current chart extraction for one side (call or put) as of
        the given timestamp. In production this is where Playwright grabs a
        screenshot and the LLM extracts structured facts from it.
        """


# ---------------------------------------------------------------------------
# CSV-backed implementations (demo / backtest against real exported data)
# ---------------------------------------------------------------------------

class CsvSheetConnector(SheetConnector):
    """
    Reads the same TradingView CSV export format used earlier: one file per
    side (call, put), columns: time, open, high, low, close, Buy, Sell,
    ..., Volume. Merges them into SheetTick objects on matching timestamps.
    """

    def __init__(self, call_csv_path: str | Path, put_csv_path: str | Path):
        self.call_rows = self._read_csv(call_csv_path)
        self.put_rows = self._read_csv(put_csv_path)

    @staticmethod
    def _read_csv(path: str | Path) -> dict[datetime, dict]:
        rows: dict[datetime, dict] = {}
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = datetime.fromisoformat(row["time"])
                rows[ts] = {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["Volume"]),
                }
        return rows

    def get_ticks(self, since: datetime | None = None) -> list[SheetTick]:
        common_times = sorted(set(self.call_rows) & set(self.put_rows))
        ticks = []
        for ts in common_times:
            if since is not None and ts <= since:
                continue
            c, p = self.call_rows[ts], self.put_rows[ts]
            ticks.append(
                SheetTick(
                    timestamp=ts,
                    call_price=c["close"],
                    put_price=p["close"],
                    call_volume=c["volume"],
                    put_volume=p["volume"],
                )
            )
        return ticks


class LiveDerivedChartConnector(ChartConnector):
    """
    Same math as DerivedChartConnector (swing highs/lows as support/
    resistance, resampled candles for the longer timeframe) but built to
    work off a rolling buffer of LIVE SheetTick objects instead of a static
    CSV. This is what makes the live rule-validation loop possible without
    needing Playwright or an LLM call: the live Google Sheet feed already
    carries price data, and this connector turns that into the same
    ChartExtraction shape the reasoning agents expect.

    Call `push_tick()` on every new live tick, then `read_chart()` whenever
    the orchestrator needs the current extraction — it always reflects the
    latest buffered ticks.
    """

    def __init__(self, base_timeframe_seconds: int = 15, buffer_size: int = 400):
        self._base_timeframe_seconds = base_timeframe_seconds
        self._buffer_size = buffer_size
        self._ticks: dict[Side, list[SheetTick]] = {Side.CALL: [], Side.PUT: []}

    def push_tick(self, tick: SheetTick) -> None:
        for side in (Side.CALL, Side.PUT):
            self._ticks[side].append(tick)
            if len(self._ticks[side]) > self._buffer_size:
                self._ticks[side] = self._ticks[side][-self._buffer_size:]

    def read_chart(self, side: Side, as_of: datetime) -> ChartExtraction:
        ticks = self._ticks[side]
        if len(ticks) < 3:
            return ChartExtraction(timestamp=as_of, side=side, levels=[], candles_by_timeframe={})

        base_candles = self._ticks_to_candles(ticks, side)
        candles_by_timeframe = {
            self._base_timeframe_seconds: base_candles[-8:],
            self._base_timeframe_seconds * 12: self._resample(base_candles, 12)[-8:],  # ~3 min if base=15s
        }

        levels = []
        for tf, candles in candles_by_timeframe.items():
            if len(candles) < 3:
                continue
            recent = candles[-6:]
            resistance = max(c.high for c in recent)
            support = min(c.low for c in recent)
            levels.append(LevelRead(level_type=LevelType.RESISTANCE, price=resistance, timeframe_seconds=tf))
            levels.append(LevelRead(level_type=LevelType.SUPPORT, price=support, timeframe_seconds=tf))

        return ChartExtraction(timestamp=as_of, side=side, levels=levels, candles_by_timeframe=candles_by_timeframe)

    def _ticks_to_candles(self, ticks: list[SheetTick], side: Side) -> list[Candle]:
        """
        Buckets raw ticks into base_timeframe_seconds candles. Since live
        ticks arrive irregularly (whatever the sheet's poll interval is),
        this groups them by time bucket rather than assuming one tick per bar.
        """
        buckets: dict[int, list[SheetTick]] = {}
        for t in ticks:
            bucket_key = int(t.timestamp.timestamp() // self._base_timeframe_seconds)
            buckets.setdefault(bucket_key, []).append(t)

        candles = []
        for bucket_key in sorted(buckets):
            bucket_ticks = buckets[bucket_key]
            prices = [t.call_price if side == Side.CALL else t.put_price for t in bucket_ticks]
            volumes = [t.call_volume if side == Side.CALL else t.put_volume for t in bucket_ticks]
            candles.append(
                Candle(
                    timestamp=bucket_ticks[0].timestamp,
                    open=prices[0], high=max(prices), low=min(prices), close=prices[-1],
                    volume=sum(volumes), timeframe_seconds=self._base_timeframe_seconds,
                )
            )
        return candles

    @staticmethod
    def _resample(candles: list[Candle], factor: int) -> list[Candle]:
        resampled = []
        for i in range(0, len(candles) - factor + 1, factor):
            chunk = candles[i:i + factor]
            resampled.append(
                Candle(
                    timestamp=chunk[0].timestamp, open=chunk[0].open,
                    high=max(c.high for c in chunk), low=min(c.low for c in chunk),
                    close=chunk[-1].close, volume=sum(c.volume for c in chunk),
                    timeframe_seconds=chunk[0].timeframe_seconds * factor,
                )
            )
        return resampled


class DerivedChartConnector(ChartConnector):
    """
    Builds a ChartExtraction directly from the same OHLCV data the sheet
    connector reads, rather than an actual screenshot + LLM call. This lets
    the full reasoning pipeline (chart agent, data agent, boss) run and be
    demonstrated end-to-end on real historical data without needing a live
    LLM/vision integration wired up yet.

    Support/resistance levels are derived as recent local highs/lows at
    each timeframe (a standard swing-high/swing-low approach) — a
    reasonable stand-in for what an LLM chart read would supply. Candle
    stacking is built by resampling the underlying 3-minute bars into
    coarser timeframes.

    Swap this for PlaywrightChartConnector in production; nothing else in
    the pipeline needs to change.
    """

    def __init__(self, call_csv_path: str | Path, put_csv_path: str | Path):
        self._raw = {
            Side.CALL: CsvSheetConnector._read_csv(call_csv_path),
            Side.PUT: CsvSheetConnector._read_csv(put_csv_path),
        }
        self._base_timeframe_seconds = 180  # the source data is 3-minute bars

    def read_chart(self, side: Side, as_of: datetime) -> ChartExtraction:
        rows = {ts: v for ts, v in self._raw[side].items() if ts <= as_of}
        timestamps = sorted(rows)
        if not timestamps:
            return ChartExtraction(timestamp=as_of, side=side, levels=[], candles_by_timeframe={})

        base_candles = [
            Candle(
                timestamp=ts,
                open=rows[ts]["open"],
                high=rows[ts]["high"],
                low=rows[ts]["low"],
                close=rows[ts]["close"],
                volume=rows[ts]["volume"],
                timeframe_seconds=self._base_timeframe_seconds,
            )
            for ts in timestamps
        ]

        candles_by_timeframe = {
            self._base_timeframe_seconds: base_candles[-8:],
            self._base_timeframe_seconds * 5: self._resample(base_candles, 5)[-8:],   # ~15 min
        }

        levels = []
        for tf, candles in candles_by_timeframe.items():
            if len(candles) < 3:
                continue
            recent = candles[-6:]
            resistance = max(c.high for c in recent)
            support = min(c.low for c in recent)
            levels.append(LevelRead(level_type=LevelType.RESISTANCE, price=resistance, timeframe_seconds=tf))
            levels.append(LevelRead(level_type=LevelType.SUPPORT, price=support, timeframe_seconds=tf))

        return ChartExtraction(
            timestamp=as_of,
            side=side,
            levels=levels,
            candles_by_timeframe=candles_by_timeframe,
        )

    @staticmethod
    def _resample(candles: list[Candle], factor: int) -> list[Candle]:
        """Merge every `factor` consecutive candles into one coarser candle."""
        resampled = []
        for i in range(0, len(candles) - factor + 1, factor):
            chunk = candles[i:i + factor]
            resampled.append(
                Candle(
                    timestamp=chunk[0].timestamp,
                    open=chunk[0].open,
                    high=max(c.high for c in chunk),
                    low=min(c.low for c in chunk),
                    close=chunk[-1].close,
                    volume=sum(c.volume for c in chunk),
                    timeframe_seconds=chunk[0].timeframe_seconds * factor,
                )
            )
        return resampled
