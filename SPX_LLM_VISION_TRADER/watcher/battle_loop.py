from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from playwright.async_api import Page

from llm.battle_analyzer import BattleAnalyzer
from playwright_engine.chart_capture import ChartCapture
from sheets.google_sheet_reader import GoogleSheetReader
from storage.database import Database
from watcher.alert_intelligence import build_rule_commentary, get_alert_level, get_battle_phase, get_entry_exit_action, get_war_grading, get_winner_grading


COMMENTARY_HEADERS = [
    "timestamp", "cycle", "battle_phase", "alert_level", "entry_exit_action", "decision",
    "current_winner", "winner_power_grade", "winner_power_score", "power_status", "trade_size_suggestion",
    "heavy_side", "weak_side", "winner", "trade_grade", "confidence", "support_break_grade",
    "rejection_grade", "holding_time_grade", "volume_imbalance_grade", "velocity_after_failure_grade",
    "power_transfer_grade", "user_commentary", "rule_commentary", "why_not_a_plus", "upgrade_to_a_plus",
    "downgrade_warning", "missing_confirmations", "danger_signals", "screenshot_path",
]

ENTRY_EXIT_HEADERS = [
    "timestamp", "cycle", "entry_exit_action", "side", "winner_power_grade", "winner_power_score",
    "trade_grade", "confidence", "entry_reason", "exit_reason", "decision", "battle_phase",
    "winner", "winner_explanation", "reason", "screenshot_path",
]


