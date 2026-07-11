from __future__ import annotations

import json
from typing import Any

from fastapi import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from dashboard_api import app, _build_current_payload, _connect, _utc_now_iso


def _normalize_signal(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if "BUY" in text or text in {"BULL", "BULLISH", "LONG", "CALL"}:
        return "BUY"
    if "SELL" in text or text in {"BEAR", "BEARISH", "SHORT", "PUT"}:
        return "SELL"
    return text


def _signal_counts(signals: dict[str, Any]) -> dict[str, int]:
    values = [_normalize_signal(signals.get(tf)) for tf in ("1m", "3m", "5m")]
    return {
        "buy": sum(value == "BUY" for value in values),
        "sell": sum(value == "SELL" for value in values),
        "known": sum(value in {"BUY", "SELL"} for value in values),
    }


def _confidence_value(value: Any) -> int:
    if isinstance(value, (int, float)):
        return max(0, min(100, int(round(float(value)))))
    text = str(value or "").strip().upper()
    mapping = {"VERY_HIGH": 95, "HIGH": 85, "MEDIUM": 65, "MODERATE": 60, "LOW": 40, "VERY_LOW": 20}
    return mapping.get(text, 0)


def build_signal_alignment(current: dict[str, Any]) -> dict[str, Any]:
    mtf = current.get("mtf_timing") or {}
    signals = mtf.get("signals") or {}
    call_signals = signals.get("call") or {}
    put_signals = signals.get("put") or {}
    call_counts = _signal_counts(call_signals)
    put_counts = _signal_counts(put_signals)

    battle = current.get("battle") or {}
    confirmations = current.get("confirmations") or {}
    factor_grades = current.get("factor_grades") or {}
    mtf_decision = mtf.get("decision") or {}

    battle_winner = str(battle.get("current_winner") or battle.get("winner") or "NONE").upper()
    candidate_side = str(mtf.get("candidate_side") or "NONE").upper()
    entry_allowed = bool(mtf_decision.get("entry_allowed"))
    action = str(mtf_decision.get("action") or "WAIT").upper()
    grade = str(mtf_decision.get("grade") or battle.get("trade_grade") or "UNCLEAR").upper()

    call_aligned = call_counts["known"] >= 2 and call_counts["buy"] >= 2 and put_counts["sell"] >= 2
    put_aligned = put_counts["known"] >= 2 and put_counts["buy"] >= 2 and call_counts["sell"] >= 2

    direction = "NONE"
    if call_aligned:
        direction = "CALL"
    elif put_aligned:
        direction = "PUT"
    elif candidate_side in {"CALL", "PUT"}:
        direction = candidate_side
    elif battle_winner in {"CALL", "PUT"}:
        direction = battle_winner

    battle_agrees = direction in {"CALL", "PUT"} and battle_winner == direction
    mtf_agrees = direction in {"CALL", "PUT"} and candidate_side == direction

    support_broken = bool(confirmations.get("weak_side_support_broken"))
    rejection_confirmed = bool(confirmations.get("rejection_confirmed"))
    velocity_confirmed = bool(confirmations.get("velocity_after_failure"))
    opposite_support_holding = bool(confirmations.get("opposite_side_holding_support"))
    opposite_volume = bool(confirmations.get("opposite_side_volume_imbalance"))

    confirmations_count = sum(
        [support_broken, rejection_confirmed, velocity_confirmed, opposite_support_holding, opposite_volume]
    )

    score = 0
    if direction in {"CALL", "PUT"}:
        score += 20
    if call_aligned or put_aligned:
        score += 30
    if battle_agrees:
        score += 15
    if mtf_agrees:
        score += 10
    if entry_allowed:
        score += 10
    score += confirmations_count * 3
    score = min(100, score)

    battle_confidence = _confidence_value(battle.get("confidence"))
    if battle_confidence:
        score = min(100, round((score + battle_confidence) / 2))

    if mtf.get("status") not in {"OK", "ACTIVE"} and not any((call_counts["known"], put_counts["known"])):
        state = "NO_DATA"
        direction = "NONE"
        score = 0
    elif direction == "NONE":
        state = "NO_ALIGNMENT"
    elif entry_allowed and action == "FULL_HAND" and score >= 80:
        state = "FULL_HAND"
    elif entry_allowed and action in {"LIGHT_HAND", "FULL_HAND"} and score >= 60:
        state = "LIGHT_HAND"
    elif call_aligned or put_aligned:
        state = "ALIGNING"
    else:
        state = "BATTLE_ZONE"

    return {
        "status": "ACTIVE" if state != "NO_DATA" else "NO_DATA",
        "timestamp": current.get("generated_at") or _utc_now_iso(),
        "source": {
            "battle": "LLM_BATTLE_ENGINE",
            "timing": "PYTHON_MTF_TIMING_BLOCKER",
            "uses_live_data_only": True,
        },
        "call": {
            "signals": call_signals,
            "buy_count_1m_3m_5m": call_counts["buy"],
            "sell_count_1m_3m_5m": call_counts["sell"],
            "aligned": call_aligned,
        },
        "put": {
            "signals": put_signals,
            "buy_count_1m_3m_5m": put_counts["buy"],
            "sell_count_1m_3m_5m": put_counts["sell"],
            "aligned": put_aligned,
        },
        "alignment": {
            "direction": direction,
            "state": state,
            "confidence": score,
            "battle_winner": battle_winner,
            "mtf_candidate_side": candidate_side,
            "battle_agrees": battle_agrees,
            "mtf_agrees": mtf_agrees,
            "entry_allowed": entry_allowed,
            "action": action,
            "grade": grade,
        },
        "confirmations": {
            "rejection_confirmed": rejection_confirmed,
            "weak_side_support_broken": support_broken,
            "opposite_side_holding_support": opposite_support_holding,
            "opposite_side_volume_imbalance": opposite_volume,
            "velocity_after_failure": velocity_confirmed,
            "count": confirmations_count,
        },
        "factor_grades": factor_grades,
        "reason": mtf_decision.get("reason") or (current.get("guidance") or {}).get("reason") or "",
    }


@app.get("/api/signal-alignment")
def signal_alignment() -> dict[str, Any]:
    with _connect() as conn:
        current = _build_current_payload(conn)
    return build_signal_alignment(current)


class SignalAlignmentInjectionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path != "/api/dashboard/current" or response.status_code != 200:
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                payload["signal_alignment"] = build_signal_alignment(payload)
                body = json.dumps(payload, default=str).encode("utf-8")
        except (TypeError, ValueError, json.JSONDecodeError):
            pass

        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )


app.add_middleware(SignalAlignmentInjectionMiddleware)


if __name__ == "__main__":
    import os
    import uvicorn

    uvicorn.run(
        "dashboard_api_with_alignment:app",
        host=os.getenv("DASHBOARD_API_HOST", "0.0.0.0"),
        port=int(os.getenv("DASHBOARD_API_PORT", "8000")),
        reload=False,
    )
