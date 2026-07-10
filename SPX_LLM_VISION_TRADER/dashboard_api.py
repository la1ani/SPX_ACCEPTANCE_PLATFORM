from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config.settings import load_settings
from mtf_timing_blocker.google_sheet_io import MTFSheetIO


app = FastAPI(
    title="SPX War Room Dashboard API",
    description=(
        "Read-only API exposing two separate decision systems: "
        "the LLM battle engine and the Python MTF timing blocker. "
        "Neither decision system modifies or overrides the other."
    ),
    version="1.1.0",
)

# Base44 or another dashboard can call this API from a browser.
# Restrict DASHBOARD_ALLOWED_ORIGINS in production if desired.
_allowed_origins = [
    origin.strip()
    for origin in os.getenv("DASHBOARD_ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins or ["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


_MTF_CACHE: dict[str, Any] = {
    "loaded_at_monotonic": 0.0,
    "payload": None,
}


def _database_path() -> Path:
    settings = load_settings()
    return Path(settings.database_path)


def _connect() -> sqlite3.Connection:
    path = _database_path()
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"SPX database not found at {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _json_load(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first_record(records: list[dict[str, Any]]) -> dict[str, Any]:
    return records[0] if records else {}


def _latest_observation(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT bo.*, bs.trigger_type, bs.status AS session_status
        FROM battle_observations bo
        JOIN battle_sessions bs ON bs.id = bo.battle_session_id
        ORDER BY bo.id DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row else None


def _latest_trigger(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM trigger_plans ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def _latest_final(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM final_results ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def _latest_snapshot(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM sheet_snapshots ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def _latest_session(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM battle_sessions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def _factor_map(grading: dict[str, Any]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for factor in grading.get("factor_grades") or []:
        if not isinstance(factor, dict):
            continue
        key = str(factor.get("factor") or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
        mapped[key] = factor
    return mapped


def _extract_prices(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {"call": None, "put": None}

    def latest_price(rows: list[dict[str, Any]]) -> Any:
        if not rows:
            return None
        row = rows[-1]
        for key in ("close", "Close", "price", "Price", "last", "Last", "plot_0"):
            if key in row and row[key] not in (None, ""):
                return row[key]
        return None

    call_rows = _json_load(snapshot.get("call_data_json"), [])
    put_rows = _json_load(snapshot.get("put_data_json"), [])
    return {
        "call": latest_price(call_rows),
        "put": latest_price(put_rows),
        "call_rows": len(call_rows),
        "put_rows": len(put_rows),
    }


def _mtf_empty_payload(status: str = "NO_DATA", error: str = "") -> dict[str, Any]:
    return {
        "system": "PYTHON_MTF_TIMING_BLOCKER",
        "independent_from_battle": True,
        "status": status,
        "error": error,
        "timestamp": None,
        "source": None,
        "contracts": {
            "call_symbol": None,
            "put_symbol": None,
        },
        "candidate_side": None,
        "signals": {
            "call": {"15s": None, "30s": None, "1m": None, "3m": None, "5m": None},
            "put": {"15s": None, "30s": None, "1m": None, "3m": None, "5m": None},
        },
        "decision": {
            "blocking_status": "NO_DATA",
            "trade_status": "NO_DATA",
            "grade": "UNCLEAR",
            "action": "WAIT",
            "reason": error or "No MTF timing-blocker state is available yet.",
            "entry_allowed": False,
        },
        "timing_evidence": {
            "fast_flip": None,
            "rejection_status": None,
            "recovery_status": None,
            "velocity_status": None,
            "volume_status": None,
            "body_stack_status": None,
            "opposite_bleeding": None,
            "price_level_status": None,
            "event_type": None,
        },
        "latest_state": [],
    }


def _mtf_entry_allowed(trade_status: str, action: str, blocking_status: str) -> bool:
    if str(blocking_status or "").upper().startswith("BLOCKED"):
        return False
    return str(trade_status or "").upper() in {"READY_TO_TRADE", "GOOD_TIMING_FULL_HAND"} or str(action or "").upper() in {"LIGHT_HAND", "FULL_HAND"}


def _build_mtf_payload(force_refresh: bool = False) -> dict[str, Any]:
    """Read the Python MTF blocker output without merging it into battle logic.

    This reads only the MTF output tabs already written by mtf_timing_blocker_main.py.
    It never changes battle winner, battle grade, battle action, or battle entry/exit logic.
    """
    cache_seconds = max(1, int(os.getenv("DASHBOARD_MTF_CACHE_SECONDS", "10")))
    age = time.monotonic() - float(_MTF_CACHE.get("loaded_at_monotonic") or 0.0)
    cached = _MTF_CACHE.get("payload")
    if not force_refresh and cached is not None and age < cache_seconds:
        return cached

    settings = load_settings()
    sheet_id = os.getenv("MTF_GOOGLE_SHEET_ID", "").strip() or settings.google_sheet_id
    service_account_file = settings.google_service_account_file

    if not sheet_id:
        payload = _mtf_empty_payload("CONFIG_MISSING", "MTF_GOOGLE_SHEET_ID / GOOGLE_SHEET_ID is missing.")
        _MTF_CACHE.update({"loaded_at_monotonic": time.monotonic(), "payload": payload})
        return payload

    if not service_account_file:
        payload = _mtf_empty_payload("CONFIG_MISSING", "GOOGLE_SERVICE_ACCOUNT_FILE is missing.")
        _MTF_CACHE.update({"loaded_at_monotonic": time.monotonic(), "payload": payload})
        return payload

    try:
        io = MTFSheetIO(
            sheet_id=sheet_id,
            service_account_file=service_account_file,
            call_tab=os.getenv("MTF_CALL_TAB", settings.call_sheet_tab),
            put_tab=os.getenv("MTF_PUT_TAB", settings.put_sheet_tab),
            manual_tab=os.getenv("MTF_MANUAL_TAB", "Manual_Signal_Input"),
        )
        blocker_records = io._api_retry(io._worksheet("MTF_Current_Blocker").get_all_records)
        latest_state_records = io._api_retry(io._worksheet("MTF_Latest_State").get_all_records)
        row = _first_record(blocker_records)

        if not row:
            payload = _mtf_empty_payload("NO_DATA")
        else:
            blocking_status = str(row.get("Blocking Status", "") or "")
            trade_status = str(row.get("Trade Status", "") or "")
            action = str(row.get("Action", "") or "")
            payload = {
                "system": "PYTHON_MTF_TIMING_BLOCKER",
                "independent_from_battle": True,
                "status": "OK",
                "error": "",
                "timestamp": row.get("Date Time") or None,
                "source": row.get("Source") or None,
                "contracts": {
                    "call_symbol": row.get("CALL Symbol") or None,
                    "put_symbol": row.get("PUT Symbol") or None,
                },
                "candidate_side": row.get("Candidate Side") or None,
                "signals": {
                    "call": {
                        "15s": row.get("CALL 15s") or None,
                        "30s": row.get("CALL 30s") or None,
                        "1m": row.get("CALL 1m") or None,
                        "3m": row.get("CALL 3m") or None,
                        "5m": row.get("CALL 5m") or None,
                    },
                    "put": {
                        "15s": row.get("PUT 15s") or None,
                        "30s": row.get("PUT 30s") or None,
                        "1m": row.get("PUT 1m") or None,
                        "3m": row.get("PUT 3m") or None,
                        "5m": row.get("PUT 5m") or None,
                    },
                },
                "decision": {
                    "blocking_status": blocking_status or "UNKNOWN",
                    "trade_status": trade_status or "UNKNOWN",
                    "grade": row.get("Grade") or "UNCLEAR",
                    "action": action or "WAIT",
                    "reason": row.get("Reason") or "",
                    "entry_allowed": _mtf_entry_allowed(trade_status, action, blocking_status),
                },
                "timing_evidence": {
                    "fast_flip": row.get("Fast Flip") or None,
                    "rejection_status": row.get("Rejection Status") or None,
                    "recovery_status": row.get("Recovery Status") or None,
                    "velocity_status": row.get("Velocity Status") or None,
                    "volume_status": row.get("Volume Status") or None,
                    "body_stack_status": row.get("Body Stack Status") or None,
                    "opposite_bleeding": row.get("Opposite Bleeding") or None,
                    "price_level_status": row.get("Price Level Status") or None,
                    "event_type": row.get("Event Type") or None,
                },
                "latest_state": latest_state_records,
            }
    except Exception as exc:
        payload = _mtf_empty_payload("ERROR", str(exc))

    _MTF_CACHE.update({"loaded_at_monotonic": time.monotonic(), "payload": payload})
    return payload


def _build_current_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    observation = _latest_observation(conn)
    trigger = _latest_trigger(conn)
    final_result = _latest_final(conn)
    snapshot = _latest_snapshot(conn)
    session = _latest_session(conn)

    trigger_json = _json_load(trigger.get("trigger_json") if trigger else None, {})
    latest_response = _json_load(observation.get("llm_response_json") if observation else None, {})
    war_grading = latest_response.get("war_grading") or {}
    winner_grading = latest_response.get("battle_winner_grading") or {}
    factors = _factor_map(war_grading)

    current_winner = (
        winner_grading.get("current_winner")
        or latest_response.get("winner")
        or (session.get("winner") if session else None)
        or "NONE"
    )
    strong_side = latest_response.get("strong_side") or latest_response.get("heavy_side") or "UNKNOWN"
    weak_side = latest_response.get("weak_side") or "UNKNOWN"

    active_session = bool(session and str(session.get("status", "")).upper() == "ACTIVE")
    battle_phase = (
        latest_response.get("battle_phase")
        or war_grading.get("battle_phase")
        or latest_response.get("battle_status")
        or ("BATTLE_ACTIVE" if active_session else "WATCHING")
    )

    price_data = _extract_prices(snapshot)

    return {
        "api_status": "OK",
        "generated_at": _utc_now_iso(),
        "system_status": "LIVE" if snapshot else "NO_DATA",
        "decision_systems": {
            "battle": "LLM battle engine: independent battle winner/grading/entry-exit analysis.",
            "mtf_timing": "Python MTF timing blocker: independent signal timing/block/allow decision.",
            "rule": "Never merge or override one decision with the other. Display both separately.",
        },
        "battle": {
            "is_active": active_session,
            "phase": battle_phase,
            "status": latest_response.get("battle_status") or (session.get("status") if session else "WATCHING"),
            "decision": latest_response.get("decision") or "WATCH",
            "entry_exit_action": latest_response.get("entry_exit_action") or "HOLD_WATCH",
            "trigger_type": latest_response.get("trigger_type") or (session.get("trigger_type") if session else None),
            "current_winner": current_winner,
            "winner": latest_response.get("winner") or current_winner,
            "strong_side": strong_side,
            "weak_side": weak_side,
            "attacking_side": latest_response.get("attacking_side") or "UNKNOWN",
            "trade_grade": war_grading.get("trade_grade") or latest_response.get("trade_grade") or "WATCH_ONLY",
            "confidence": latest_response.get("confidence") or war_grading.get("grade_confidence") or "LOW",
        },
        "winner_power": {
            "current_winner": current_winner,
            "grade": winner_grading.get("winner_power_grade") or "UNCLEAR",
            "score": winner_grading.get("winner_power_score") or 0,
            "status": winner_grading.get("power_status") or "UNCLEAR",
            "trade_size_suggestion": winner_grading.get("trade_size_suggestion") or war_grading.get("trade_grade") or "WATCH_ONLY",
            "explanation": winner_grading.get("winner_explanation") or latest_response.get("reason") or "",
        },
        "factor_grades": {
            "support_break": {
                "grade": winner_grading.get("support_break_grade") or factors.get("weak_side_support_break", {}).get("grade") or "UNCLEAR",
                "detail": factors.get("weak_side_support_break", {}),
            },
            "rejection": {
                "grade": winner_grading.get("rejection_grade") or factors.get("rejection", {}).get("grade") or "UNCLEAR",
                "detail": factors.get("rejection", {}),
            },
            "holding_time": {
                "grade": winner_grading.get("holding_time_grade") or factors.get("holding_time", {}).get("grade") or "UNCLEAR",
                "detail": factors.get("holding_time", {}),
            },
            "opposite_side_support_hold": {
                "grade": factors.get("opposite_side_support_hold", {}).get("grade") or "UNCLEAR",
                "detail": factors.get("opposite_side_support_hold", {}),
            },
            "volume_imbalance": {
                "grade": winner_grading.get("volume_imbalance_grade") or factors.get("volume_imbalance", {}).get("grade") or "UNCLEAR",
                "detail": factors.get("volume_imbalance", {}),
            },
            "velocity_after_failure": {
                "grade": winner_grading.get("velocity_after_failure_grade") or factors.get("velocity_after_failure", {}).get("grade") or "UNCLEAR",
                "detail": factors.get("velocity_after_failure", {}),
            },
            "power_transfer": {
                "grade": winner_grading.get("power_transfer_grade") or factors.get("power_transfer", {}).get("grade") or "UNCLEAR",
                "detail": factors.get("power_transfer", {}),
            },
            "trade_risk": {
                "grade": factors.get("trade_risk", {}).get("grade") or "UNCLEAR",
                "detail": factors.get("trade_risk", {}),
            },
        },
        "confirmations": {
            "rejection_confirmed": latest_response.get("rejection_confirmed", False),
            "weak_side_support_broken": latest_response.get("weak_side_support_broken", False),
            "opposite_side_holding_support": latest_response.get("opposite_side_holding_support", False),
            "opposite_side_volume_imbalance": latest_response.get("opposite_side_volume_imbalance", False),
            "velocity_after_failure": latest_response.get("velocity_after_failure", False),
            "missing": war_grading.get("missing_confirmations") or [],
            "danger_signals": war_grading.get("danger_signals") or [],
        },
        "guidance": {
            "why_not_a_plus": winner_grading.get("why_not_a_plus") or war_grading.get("why_not_full_hand") or "",
            "upgrade_to_a_plus": winner_grading.get("upgrade_to_a_plus") or war_grading.get("what_would_upgrade_grade") or "",
            "downgrade_warning": winner_grading.get("downgrade_warning") or war_grading.get("what_would_downgrade_grade") or "",
            "user_commentary": latest_response.get("user_commentary") or "",
            "reason": latest_response.get("reason") or "",
            "memory_update": latest_response.get("memory_update") or "",
            "next_action_for_python": latest_response.get("next_action_for_python") or "",
        },
        "zones": {
            "battlefield_status": trigger_json.get("battlefield_status") or "UNKNOWN",
            "market_context": trigger_json.get("market_context") or "",
            "call_battle_area": trigger_json.get("call_battle_area") or {},
            "put_battle_area": trigger_json.get("put_battle_area") or {},
            "consolidation_zone": trigger_json.get("consolidation_zone") or {},
            "liquidity_zone": trigger_json.get("liquidity_zone") or {},
            "rejection_zones": trigger_json.get("rejection_zones") or [],
            "next_action": trigger_json.get("next_action") or "WATCH",
        },
        "market_data": {
            "latest_call_price": price_data.get("call"),
            "latest_put_price": price_data.get("put"),
            "call_rows": price_data.get("call_rows", 0),
            "put_rows": price_data.get("put_rows", 0),
            "last_sheet_snapshot_at": snapshot.get("timestamp") if snapshot else None,
        },
        "timestamps": {
            "last_battle_observation": observation.get("timestamp") if observation else None,
            "last_trigger_created": trigger.get("created_at") if trigger else None,
            "last_final_result": final_result.get("timestamp") if final_result else None,
        },
        "latest_final_result": {
            "winner": final_result.get("winner") if final_result else None,
            "confidence": final_result.get("confidence") if final_result else None,
            "trade_grade": final_result.get("trade_grade") if final_result else None,
            "reason": final_result.get("reason") if final_result else None,
            "timestamp": final_result.get("timestamp") if final_result else None,
        },
        # This is deliberately a separate top-level decision object.
        # It does not alter battle.* or winner_power.* in any way.
        "mtf_timing": _build_mtf_payload(),
    }


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "name": "SPX War Room Dashboard API",
        "status": "OK",
        "read_only": True,
        "version": "1.1.0",
        "current_endpoint": "/api/dashboard/current",
        "mtf_endpoint": "/api/mtf/current",
        "docs": "/docs",
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    path = _database_path()
    mtf = _build_mtf_payload()
    return {
        "status": "OK" if path.exists() else "DATABASE_MISSING",
        "database_path": str(path),
        "database_exists": path.exists(),
        "battle_system": "AVAILABLE" if path.exists() else "DATABASE_MISSING",
        "mtf_timing_system": mtf.get("status", "UNKNOWN"),
        "mtf_last_update": mtf.get("timestamp"),
        "timestamp": _utc_now_iso(),
    }


@app.get("/api/mtf/current")
def mtf_current(force_refresh: bool = Query(default=False)) -> dict[str, Any]:
    """Return only the independent Python MTF timing/blocker decision."""
    return _build_mtf_payload(force_refresh=force_refresh)


@app.get("/api/dashboard/current")
def current_dashboard() -> dict[str, Any]:
    with _connect() as conn:
        return _build_current_payload(conn)


@app.get("/api/dashboard/history")
def dashboard_history(limit: int = Query(default=50, ge=1, le=500)) -> dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, battle_session_id, timestamp, winner, confidence, trade_grade,
                   reason, screenshot_path, final_overall_grade, final_trade_grade
            FROM final_results
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return {"count": len(rows), "results": [dict(row) for row in rows]}


@app.get("/api/dashboard/grade-progression")
def grade_progression(
    battle_session_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    with _connect() as conn:
        session_id = battle_session_id
        if session_id is None:
            row = conn.execute("SELECT id FROM battle_sessions ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                return {"battle_session_id": None, "count": 0, "results": []}
            session_id = int(row["id"])

        rows = conn.execute(
            """
            SELECT id, battle_session_id, timestamp, overall_grade, trade_grade,
                   grade_confidence, grade_direction, factor_grades_json,
                   missing_confirmations_json, danger_signals_json,
                   why_not_full_hand, what_would_upgrade_grade, what_would_downgrade_grade
            FROM war_grade_history
            WHERE battle_session_id = ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()

    results = []
    for row in rows:
        item = dict(row)
        item["factor_grades"] = _json_load(item.pop("factor_grades_json"), [])
        item["missing_confirmations"] = _json_load(item.pop("missing_confirmations_json"), [])
        item["danger_signals"] = _json_load(item.pop("danger_signals_json"), [])
        results.append(item)

    return {"battle_session_id": session_id, "count": len(results), "results": results}


@app.get("/api/dashboard/timeline")
def dashboard_timeline(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, battle_session_id, timestamp, memory_update, overall_grade,
                   trade_grade, grade_confidence, llm_response_json
            FROM battle_observations
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    results = []
    for row in reversed(rows):
        item = dict(row)
        response = _json_load(item.pop("llm_response_json"), {})
        winner_grading = response.get("battle_winner_grading") or {}
        item.update(
            {
                "battle_status": response.get("battle_status"),
                "battle_phase": response.get("battle_phase") or (response.get("war_grading") or {}).get("battle_phase"),
                "decision": response.get("decision"),
                "entry_exit_action": response.get("entry_exit_action"),
                "winner": winner_grading.get("current_winner") or response.get("winner"),
                "winner_power_grade": winner_grading.get("winner_power_grade"),
                "winner_power_score": winner_grading.get("winner_power_score"),
                "user_commentary": response.get("user_commentary"),
                "reason": response.get("reason"),
            }
        )
        results.append(item)

    return {"count": len(results), "results": results}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "dashboard_api:app",
        host=os.getenv("DASHBOARD_API_HOST", "0.0.0.0"),
        port=int(os.getenv("DASHBOARD_API_PORT", "8000")),
        reload=False,
    )