class BattleLoop:
    def __init__(self, db: Database, analyzer: BattleAnalyzer, capture: ChartCapture, sheet_reader: GoogleSheetReader, loop_seconds: int, alert_manager: Any = None):
        self.db = db
        self.analyzer = analyzer
        self.capture = capture
        self.sheet_reader = sheet_reader
        self.loop_seconds = loop_seconds
        self.alert_manager = alert_manager

    def _join(self, value: Any) -> str:
        if isinstance(value, list):
            return " | ".join(str(item) for item in value)
        return str(value or "")

    def _append_readable_sheet_logs(self, response: dict[str, Any], cycle: int, screenshot_path: str) -> None:
        grading = get_war_grading(response)
        winner_grading = get_winner_grading(response)
        phase = get_battle_phase(response)
        entry_action = response.get("entry_exit_action") or get_entry_exit_action(response)
        commentary = response.get("user_commentary") or ""
        rule_commentary = build_rule_commentary(response)
        grade_value = grading.get("trade_grade") or response.get("trade_grade") or "WATCH_ONLY"
        confidence = response.get("confidence") or grading.get("grade_confidence") or "LOW"
        heavy = response.get("heavy_side") or response.get("strong_side") or "UNKNOWN"
        weak = response.get("weak_side") or "UNKNOWN"
        winner = response.get("winner") or "NONE"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        commentary_row = [
            timestamp,
            cycle,
            phase,
            get_alert_level(response),
            entry_action,
            response.get("decision", ""),
            winner_grading.get("current_winner", ""),
            winner_grading.get("winner_power_grade", ""),
            winner_grading.get("winner_power_score", ""),
            winner_grading.get("power_status", ""),
            winner_grading.get("trade_size_suggestion", ""),
            heavy,
            weak,
            winner,
            grade_value,
            confidence,
            winner_grading.get("support_break_grade", ""),
            winner_grading.get("rejection_grade", ""),
            winner_grading.get("holding_time_grade", ""),
            winner_grading.get("volume_imbalance_grade", ""),
            winner_grading.get("velocity_after_failure_grade", ""),
            winner_grading.get("power_transfer_grade", ""),
            commentary,
            rule_commentary,
            winner_grading.get("why_not_a_plus", ""),
            winner_grading.get("upgrade_to_a_plus", ""),
            winner_grading.get("downgrade_warning", ""),
            self._join(grading.get("missing_confirmations")),
            self._join(grading.get("danger_signals")),
            screenshot_path,
        ]
        try:
            ws = self.sheet_reader._get_or_create_worksheet("Battle_Commentary", COMMENTARY_HEADERS, rows=10000)
            ws.append_row(commentary_row, value_input_option="USER_ENTERED")
        except Exception as exc:
            print(f"[sheet-log] Could not write Battle_Commentary: {exc}")

        if entry_action in {"FIGHTING_STARTED", "ENTER_CALL", "ENTER_PUT", "ENTRY_ALERT", "SINGLE_WATCH", "EXIT", "EXIT_ALERT", "FLIP_WATCH", "NO_TRADE"}:
            side = winner_grading.get("current_winner") or winner if winner in {"CALL", "PUT"} else heavy
            entry_exit_row = [
                timestamp,
                cycle,
                entry_action,
                side,
                winner_grading.get("winner_power_grade", ""),
                winner_grading.get("winner_power_score", ""),
                grade_value,
                confidence,
                response.get("entry_reason", ""),
                response.get("exit_reason", ""),
                response.get("decision", ""),
                phase,
                winner,
                winner_grading.get("winner_explanation", ""),
                response.get("reason", ""),
                screenshot_path,
            ]
            try:
                ws = self.sheet_reader._get_or_create_worksheet("Entry_Exit_Log", ENTRY_EXIT_HEADERS, rows=10000)
                ws.append_row(entry_exit_row, value_input_option="USER_ENTERED")
            except Exception as exc:
                print(f"[sheet-log] Could not write Entry_Exit_Log: {exc}")

    async def run(self, page: Page, trigger_plan_id: int, trigger_plan: dict[str, Any], trigger_type: str, max_cycles: int = 60) -> dict[str, Any]:
        session_id = self.db.start_battle_session(trigger_plan_id, trigger_type)
        memory: list[dict[str, Any]] = []
        grade_history: list[dict[str, Any]] = []
        latest_response: dict[str, Any] = {}
        latest_screenshot = ""
        for cycle in range(1, max_cycles + 1):
            latest_screenshot = await self.capture.capture(page, prefix="battle")
            call_rows, put_rows = self.sheet_reader.read_recent(limit=80)
            self.db.save_sheet_snapshot(call_rows, put_rows)
            decision_model, raw = self.analyzer.analyze(latest_screenshot, trigger_plan, call_rows, put_rows, memory, grade_history)
            latest_response = decision_model.model_dump()
            self.db.save_raw_llm_response("battle", raw, latest_response)
            self.db.save_battle_observation(session_id, latest_screenshot, call_rows, put_rows, latest_response)
            self.db.save_war_grade_history(session_id, latest_screenshot, call_rows, put_rows, latest_response)
            try:
                self.sheet_reader.append_battle_log(
                    latest_response,
                    event_type="BATTLE_UPDATE",
                    screenshot_path=latest_screenshot,
                    trigger_type=trigger_type,
                    cycle=cycle,
                    telegram_mode=getattr(self.alert_manager, "mode", "") if self.alert_manager else "",
                )
            except Exception as exc:
                print(f"[sheet-log] Could not write AI_Log / Alert_Log / Auto_Check / Best_Alerts: {exc}")
            self._append_readable_sheet_logs(latest_response, cycle, latest_screenshot)
            memory.append({"cycle": cycle, "decision": latest_response.get("decision"), "status": latest_response.get("battle_status"), "message": latest_response.get("memory_update", ""), "reason": latest_response.get("reason", ""), "commentary": latest_response.get("user_commentary", ""), "winner_grading": latest_response.get("battle_winner_grading", {})})
            grade_history.append({"war_grading": latest_response.get("war_grading", {}), "battle_winner_grading": latest_response.get("battle_winner_grading", {})})
            if self.alert_manager:
                self.alert_manager.send_battle_update(latest_response)
            status = str(latest_response.get("battle_status", "ACTIVE")).upper()
            action = str(latest_response.get("next_action_for_python", "")).upper()
            if status == "FINAL" or action == "SAVE_FINAL_RESULT":
                self.db.finish_battle_session(session_id, latest_response, latest_screenshot)
                return latest_response
            if status == "NEW_TRIGGER_REQUIRED" or action == "REQUEST_NEW_TRIGGER":
                return latest_response
            await asyncio.sleep(max(1, int(latest_response.get("next_check_seconds") or self.loop_seconds)))
        latest_response.setdefault("battle_status", "ACTIVE")
        latest_response.setdefault("decision", "CONTINUE_ANALYZING")
        latest_response.setdefault("reason", "Max cycles reached without final LLM decision.")
        return latest_response
