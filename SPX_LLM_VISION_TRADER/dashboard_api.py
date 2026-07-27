"""Read-only API for the opposite CALL/PUT expansion system."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import load_settings


app = FastAPI(
    title="SPX Opposite-Expansion API",
    description="CALL/PUT candle-body expansion confirmation. No support/resistance logic.",
    version="2.0.0",
)

origins = [item.strip() for item in os.getenv("DASHBOARD_ALLOWED_ORIGINS", "*").split(",") if item.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _state_path() -> Path:
    return load_settings().output_dir / "results" / "expansion_state.json"


def _empty_state() -> dict:
    return {
        "system": "OPPOSITE_CALL_PUT_EXPANSION",
        "status": "NO_DATA",
        "decision": "NO_TRADE",
        "entry_allowed": False,
        "reason": "Waiting for closed 3-minute or 15-minute candle data.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _current_state() -> dict:
    path = _state_path()
    if not path.exists():
        return _empty_state()
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    state["system"] = "OPPOSITE_CALL_PUT_EXPANSION"
    state["entry_allowed"] = state.get("decision") in {"CONFIRMED_CALL", "CONFIRMED_PUT"}
    return state


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "system": "OPPOSITE_CALL_PUT_EXPANSION",
        "support_resistance_enabled": False,
    }


@app.get("/api/dashboard/current")
def dashboard_current() -> dict:
    return _current_state()


@app.get("/api/expansion/current")
def expansion_current() -> dict:
    return _current_state()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
