from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional
import time


@dataclass
class WatchResult:
    action: str
    trigger_type: str = "BATTLE_ZONE_TRIGGER"
    reason: str = ""
    data_status: str = "UNKNOWN"
    latest_call_price: Optional[float] = None
    latest_put_price: Optional[float] = None
    call_source: str = ""
    put_source: str = ""


class TriggerWatcher:
    """Watch LLM battle zones using live rows coming from Google Sheets.

    The LLM decides the battlefield zones from screenshots. Python does not invent
    support/resistance. Python only watches the live CALL/PUT sheet feeds and starts
    the battle when fresh sheet data touches the LLM zones.
    """

    def __init__(self, plan: dict[str, Any], max_age_seconds: int = 300, max_data_stale_seconds: int = 120):
        self.plan = plan
        self.created_at = time.time()
        self.max_age_seconds = max_age_seconds
        self.max_data_stale_seconds = max_data_stale_seconds
        self._last_call_signature = ""
        self._last_put_signature = ""
        self._last_fresh_data_seen_at = time.time()

    def update_plan(self, plan: dict[str, Any]) -> None:
        self.plan = plan
        self.created_at = time.time()
        self._last_call_signature = ""
        self._last_put_signature = ""
        self._last_fresh_data_seen_at = time.time()

    def _parse_float(self, value: Any) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        try:
            if value not in (None, ""):
                return float(str(value).replace(",", "").strip())
        except ValueError:
            return None
        return None

    def _row_time(self, row: dict[str, Any]) -> Optional[float]:
        for key in ("timestamp", "time", "datetime", "date_time", "created_at", "alert_time"):
            value = row.get(key)
            if value in (None, ""):
                continue
            if isinstance(value, (int, float)):
                return float(value)
            text = str(value).strip().replace("Z", "")
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M:%S", "%H:%M:%S", "%H:%M"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    if fmt.startswith("%H"):
                        now = datetime.now()
                        parsed = parsed.replace(year=now.year, month=now.month, day=now.day)
                    return parsed.timestamp()
                except ValueError:
                    continue
            try:
                return datetime.fromisoformat(text).timestamp()
            except ValueError:
                continue
        return None

    def _latest_row(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not rows:
            return None
        timed_rows = [(self._row_time(row), row) for row in rows]
        timed_rows = [(ts, row) for ts, row in timed_rows if ts is not None]
        if timed_rows:
            return max(timed_rows, key=lambda item: item[0])[1]
        return rows[-1]

    def _latest_price(self, rows: list[dict[str, Any]]) -> tuple[Optional[float], str, str]:
        row = self._latest_row(rows)
        if not row:
            return None, "", ""
        source = str(row.get("source_tab") or row.get("_source_tab") or "")
        signature = self._row_signature(row)
        for key in ("price", "close", "last", "ltp", "option_price", "current_price", "value"):
            price = self._parse_float(row.get(key))
            if price is not None:
                return price, source, signature
        return None, source, signature

    def _row_signature(self, row: dict[str, Any] | None) -> str:
        if not row:
            return ""
        important = []
        for key in ("timestamp", "time", "datetime", "date_time", "alert_time", "price", "close", "last", "ltp", "option_price", "current_price", "volume", "signal", "comment", "source_tab", "_source_tab"):
            if key in row:
                important.append(f"{key}={row.get(key)}")
        if important:
            return "|".join(important)
        return str(row)

    def _data_status(self, call_signature: str, put_signature: str) -> str:
        if not call_signature and not put_signature:
            return "NO_LIVE_ROWS"
        changed = call_signature != self._last_call_signature or put_signature != self._last_put_signature
        if changed:
            self._last_call_signature = call_signature
            self._last_put_signature = put_signature
            self._last_fresh_data_seen_at = time.time()
            return "LIVE_UPDATED"
        age = int(time.time() - self._last_fresh_data_seen_at)
        if age > self.max_data_stale_seconds:
            return f"STALE_{age}s"
        return f"LIVE_NO_CHANGE_{age}s"

    def _data_is_usable(self, data_status: str) -> bool:
        return data_status == "LIVE_UPDATED" or data_status.startswith("LIVE_NO_CHANGE")

    def _in_zone(self, value: Optional[float], zone: dict[str, Any]) -> bool:
        if value is None:
            return False
        if not zone or not zone.get("exists", False):
            return False
        low = self._parse_float(zone.get("zone_low"))
        high = self._parse_float(zone.get("zone_high"))
        if low is None or high is None:
            return False
        low_f, high_f = sorted((low, high))
        return low_f <= value <= high_f

    def _watch_reason(self, data_status: str, call_price: Optional[float], put_price: Optional[float], call_source: str, put_source: str) -> str:
        return (
            "Watching LIVE Google Sheet rows only; no LLM trigger zone touched yet | "
            f"data={data_status} | call={call_price} from {call_source or 'CALLS/CALLS_LINK'} | "
            f"put={put_price} from {put_source or 'PUTS/PUTS_LINK'}"
        )

    def check(self, call_rows: list[dict[str, Any]], put_rows: list[dict[str, Any]]) -> WatchResult:
        call_price, call_source, call_signature = self._latest_price(call_rows)
        put_price, put_source, put_signature = self._latest_price(put_rows)
        data_status = self._data_status(call_signature, put_signature)

        if time.time() - self.created_at > self.max_age_seconds:
            return WatchResult(action="NEW_TRIGGER_REQUIRED", reason="Plan age exceeded max_age_seconds; requesting fresh screenshot and fresh LLM battle zone", data_status=data_status, latest_call_price=call_price, latest_put_price=put_price, call_source=call_source, put_source=put_source)

        status = str(self.plan.get("battlefield_status", "")).upper()
        if status in {"INVALID", "NEW_TRIGGER_REQUIRED", "UNREADABLE_CHART"}:
            return WatchResult(action="NEW_TRIGGER_REQUIRED", reason=f"LLM plan status is {status}; requesting new readable screenshot", data_status=data_status, latest_call_price=call_price, latest_put_price=put_price, call_source=call_source, put_source=put_source)

        next_action = str(self.plan.get("next_action", "WATCH")).upper()
        if next_action in {"NEW_SCREENSHOT", "REQUEST_NEW_SCREENSHOT", "NEW_TRIGGER_REQUIRED"}:
            return WatchResult(action="NEW_TRIGGER_REQUIRED", reason=f"LLM next_action={next_action}; requesting new screenshot", data_status=data_status, latest_call_price=call_price, latest_put_price=put_price, call_source=call_source, put_source=put_source)

        if data_status == "NO_LIVE_ROWS":
            return WatchResult(action="WATCH", reason="No live CALL/PUT rows found yet; waiting for Google Sheet data", data_status=data_status, latest_call_price=call_price, latest_put_price=put_price, call_source=call_source, put_source=put_source)

        if not self._data_is_usable(data_status):
            return WatchResult(action="WATCH", reason=f"Live sheet data is stale ({data_status}); waiting for fresh rows before any trigger", data_status=data_status, latest_call_price=call_price, latest_put_price=put_price, call_source=call_source, put_source=put_source)

        if self._in_zone(call_price, self.plan.get("call_battle_area", {})):
            return WatchResult(action="START_BATTLE", trigger_type="CALL_BATTLE_ZONE_TRIGGER", reason=f"Fresh LIVE SHEET DATA touched LLM CALL battle zone | data={data_status} | call={call_price} from {call_source or 'CALLS/CALLS_LINK'}", data_status=data_status, latest_call_price=call_price, latest_put_price=put_price, call_source=call_source, put_source=put_source)

        if self._in_zone(put_price, self.plan.get("put_battle_area", {})):
            return WatchResult(action="START_BATTLE", trigger_type="PUT_BATTLE_ZONE_TRIGGER", reason=f"Fresh LIVE SHEET DATA touched LLM PUT battle zone | data={data_status} | put={put_price} from {put_source or 'PUTS/PUTS_LINK'}", data_status=data_status, latest_call_price=call_price, latest_put_price=put_price, call_source=call_source, put_source=put_source)

        consolidation = self.plan.get("consolidation_zone", {})
        if self._in_zone(call_price, consolidation) or self._in_zone(put_price, consolidation):
            return WatchResult(action="START_BATTLE", trigger_type="CONSOLIDATION_ZONE_TRIGGER", reason=f"Fresh LIVE SHEET DATA touched LLM consolidation zone | data={data_status} | call={call_price} | put={put_price}", data_status=data_status, latest_call_price=call_price, latest_put_price=put_price, call_source=call_source, put_source=put_source)

        if next_action in {"START_BATTLE", "START_BATTLE_MODE"}:
            return WatchResult(action="START_BATTLE", trigger_type="LLM_BATTLE_MODE_LIVE_DATA", reason=f"LLM requested {next_action}; live sheet feed is usable | data={data_status} | call={call_price} | put={put_price}", data_status=data_status, latest_call_price=call_price, latest_put_price=put_price, call_source=call_source, put_source=put_source)

        return WatchResult(action="WATCH", reason=self._watch_reason(data_status, call_price, put_price, call_source, put_source), data_status=data_status, latest_call_price=call_price, latest_put_price=put_price, call_source=call_source, put_source=put_source)
