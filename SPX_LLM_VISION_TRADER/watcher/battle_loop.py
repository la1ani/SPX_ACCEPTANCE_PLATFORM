from __future__ import annotations

import asyncio
from typing import Any
from playwright.async_api import Page

from llm.battle_analyzer import BattleAnalyzer
from playwright_engine.chart_capture import ChartCapture
from sheets.google_sheet_reader import GoogleSheetReader
from storage.database import Database


class BattleLoop:
    def __init__(self, db: Database, analyzer: BattleAnalyzer, capture: ChartCapture, sheet_reader: GoogleSheetReader, loop_seconds: int, alert_manager: Any = None):
        self.db = db
        self.analyzer = analyzer
        self.capture = capture
        self.sheet_reader = sheet_reader
        self.loop_seconds = loop_seconds
        self.alert_manager = alert_manager

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
            memory.append({"cycle": cycle, "decision": latest_response.get("decision"), "status": latest_response.get("battle_status"), "message": latest_response.get("memory_update", ""), "reason": latest_response.get("reason", "")})
            grade_history.append(latest_response.get("war_grading", {}))
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
