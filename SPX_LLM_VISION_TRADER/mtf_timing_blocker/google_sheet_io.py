from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import time

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:  # pragma: no cover
    gspread = None
    Credentials = None


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

RAW_HEADERS = [
    "Server Time",
    "Ticker",
    "Exchange",
    "Interval",
    "Candle Time",
    "Open",
    "Close",
    "High",
    "Low",
    "Volume",
    "Signal",
    "Comment",
]

CURRENT_BLOCKER_HEADERS = [
    "Date Time",
    "Source",
    "CALL Symbol",
    "PUT Symbol",
    "Candidate Side",
    "CALL 15s",
    "CALL 30s",
    "CALL 1m",
    "CALL 3m",
    "CALL 5m",
    "PUT 15s",
    "PUT 30s",
    "PUT 1m",
    "PUT 3m",
    "PUT 5m",
    "Fast Flip",
    "Rejection Status",
    "Recovery Status",
    "Velocity Status",
    "Volume Status",
    "Body Stack Status",
    "Opposite Bleeding",
    "Price Level Status",
    "Blocking Status",
    "Trade Status",
    "Grade",
    "Action",
    "Reason",
    "Event Type",
]

EVENT_LOG_HEADERS = [
    "Date Time",
    "Source",
    "Event Type",
    "Symbol",
    "Side",
    "Interval",
    "Old Signal",
    "New Signal",
    "Candidate Side",
    "Blocking Status",
    "Trade Status",
    "Grade",
    "Action",
    "Reason",
    "Flip Speed",
    "Seconds Between",
    "Price Delta",
    "Velocity Per Min",
    "Volume Ratio",
    "Price Level Status",
    "Opposite Side Status",
]

LATEST_STATE_HEADERS = [
    "Date Time",
    "Source",
    "Side",
    "Interval",
    "Ticker",
    "Server Time",
    "Candle Time",
    "Open",
    "Close",
    "High",
    "Low",
    "Volume",
    "Signal",
]

ENGINE_STATE_HEADERS = ["State Key", "State JSON", "Updated At"]


