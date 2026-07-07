from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import re

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

AI_LOG_HEADERS = [
    "timestamp",
    "event_type",
    "battle_status",
    "decision",
    "winner",
    "weak_side",
    "strong_side",
    "trade_grade",
    "confidence",
    "holding_time_status",
    "rejection_confirmed",
    "weak_side_support_broken",
    "opposite_side_holding_support",
    "opposite_side_volume_imbalance",
    "velocity_after_failure",
    "next_action_for_python",
    "reason",
    "trigger_type",
    "cycle",
    "screenshot_path",
]


class GoogleSheetReader:
    def __init__(self, sheet_id: str, service_account_file: str | Path, call_tab: str, put_tab: str):
        self.sheet_id = sheet_id
        self.service_account_file = Path(service_account_file)
        self.call_tab = call_tab
        self.put_tab = put_tab
        self.client = None
        self.sheet = None

    def connect(self) -> None:
        if not self.sheet_id:
            raise RuntimeError("GOOGLE_SHEET_ID is missing in .env")
        if not self.service_account_file.exists():
            raise FileNotFoundError(f"Google service account file not found: {self.service_account_file}")
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError as exc:
            raise RuntimeError("Install Google Sheet packages: pip install gspread google-auth") from exc
        creds = Credentials.from_service_account_file(str(self.service_account_file), scopes=SCOPES)
        self.client = gspread.authorize(creds)
        self.sheet = self.client.open_by_key(self.sheet_id)

    def _worksheet_rows(self, tab_name: str) -> list[dict[str, Any]]:
        if self.sheet is None:
            self.connect()
        assert self.sheet is not None
        return self.sheet.worksheet(tab_name).get_all_records()

    def _clean_key(self, key: str) -> str:
        key = str(key or "").strip().lower()
        return re.sub(r"[^a-z0-9]+", "_", key).strip("_")

    def _number(self, value: Any) -> Any:
        if isinstance(value, (int, float)):
            return value
        text = str(value).replace(",", "").strip()
        if text == "":
            return None
        try:
            return float(text) if "." in text else int(text)
        except ValueError:
            return value

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = {self._clean_key(k): self._number(v) for k, v in row.items()}
        aliases = {"timestamp": ["time", "datetime", "date_time", "created_at"], "price": ["close", "last", "ltp", "option_price"], "high": ["h"], "low": ["l"], "volume": ["vol", "contracts"], "velocity": ["speed", "delta_speed"]}
        for target, keys in aliases.items():
            if target not in normalized or normalized.get(target) in (None, ""):
                for candidate in keys:
                    if candidate in normalized and normalized.get(candidate) not in (None, ""):
                        normalized[target] = normalized[candidate]
                        break
        return normalized

    def read_recent(self, limit: int = 50) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        call_rows = [self._normalize_row(row) for row in self._worksheet_rows(self.call_tab)]
        put_rows = [self._normalize_row(row) for row in self._worksheet_rows(self.put_tab)]
        return call_rows[-limit:], put_rows[-limit:]

    def _get_or_create_worksheet(self, tab_name: str, headers: list[str]):
        if self.sheet is None:
            self.connect()
        assert self.sheet is not None
        try:
            worksheet = self.sheet.worksheet(tab_name)
        except Exception:
            worksheet = self.sheet.add_worksheet(title=tab_name, rows=1000, cols=max(20, len(headers)))
        current_headers = worksheet.row_values(1)
        if not current_headers:
            worksheet.append_row(headers, value_input_option="USER_ENTERED")
        return worksheet

    def _row_from_response(self, response: dict[str, Any], event_type: str, screenshot_path: str = "", trigger_type: str = "", cycle: int | str = "") -> list[Any]:
        grading = response.get("war_grading") or {}
        trade_grade = grading.get("trade_grade") or response.get("trade_grade") or ""
        confidence = response.get("confidence") or grading.get("grade_confidence") or ""
        return [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            event_type,
            response.get("battle_status", ""),
            response.get("decision", ""),
            response.get("winner", ""),
            response.get("weak_side", ""),
            response.get("strong_side", ""),
            trade_grade,
            confidence,
            response.get("holding_time_status", ""),
            response.get("rejection_confirmed", ""),
            response.get("weak_side_support_broken", ""),
            response.get("opposite_side_holding_support", ""),
            response.get("opposite_side_volume_imbalance", ""),
            response.get("velocity_after_failure", ""),
            response.get("next_action_for_python", ""),
            response.get("reason", ""),
            trigger_type or response.get("trigger_type", ""),
            cycle,
            screenshot_path,
        ]

    def _is_best_alert(self, response: dict[str, Any]) -> bool:
        grading = response.get("war_grading") or {}
        trade_grade = str(grading.get("trade_grade") or response.get("trade_grade") or "").upper()
        winner = str(response.get("winner") or "").upper()
        decision = str(response.get("decision") or "").upper()
        status = str(response.get("battle_status") or "").upper()
        strong_grades = {"LIGHT_HAND", "HALF_HAND", "FULL_HAND", "SUPER_HAND", "ENTRY", "ENTER"}
        return (
            status == "FINAL"
            or winner in {"CALL", "CALLS", "PUT", "PUTS"}
            or trade_grade in strong_grades
            or "ENTER" in decision
            or "ENTRY" in decision
        )

    def append_battle_log(self, response: dict[str, Any], event_type: str = "BATTLE_UPDATE", screenshot_path: str = "", trigger_type: str = "", cycle: int | str = "") -> None:
        row = self._row_from_response(response, event_type, screenshot_path=screenshot_path, trigger_type=trigger_type, cycle=cycle)
        ai_log = self._get_or_create_worksheet("AI_Log", AI_LOG_HEADERS)
        ai_log.append_row(row, value_input_option="USER_ENTERED")
        if self._is_best_alert(response):
            best_alerts = self._get_or_create_worksheet("Best_Alerts", AI_LOG_HEADERS)
            best_alerts.append_row(row, value_input_option="USER_ENTERED")
