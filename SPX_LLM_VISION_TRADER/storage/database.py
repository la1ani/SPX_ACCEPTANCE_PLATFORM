from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript('''
            CREATE TABLE IF NOT EXISTS trigger_plans (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, screenshot_path TEXT, trigger_json TEXT, status TEXT);
            CREATE TABLE IF NOT EXISTS battle_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, trigger_plan_id INTEGER, started_at TEXT, ended_at TEXT, trigger_type TEXT, status TEXT, final_decision TEXT, winner TEXT, trade_grade TEXT, confidence TEXT, final_reason TEXT);
            CREATE TABLE IF NOT EXISTS battle_observations (id INTEGER PRIMARY KEY AUTOINCREMENT, battle_session_id INTEGER, timestamp TEXT, screenshot_path TEXT, call_sheet_snapshot_json TEXT, put_sheet_snapshot_json TEXT, llm_response_json TEXT, memory_update TEXT, overall_grade TEXT, trade_grade TEXT, grade_confidence TEXT, factor_grades_json TEXT);
            CREATE TABLE IF NOT EXISTS war_grade_history (id INTEGER PRIMARY KEY AUTOINCREMENT, battle_session_id INTEGER, timestamp TEXT, screenshot_path TEXT, call_sheet_snapshot_json TEXT, put_sheet_snapshot_json TEXT, overall_grade TEXT, trade_grade TEXT, grade_confidence TEXT, grade_direction TEXT, factor_grades_json TEXT, missing_confirmations_json TEXT, danger_signals_json TEXT, why_not_full_hand TEXT, what_would_upgrade_grade TEXT, what_would_downgrade_grade TEXT, llm_raw_response_json TEXT);
            CREATE TABLE IF NOT EXISTS sheet_snapshots (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, call_data_json TEXT, put_data_json TEXT);
            CREATE TABLE IF NOT EXISTS final_results (id INTEGER PRIMARY KEY AUTOINCREMENT, battle_session_id INTEGER, timestamp TEXT, winner TEXT, confidence TEXT, trade_grade TEXT, reason TEXT, screenshot_path TEXT, result_json TEXT, final_overall_grade TEXT, final_trade_grade TEXT, final_factor_grades_json TEXT, grade_progression_json TEXT);
            CREATE TABLE IF NOT EXISTS raw_llm_responses (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, response_type TEXT, raw_text TEXT, parsed_json TEXT);
            ''')

    def save_trigger_plan(self, screenshot_path: str, trigger_json: dict[str, Any], status: str = "ACTIVE") -> int:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO trigger_plans(created_at, screenshot_path, trigger_json, status) VALUES (?, ?, ?, ?)", (now_iso(), screenshot_path, _json(trigger_json), status))
            return int(cur.lastrowid)

    def start_battle_session(self, trigger_plan_id: int, trigger_type: str) -> int:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO battle_sessions(trigger_plan_id, started_at, trigger_type, status, final_decision, winner, trade_grade, confidence, final_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (trigger_plan_id, now_iso(), trigger_type, "ACTIVE", "", "NONE", "WATCH_ONLY", "LOW", ""))
            return int(cur.lastrowid)

    def save_sheet_snapshot(self, call_data: list[dict[str, Any]], put_data: list[dict[str, Any]]) -> int:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO sheet_snapshots(timestamp, call_data_json, put_data_json) VALUES (?, ?, ?)", (now_iso(), _json(call_data), _json(put_data)))
            return int(cur.lastrowid)

    def save_raw_llm_response(self, response_type: str, raw_text: str, parsed_json: Optional[dict[str, Any]] = None) -> int:
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO raw_llm_responses(timestamp, response_type, raw_text, parsed_json) VALUES (?, ?, ?, ?)", (now_iso(), response_type, raw_text, _json(parsed_json or {})))
            return int(cur.lastrowid)

    def save_battle_observation(self, battle_session_id: int, screenshot_path: str, call_data: list[dict[str, Any]], put_data: list[dict[str, Any]], llm_response: dict[str, Any]) -> int:
        grading = llm_response.get("war_grading") or {}
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO battle_observations(battle_session_id, timestamp, screenshot_path, call_sheet_snapshot_json, put_sheet_snapshot_json, llm_response_json, memory_update, overall_grade, trade_grade, grade_confidence, factor_grades_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (battle_session_id, now_iso(), screenshot_path, _json(call_data), _json(put_data), _json(llm_response), llm_response.get("memory_update", ""), grading.get("overall_grade", "UNCLEAR"), grading.get("trade_grade", llm_response.get("trade_grade", "WATCH_ONLY")), grading.get("grade_confidence", llm_response.get("confidence", "LOW")), _json(grading.get("factor_grades", []))))
            return int(cur.lastrowid)

    def save_war_grade_history(self, battle_session_id: int, screenshot_path: str, call_data: list[dict[str, Any]], put_data: list[dict[str, Any]], llm_response: dict[str, Any]) -> int:
        grading = llm_response.get("war_grading") or {}
        with self.connect() as conn:
            cur = conn.execute("INSERT INTO war_grade_history(battle_session_id, timestamp, screenshot_path, call_sheet_snapshot_json, put_sheet_snapshot_json, overall_grade, trade_grade, grade_confidence, grade_direction, factor_grades_json, missing_confirmations_json, danger_signals_json, why_not_full_hand, what_would_upgrade_grade, what_would_downgrade_grade, llm_raw_response_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (battle_session_id, now_iso(), screenshot_path, _json(call_data), _json(put_data), grading.get("overall_grade", "UNCLEAR"), grading.get("trade_grade", llm_response.get("trade_grade", "WATCH_ONLY")), grading.get("grade_confidence", llm_response.get("confidence", "LOW")), grading.get("grade_direction", "NONE"), _json(grading.get("factor_grades", [])), _json(grading.get("missing_confirmations", [])), _json(grading.get("danger_signals", [])), grading.get("why_not_full_hand", ""), grading.get("what_would_upgrade_grade", ""), grading.get("what_would_downgrade_grade", ""), _json(llm_response)))
            return int(cur.lastrowid)

    def get_grade_progression(self, battle_session_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT timestamp, overall_grade, trade_grade, grade_confidence, grade_direction, factor_grades_json FROM war_grade_history WHERE battle_session_id=? ORDER BY id ASC", (battle_session_id,)).fetchall()
        return [dict(row) for row in rows]

    def finish_battle_session(self, battle_session_id: int, llm_response: dict[str, Any], screenshot_path: str) -> int:
        grading = llm_response.get("war_grading") or {}
        progression = self.get_grade_progression(battle_session_id)
        with self.connect() as conn:
            conn.execute("UPDATE battle_sessions SET ended_at=?, status=?, final_decision=?, winner=?, trade_grade=?, confidence=?, final_reason=? WHERE id=?", (now_iso(), "FINAL", llm_response.get("decision", ""), llm_response.get("winner", "NONE"), grading.get("trade_grade", llm_response.get("trade_grade", "WATCH_ONLY")), llm_response.get("confidence", grading.get("grade_confidence", "LOW")), llm_response.get("reason", ""), battle_session_id))
            cur = conn.execute("INSERT INTO final_results(battle_session_id, timestamp, winner, confidence, trade_grade, reason, screenshot_path, result_json, final_overall_grade, final_trade_grade, final_factor_grades_json, grade_progression_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (battle_session_id, now_iso(), llm_response.get("winner", "NONE"), llm_response.get("confidence", grading.get("grade_confidence", "LOW")), grading.get("trade_grade", llm_response.get("trade_grade", "WATCH_ONLY")), llm_response.get("reason", ""), screenshot_path, _json(llm_response), grading.get("overall_grade", "UNCLEAR"), grading.get("trade_grade", llm_response.get("trade_grade", "WATCH_ONLY")), _json(grading.get("factor_grades", [])), _json(progression)))
            return int(cur.lastrowid)
