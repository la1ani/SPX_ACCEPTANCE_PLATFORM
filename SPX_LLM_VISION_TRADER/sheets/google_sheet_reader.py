from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import json
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
    "memory_update",
    "missing_confirmations",
    "danger_signals",
    "why_not_full_hand",
    "what_would_upgrade_grade",
    "what_would_downgrade_grade",
    "factor_grades_json",
    "trigger_type",
    "cycle",
    "screenshot_path",
]

ALERT_LOG_HEADERS = [
    "timestamp",
    "event_type",
    "alert_level",
    "battle_status",
    "decision",
    "winner",
    "trade_grade",
    "confidence",
    "reason",
    "next_action",
    "telegram_mode",
    "alert_text",
]

WATCH_LOG_HEADERS = [
    "timestamp",
    "watch_action",
    "trigger_type",
    "reason",
    "data_status",
    "latest_call_price",
    "latest_put_price",
    "call_source",
    "put_source",
    "call_rows_count",
    "put_rows_count",
    "commentary",
]

AUTO_CHECK_HEADERS = [
    "timestamp",
    "event_type",
    "cycle",
    "battle_status",
    "decision",
    "overall_grade",
    "trade_grade",
    "grade_confidence",
    "grade_direction",
    "missing_confirmations",
    "danger_signals",
    "why_not_full_hand",
    "what_would_upgrade_grade",
    "what_would_downgrade_grade",
    "memory_update",
    "reason",
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

ZONE_VIEW_HEADERS = ["Field", "Latest LLM Battle Zone"]


class GoogleSheetReader:
    def __init__(
        self,
        sheet_id: str,
        service_account_file: str | Path,
        call_tab: str,
        put_tab: str,
        call_link_tab: str = "CALLS_LINK",
        put_link_tab: str = "PUTS_LINK",
    ):
        self.sheet_id = sheet_id
        self.service_account_file = Path(service_account_file)
        self.call_tab = call_tab
        self.put_tab = put_tab
        self.call_link_tab = call_link_tab
        self.put_link_tab = put_link_tab
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
        rows = self.sheet.worksheet(tab_name).get_all_records()
        for row in rows:
            row["_source_tab"] = tab_name
        return rows

    def _worksheet_rows_safe(self, tab_name: str) -> list[dict[str, Any]]:
        if not tab_name:
            return []
        try:
            return self._worksheet_rows(tab_name)
        except Exception:
            return []

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
        if "_source_tab" in row:
            normalized["_source_tab"] = row.get("_source_tab")
            normalized["source_tab"] = row.get("_source_tab")
        aliases = {
            "timestamp": ["time", "datetime", "date_time", "created_at", "alert_time"],
            "price": ["close", "last", "ltp", "option_price", "current_price", "value"],
            "high": ["h"],
            "low": ["l"],
            "volume": ["vol", "contracts"],
            "velocity": ["speed", "delta_speed"],
        }
        for target, keys in aliases.items():
            if target not in normalized or normalized.get(target) in (None, ""):
                for candidate in keys:
                    if candidate in normalized and normalized.get(candidate) not in (None, ""):
                        normalized[target] = normalized[candidate]
                        break
        return normalized

    def _row_time_value(self, row: dict[str, Any]) -> float:
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
        return 0.0

    def _merge_live_tabs(self, primary_tab: str, fast_tab: str, limit: int) -> list[dict[str, Any]]:
        primary_rows = [self._normalize_row(row) for row in self._worksheet_rows_safe(primary_tab)]
        fast_rows = [self._normalize_row(row) for row in self._worksheet_rows_safe(fast_tab)]
        combined = primary_rows + fast_rows
        if not combined:
            return []
        combined.sort(key=self._row_time_value)
        return combined[-limit:]

    def read_recent(self, limit: int = 50) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        # IMPORTANT: Triggers use live sheet data, not chart guesses.
        # CALLS/PUTS = main decision feed. CALLS_LINK/PUTS_LINK = faster live sensor feed.
        call_rows = self._merge_live_tabs(self.call_tab, self.call_link_tab, limit)
        put_rows = self._merge_live_tabs(self.put_tab, self.put_link_tab, limit)
        return call_rows, put_rows

    def _get_or_create_worksheet(self, tab_name: str, headers: list[str], rows: int = 1000):
        if self.sheet is None:
            self.connect()
        assert self.sheet is not None
        try:
            worksheet = self.sheet.worksheet(tab_name)
        except Exception:
            worksheet = self.sheet.add_worksheet(title=tab_name, rows=rows, cols=max(20, len(headers)))
        current_headers = worksheet.row_values(1)
        if current_headers != headers:
            worksheet.update("A1", [headers], value_input_option="USER_ENTERED")
        return worksheet

    def _json_text(self, value: Any) -> str:
        if value in (None, ""):
            return ""
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            return str(value)

    def _join_list(self, value: Any) -> str:
        if isinstance(value, list):
            return " | ".join(str(item) for item in value)
        return str(value or "")

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
            response.get("memory_update", ""),
            self._join_list(grading.get("missing_confirmations")),
            self._join_list(grading.get("danger_signals")),
            grading.get("why_not_full_hand", ""),
            grading.get("what_would_upgrade_grade", ""),
            grading.get("what_would_downgrade_grade", ""),
            self._json_text(grading.get("factor_grades")),
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

    def _alert_text(self, response: dict[str, Any], event_type: str) -> str:
        grading = response.get("war_grading") or {}
        return (
            f"SPX {event_type} | "
            f"Status={response.get('battle_status')} | "
            f"Decision={response.get('decision')} | "
            f"Winner={response.get('winner')} | "
            f"Grade={grading.get('trade_grade') or response.get('trade_grade')} | "
            f"Confidence={response.get('confidence') or grading.get('grade_confidence')} | "
            f"Reason={response.get('reason')} | "
            f"Next={response.get('next_action_for_python')}"
        )

    def _alert_row(self, response: dict[str, Any], event_type: str, telegram_mode: str = "") -> list[Any]:
        grading = response.get("war_grading") or {}
        grade_value = grading.get("trade_grade") or response.get("trade_grade") or ""
        confidence = response.get("confidence") or grading.get("grade_confidence") or ""
        alert_level = "BEST_ALERT" if self._is_best_alert(response) else "COMMENTARY"
        return [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            event_type,
            alert_level,
            response.get("battle_status", ""),
            response.get("decision", ""),
            response.get("winner", ""),
            grade_value,
            confidence,
            response.get("reason", ""),
            response.get("next_action_for_python", ""),
            telegram_mode,
            self._alert_text(response, event_type),
        ]

    def _auto_check_row(self, response: dict[str, Any], event_type: str, screenshot_path: str, cycle: int | str) -> list[Any]:
        grading = response.get("war_grading") or {}
        return [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            event_type,
            cycle,
            response.get("battle_status", ""),
            response.get("decision", ""),
            grading.get("overall_grade", ""),
            grading.get("trade_grade", response.get("trade_grade", "")),
            grading.get("grade_confidence", response.get("confidence", "")),
            grading.get("grade_direction", ""),
            self._join_list(grading.get("missing_confirmations")),
            self._join_list(grading.get("danger_signals")),
            grading.get("why_not_full_hand", ""),
            grading.get("what_would_upgrade_grade", ""),
            grading.get("what_would_downgrade_grade", ""),
            response.get("memory_update", ""),
            response.get("reason", ""),
            screenshot_path,
        ]

    def append_watch_log(
        self,
        action: str,
        reason: str,
        trigger_type: str = "",
        call_rows_count: int = 0,
        put_rows_count: int = 0,
        data_status: str = "",
        latest_call_price: Any = "",
        latest_put_price: Any = "",
        call_source: str = "",
        put_source: str = "",
    ) -> None:
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            action,
            trigger_type,
            reason,
            data_status,
            latest_call_price,
            latest_put_price,
            call_source,
            put_source,
            call_rows_count,
            put_rows_count,
            f"Watch action: {action} | {reason}",
        ]
        watch_log = self._get_or_create_worksheet("Watch_Log", WATCH_LOG_HEADERS, rows=10000)
        watch_log.append_row(row, value_input_option="USER_ENTERED")

    def append_battle_log(self, response: dict[str, Any], event_type: str = "BATTLE_UPDATE", screenshot_path: str = "", trigger_type: str = "", cycle: int | str = "", telegram_mode: str = "") -> None:
        row = self._row_from_response(response, event_type, screenshot_path=screenshot_path, trigger_type=trigger_type, cycle=cycle)
        ai_log = self._get_or_create_worksheet("AI_Log", AI_LOG_HEADERS, rows=10000)
        ai_log.append_row(row, value_input_option="USER_ENTERED")

        alert_log = self._get_or_create_worksheet("Alert_Log", ALERT_LOG_HEADERS, rows=10000)
        alert_log.append_row(self._alert_row(response, event_type, telegram_mode=telegram_mode), value_input_option="USER_ENTERED")

        auto_check = self._get_or_create_worksheet("Auto_Check", AUTO_CHECK_HEADERS, rows=10000)
        auto_check.append_row(self._auto_check_row(response, event_type, screenshot_path, cycle), value_input_option="USER_ENTERED")

        if self._is_best_alert(response):
            best_alerts = self._get_or_create_worksheet("Best_Alerts", AI_LOG_HEADERS, rows=5000)
            best_alerts.append_row(row, value_input_option="USER_ENTERED")

    def _zone_value(self, zone: dict[str, Any] | None, key: str) -> Any:
        if not isinstance(zone, dict):
            return ""
        return zone.get(key, "")

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

    def _format_zone_text(self, exists_value: Any, low_value: Any, high_value: Any) -> str:
        return f"Exists: {exists_value} | Low: {low_value} | High: {high_value}"

    def _update_zone_view(self, row: list[Any]) -> None:
        view_rows = [
            ZONE_VIEW_HEADERS,
            ["Last update", row[0]],
            ["Event", row[1]],
            ["Battlefield status", row[2]],
            ["Market context", row[3]],
            ["CALL zone", self._format_zone_text(row[4], row[5], row[6])],
            ["CALL reason", row[7]],
            ["CALL trigger", row[8]],
            ["CALL invalidation", row[9]],
            ["PUT zone", self._format_zone_text(row[10], row[11], row[12])],
            ["PUT reason", row[13]],
            ["PUT trigger", row[14]],
            ["PUT invalidation", row[15]],
            ["Consolidation", self._format_zone_text(row[16], row[17], row[18])],
            ["Consolidation reason", row[19]],
            ["Liquidity", self._format_zone_text(row[20], row[21], row[22])],
            ["Liquidity reason", row[23]],
            ["Next action", row[24]],
            ["Watch conditions", row[25]],
            ["Call LLM when", row[26]],
            ["New screenshot when", row[27]],
            ["Screenshot path", row[28]],
        ]
        view = self._get_or_create_worksheet("LLM_Zone_View", ZONE_VIEW_HEADERS, rows=100)
        try:
            view.clear()
        except Exception:
            pass
        view.update("A1:B22", view_rows, value_input_option="USER_ENTERED")

    def append_trigger_plan_log(self, trigger_plan: dict[str, Any], screenshot_path: str = "", event_type: str = "LLM_BATTLE_ZONE") -> None:
        row = self._trigger_plan_row(trigger_plan, event_type=event_type, screenshot_path=screenshot_path)
        trigger_zones = self._get_or_create_worksheet("Trigger_Zones", TRIGGER_ZONE_HEADERS, rows=5000)
        trigger_zones.append_row(row, value_input_option="USER_ENTERED")
        self._update_zone_view(row)