class MTFSheetIO:
    """Google Sheet IO for the MTF Timing Blocker.

    It reads raw tabs and writes all blocker output tabs. It does not touch
    existing calls/puts tabs except reading them.
    """

    def __init__(
        self,
        sheet_id: str,
        service_account_file: str | Path,
        call_tab: str = "calls",
        put_tab: str = "puts",
        manual_tab: str = "Manual_Signal_Input",
    ):
        self.sheet_id = sheet_id
        self.service_account_file = Path(service_account_file)
        self.call_tab = call_tab
        self.put_tab = put_tab
        self.manual_tab = manual_tab
        self.client = None
        self.sheet = None
        self._ws_cache: dict[str, Any] = {}
        self._headers_checked: set[str] = set()
        self._outputs_ensured = False

    def connect(self) -> None:
        if self.sheet is not None:
            return
        if not self.sheet_id:
            raise RuntimeError("MTF/GOOGLE_SHEET_ID is missing.")
        if not self.service_account_file.exists():
            raise FileNotFoundError(f"Google service account file not found: {self.service_account_file}")
        if gspread is None or Credentials is None:
            raise RuntimeError("Install Google packages: pip install gspread google-auth")
        creds = Credentials.from_service_account_file(str(self.service_account_file), scopes=SCOPES)
        self.client = gspread.authorize(creds)
        self.sheet = self.client.open_by_key(self.sheet_id)

    def _api_retry(self, func, *args, **kwargs):
        last_exc = None
        for attempt in range(4):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if "429" not in str(exc) and "Quota exceeded" not in str(exc):
                    raise
                wait = 20 + (attempt * 15)
                print(f"Google Sheets quota hit. Waiting {wait}s then retrying...")
                time.sleep(wait)
        raise last_exc

    def _worksheet(self, tab_name: str):
        self.connect()
        assert self.sheet is not None
        if tab_name not in self._ws_cache:
            self._ws_cache[tab_name] = self._api_retry(self.sheet.worksheet, tab_name)
        return self._ws_cache[tab_name]

    def _get_or_create(self, tab_name: str, headers: list[str], rows: int = 1000):
        self.connect()
        assert self.sheet is not None
        if tab_name in self._ws_cache:
            ws = self._ws_cache[tab_name]
        else:
            try:
                ws = self._api_retry(self.sheet.worksheet, tab_name)
            except Exception:
                ws = self._api_retry(self.sheet.add_worksheet, title=tab_name, rows=rows, cols=max(20, len(headers)))
            self._ws_cache[tab_name] = ws

        if tab_name not in self._headers_checked:
            current_headers = self._api_retry(ws.row_values, 1)
            if current_headers != headers:
                self._api_retry(ws.update, "A1", [headers], value_input_option="USER_ENTERED")
            self._headers_checked.add(tab_name)
        return ws

    def ensure_output_tabs(self) -> None:
        if self._outputs_ensured:
            return
        self._get_or_create(self.manual_tab, RAW_HEADERS, rows=1000)
        self._get_or_create("MTF_Current_Blocker", CURRENT_BLOCKER_HEADERS, rows=50)
        self._get_or_create("MTF_Blocker_History", CURRENT_BLOCKER_HEADERS, rows=20000)
        self._get_or_create("MTF_Event_Log", EVENT_LOG_HEADERS, rows=20000)
        self._get_or_create("MTF_Rejection_Watch", EVENT_LOG_HEADERS, rows=10000)
        self._get_or_create("MTF_Blocked_Trades", EVENT_LOG_HEADERS, rows=10000)
        self._get_or_create("MTF_Allowed_Trades", EVENT_LOG_HEADERS, rows=5000)
        self._get_or_create("MTF_Exit_Watch", EVENT_LOG_HEADERS, rows=5000)
        self._get_or_create("MTF_Latest_State", LATEST_STATE_HEADERS, rows=100)
        self._get_or_create("MTF_Engine_State", ENGINE_STATE_HEADERS, rows=10)
        self._outputs_ensured = True

    def _records_from_tab(self, tab_name: str, source: str, lookback_rows: int) -> list[dict[str, Any]]:
        try:
            ws = self._worksheet(tab_name)
        except Exception:
            return []
        rows = self._api_retry(ws.get_all_records)
        if lookback_rows and len(rows) > lookback_rows:
            rows = rows[-lookback_rows:]
        for row in rows:
            row["_source"] = source
            row["_source_tab"] = tab_name
        return rows

    def read_input_rows(self, lookback_rows: int = 200) -> list[dict[str, Any]]:
        call_rows = self._records_from_tab(self.call_tab, "AUTO", lookback_rows)
        put_rows = self._records_from_tab(self.put_tab, "AUTO", lookback_rows)
        manual_rows = self._records_from_tab(self.manual_tab, "MANUAL", lookback_rows)
        return call_rows + put_rows + manual_rows

    def read_engine_state_json(self) -> str:
        try:
            ws = self._get_or_create("MTF_Engine_State", ENGINE_STATE_HEADERS, rows=10)
            rows = self._api_retry(ws.get_all_records)
            for row in rows:
                if str(row.get("State Key", "")).strip() == "engine_state":
                    return str(row.get("State JSON", "") or "")
        except Exception:
            return ""
        return ""

    def write_engine_state_json(self, state_json: str, updated_at: str) -> None:
        ws = self._get_or_create("MTF_Engine_State", ENGINE_STATE_HEADERS, rows=10)
        try:
            self._api_retry(ws.clear)
        except Exception:
            pass
        self._api_retry(
            ws.update,
            "A1:C2",
            [
                ENGINE_STATE_HEADERS,
                ["engine_state", state_json, updated_at],
            ],
            value_input_option="USER_ENTERED",
        )

    def write_current_blocker(self, decision_row: list[Any]) -> None:
        ws = self._get_or_create("MTF_Current_Blocker", CURRENT_BLOCKER_HEADERS, rows=50)
        try:
            self._api_retry(ws.clear)
        except Exception:
            pass
        self._api_retry(ws.update, "A1", [CURRENT_BLOCKER_HEADERS, decision_row], value_input_option="USER_ENTERED")

    def append_history(self, decision_row: list[Any]) -> None:
        ws = self._get_or_create("MTF_Blocker_History", CURRENT_BLOCKER_HEADERS, rows=20000)
        self._api_retry(ws.append_row, decision_row, value_input_option="USER_ENTERED")

    def write_latest_state(self, rows: list[list[Any]]) -> None:
        ws = self._get_or_create("MTF_Latest_State", LATEST_STATE_HEADERS, rows=100)
        try:
            self._api_retry(ws.clear)
        except Exception:
            pass
        self._api_retry(ws.update, "A1", [LATEST_STATE_HEADERS] + rows, value_input_option="USER_ENTERED")

    def append_events(self, events: list[Any]) -> None:
        if not events:
            return
        all_rows = [event.row() for event in events]

        event_log = self._get_or_create("MTF_Event_Log", EVENT_LOG_HEADERS, rows=20000)
        self._api_retry(event_log.append_rows, all_rows, value_input_option="USER_ENTERED")

        rejection_rows = [
            event.row()
            for event in events
            if "REJECTION" in event.event_type or "WAIT_FOR_1M_FLIP" in event.event_type
        ]
        if rejection_rows:
            ws = self._get_or_create("MTF_Rejection_Watch", EVENT_LOG_HEADERS, rows=10000)
            self._api_retry(ws.append_rows, rejection_rows, value_input_option="USER_ENTERED")

        blocked_rows = [
            event.row()
            for event in events
            if event.blocking_status.startswith("BLOCKED")
            or event.blocking_status in {"CHOP_SIGNAL_NO_TRADE", "FAKE_SIGNAL_FLIP_NO_TRADE"}
            or event.trade_status in {"NO_TRADE", "WAIT_FOR_1M_FLIP"}
        ]
        if blocked_rows:
            ws = self._get_or_create("MTF_Blocked_Trades", EVENT_LOG_HEADERS, rows=10000)
            self._api_retry(ws.append_rows, blocked_rows, value_input_option="USER_ENTERED")

        allowed_rows = [
            event.row()
            for event in events
            if event.trade_status in {"READY_TO_TRADE", "GOOD_TIMING_FULL_HAND"}
            or event.action in {"LIGHT_HAND", "FULL_HAND"}
        ]
        if allowed_rows:
            ws = self._get_or_create("MTF_Allowed_Trades", EVENT_LOG_HEADERS, rows=5000)
            self._api_retry(ws.append_rows, allowed_rows, value_input_option="USER_ENTERED")

        exit_rows = [
            event.row()
            for event in events
            if event.event_type in {"EXIT_NOW", "FLIP_WATCH"}
            or "EXIT" in event.event_type
            or "TIMING_LOST" in event.event_type
            or "OPPOSITE_SIDE_RECOVERY" in event.event_type
        ]
        if exit_rows:
            ws = self._get_or_create("MTF_Exit_Watch", EVENT_LOG_HEADERS, rows=5000)
            self._api_retry(ws.append_rows, exit_rows, value_input_option="USER_ENTERED")

    def snapshot(self, decision: Any, events: list[Any], latest_state_rows: list[list[Any]], state_json: str, updated_at: str) -> None:
        self.ensure_output_tabs()
        self.write_current_blocker(decision.row())
        self.append_history(decision.row())
        self.write_latest_state(latest_state_rows)
        self.append_events(events)
        self.write_engine_state_json(state_json, updated_at)
