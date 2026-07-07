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

TRIGGER_ZONE_HEADERS = [
    "timestamp",
    "event_type",
    "battlefield_status",
    "market_context",
    "call_zone_exists",
    "call_zone_low",
    "call_zone_high",
    "call_visual_reason",
    "call_trigger_condition",
    "call_invalidation_condition",
    "put_zone_exists",
    "put_zone_low",
    "put_zone_high",
    "put_visual_reason",
    "put_trigger_condition",
    "put_invalidation_condition",
    "consolidation_exists",
    "consolidation_low",
    "consolidation_high",
    "consolidation_reason",
    "liquidity_exists",
    "liquidity_low",
    "liquidity_high",
    "liquidity_reason",
    "next_action",
    "watch_conditions",
    "call_llm_when",
    "new_screenshot_when",
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
        grade_value = grading.get("trade_grade") or response.get("trade_grade") or ""
        confidence = response.get("confidence") or grading.get("grade_confidence") or ""
        return [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            event_type,
            response.get("battle_status", ""),
            response.get("decision", ""),
            response.get("winner", ""),
            response.get("weak_side", ""),
            response.get("strong_side", ""),
            grade_value,
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
        grade_value = str(grading.get("trade_grade") or response.get("trade_grade") or "").upper()
        side_value = str(response.get("winner") or "").upper()
        decision = str(response.get("decision") or "").upper()
        status = str(response.get("battle_status") or "").upper()
        strong_grades = {"LIGHT_HAND", "HALF_HAND", "FULL_HAND", "SUPER_HAND", "ENTRY", "ENTER"}
        return (
            status == "FINAL"
            or side_value in {"CALL", "CALLS", "PUT", "PUTS"}
            or grade_value in strong_grades
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

    def _zone_value(self, zone: dict[str, Any] | None, key: str) -> Any:
        if not isinstance(zone, dict):
            return ""
        return zone.get(key, "")

    def _join_list(self, value: Any) -> str:
        if isinstance(value, list):
            return " | ".join(str(item) for item in value)
        return str(value or "")

    def _trigger_plan_row(self, trigger_plan: dict[str, Any], event_type: str, screenshot_path: str) -> list[Any]:
        call_zone = trigger_plan.get("call_battle_area") or {}
        put_zone = trigger_plan.get("put_battle_area") or {}
        consolidation = trigger_plan.get("consolidation_zone") or {}
        liquidity = trigger_plan.get("liquidity_zone") or {}
        watch_plan = trigger_plan.get("watch_plan") or {}
        return [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            event_type,
            trigger_plan.get("battlefield_status", ""),
            trigger_plan.get("market_context", ""),
            self._zone_value(call_zone, "exists"),
            self._zone_value(call_zone, "zone_low"),
            self._zone_value(call_zone, "zone_high"),
            self._zone_value(call_zone, "visual_reason"),
            self._zone_value(call_zone, "trigger_condition"),
            self._zone_value(call_zone, "invalidation_condition"),
            self._zone_value(put_zone, "exists"),
            self._zone_value(put_zone, "zone_low"),
            self._zone_value(put_zone, "zone_high"),
            self._zone_value(put_zone, "visual_reason"),
            self._zone_value(put_zone, "trigger_condition"),
            self._zone_value(put_zone, "invalidation_condition"),
            self._zone_value(consolidation, "exists"),
            self._zone_value(consolidation, "zone_low"),
            self._zone_value(consolidation, "zone_high"),
            self._zone_value(consolidation, "visual_reason"),
            self._zone_value(liquidity, "exists"),
            self._zone_value(liquidity, "zone_low"),
            self._zone_value(liquidity, "zone_high"),
            self._zone_value(liquidity, "visual_reason"),
            trigger_plan.get("next_action", ""),
            self._join_list(watch_plan.get("conditions_to_watch")),
            self._join_list(watch_plan.get("call_llm_when")),
            self._join_list(watch_plan.get("new_screenshot_when")),
            screenshot_path,
        ]

    def append_trigger_plan_log(self, trigger_plan: dict[str, Any], screenshot_path: str = "", event_type: str = "LLM_BATTLE_ZONE") -> None:
        row = self._trigger_plan_row(trigger_plan, event_type=event_type, screenshot_path=screenshot_path)
        trigger_zones = self._get_or_create_worksheet("Trigger_Zones", TRIGGER_ZONE_HEADERS)
        trigger_zones.append_row(row, value_input_option="USER_ENTERED")
