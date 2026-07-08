from __future__ import annotations

from typing import Any


def _upper(value: Any) -> str:
    return str(value or "").upper()


def get_war_grading(response: dict[str, Any]) -> dict[str, Any]:
    grading = response.get("war_grading")
    return grading if isinstance(grading, dict) else {}


def get_winner_grading(response: dict[str, Any]) -> dict[str, Any]:
    grading = response.get("battle_winner_grading")
    if isinstance(grading, dict):
        return grading
    war = get_war_grading(response)
    direction = war.get("grade_direction") or response.get("winner") or "UNCLEAR"
    trade_grade = war.get("trade_grade") or response.get("trade_grade") or "WATCH_ONLY"
    score_map = {"FULL_HAND": 92, "LIGHT_HAND": 78, "SINGLE": 65, "WATCH_ONLY": 45, "NO_TRADE": 20, "EXIT": 10, "FLIP_WATCH": 35}
    power_grade_map = {"FULL_HAND": "A", "LIGHT_HAND": "B", "SINGLE": "B", "WATCH_ONLY": "C", "NO_TRADE": "D", "EXIT": "F", "FLIP_WATCH": "D"}
    return {
        "current_winner": direction,
        "winner_power_grade": power_grade_map.get(str(trade_grade).upper(), "UNCLEAR"),
        "winner_power_score": score_map.get(str(trade_grade).upper(), 0),
        "power_status": "UNCLEAR",
        "trade_size_suggestion": trade_grade,
        "support_break_grade": "UNCLEAR",
        "rejection_grade": "UNCLEAR",
        "holding_time_grade": "UNCLEAR",
        "volume_imbalance_grade": "UNCLEAR",
        "velocity_after_failure_grade": "UNCLEAR",
        "power_transfer_grade": "UNCLEAR",
        "winner_explanation": response.get("reason", ""),
        "why_not_a_plus": war.get("why_not_full_hand", ""),
        "upgrade_to_a_plus": war.get("what_would_upgrade_grade", ""),
        "downgrade_warning": war.get("what_would_downgrade_grade", ""),
    }


def get_factor_status(response: dict[str, Any], factor_name: str) -> dict[str, Any]:
    grading = get_war_grading(response)
    factors = grading.get("factor_grades") or []
    target = factor_name.lower().strip()
    for item in factors:
        if not isinstance(item, dict):
            continue
        if str(item.get("factor", "")).lower().strip() == target:
            return item
    return {"factor": factor_name, "grade": "UNCLEAR", "status": "MISSING", "direction_impact": "NEUTRAL", "reason": "LLM did not return this factor yet."}


def get_battle_phase(response: dict[str, Any]) -> str:
    grading = get_war_grading(response)
    explicit = response.get("battle_phase") or grading.get("battle_phase")
    if explicit:
        return str(explicit)
    status = _upper(response.get("battle_status"))
    decision = _upper(response.get("decision"))
    grade = _upper(grading.get("trade_grade") or response.get("trade_grade"))
    if status == "TRIGGER_TOUCHED" or decision in {"START_BATTLE", "FIGHTING_STARTED"}:
        return "FIGHTING_STARTED"
    if status == "FINAL" or decision in {"CALL_WINNER", "PUT_WINNER"}:
        return "FINAL_DECISION"
    if grade in {"FULL_HAND", "LIGHT_HAND", "SINGLE"}:
        return "ENTRY_READY"
    if grade in {"EXIT", "FLIP_WATCH"}:
        return "EXIT_DANGER"
    return "BATTLE_ACTIVE"


def get_alert_level(response: dict[str, Any]) -> str:
    phase = get_battle_phase(response)
    grading = get_war_grading(response)
    winner_grading = get_winner_grading(response)
    grade = _upper(grading.get("trade_grade") or response.get("trade_grade"))
    power_grade = _upper(winner_grading.get("winner_power_grade"))
    decision = _upper(response.get("decision"))
    if phase in {"FIGHTING_STARTED", "ENTRY_READY", "EXIT_DANGER", "FINAL_DECISION"}:
        return "BEST_ALERT"
    if decision in {"CALL_WINNER", "PUT_WINNER", "ENTRY_ALERT", "EXIT_ALERT"}:
        return "BEST_ALERT"
    if grade in {"FULL_HAND", "LIGHT_HAND", "SINGLE", "EXIT", "FLIP_WATCH"}:
        return "BEST_ALERT"
    if power_grade in {"A_PLUS", "A", "B"}:
        return "BEST_ALERT"
    return "COMMENTARY"


def build_rule_commentary(response: dict[str, Any]) -> str:
    grading = get_war_grading(response)
    winner_grading = get_winner_grading(response)
    weak = response.get("weak_side") or "UNKNOWN"
    strong = response.get("strong_side") or "UNKNOWN"
    winner = winner_grading.get("current_winner") or response.get("winner") or "NONE"
    grade = grading.get("trade_grade") or response.get("trade_grade") or "WATCH_ONLY"
    phase = get_battle_phase(response)

    holding = get_factor_status(response, "Holding Time")
    rejection = get_factor_status(response, "Rejection")
    support_break = get_factor_status(response, "Weak-Side Support Break")
    opposite_hold = get_factor_status(response, "Opposite-Side Support Hold")
    volume = get_factor_status(response, "Volume Imbalance")
    velocity = get_factor_status(response, "Velocity After Failure")
    power = get_factor_status(response, "Power Transfer")
    risk = get_factor_status(response, "Trade Risk")

    lines = [
        f"{phase}: current winner={winner}. Winner power grade={winner_grading.get('winner_power_grade')} / score={winner_grading.get('winner_power_score')}. Strong side={strong}. Weak side={weak}. Trade grade={grade}.",
        f"Power status: {winner_grading.get('power_status')} | Trade size: {winner_grading.get('trade_size_suggestion')}",
        f"Winner explanation: {winner_grading.get('winner_explanation')}",
        f"Support break grade: {winner_grading.get('support_break_grade')} | Rejection grade: {winner_grading.get('rejection_grade')} | Holding-time grade: {winner_grading.get('holding_time_grade')}",
        f"Volume grade: {winner_grading.get('volume_imbalance_grade')} | Velocity grade: {winner_grading.get('velocity_after_failure_grade')} | Power-transfer grade: {winner_grading.get('power_transfer_grade')}",
        f"Why not A+: {winner_grading.get('why_not_a_plus')}",
        f"Upgrade to A+: {winner_grading.get('upgrade_to_a_plus')}",
        f"Downgrade warning: {winner_grading.get('downgrade_warning')}",
        f"Holding time: {holding.get('status')} / {holding.get('grade')} - {holding.get('reason')}",
        f"Rejection: {rejection.get('status')} / {rejection.get('grade')} - {rejection.get('reason')}",
        f"Weak-side support break: {support_break.get('status')} / {support_break.get('grade')} - {support_break.get('reason')}",
        f"Opposite-side support hold: {opposite_hold.get('status')} / {opposite_hold.get('grade')} - {opposite_hold.get('reason')}",
        f"Volume imbalance: {volume.get('status')} / {volume.get('grade')} - {volume.get('reason')}",
        f"Velocity after failure: {velocity.get('status')} / {velocity.get('grade')} - {velocity.get('reason')}",
        f"Power transfer: {power.get('status')} / {power.get('grade')} - {power.get('reason')}",
        f"Risk: {risk.get('status')} / {risk.get('grade')} - {risk.get('reason')}",
        f"Missing: {', '.join(grading.get('missing_confirmations') or [])}",
        f"Danger: {', '.join(grading.get('danger_signals') or [])}",
        f"LLM reason: {response.get('reason', '')}",
    ]
    return "\n".join(lines)


def get_entry_exit_action(response: dict[str, Any]) -> str:
    phase = get_battle_phase(response)
    grading = get_war_grading(response)
    winner_grading = get_winner_grading(response)
    grade = _upper(grading.get("trade_grade") or response.get("trade_grade"))
    power_grade = _upper(winner_grading.get("winner_power_grade"))
    decision = _upper(response.get("decision"))
    if phase == "FIGHTING_STARTED" or decision in {"START_BATTLE", "FIGHTING_STARTED"}:
        return "FIGHTING_STARTED"
    if power_grade in {"A_PLUS", "A"} or grade in {"FULL_HAND", "LIGHT_HAND"} or decision in {"CALL_WINNER", "PUT_WINNER"}:
        return "ENTRY_ALERT"
    if power_grade == "B" or grade == "SINGLE":
        return "SINGLE_WATCH"
    if grade == "EXIT":
        return "EXIT_ALERT"
    if grade == "FLIP_WATCH":
        return "FLIP_WATCH"
    if grade == "NO_TRADE":
        return "NO_TRADE"
    return "HOLD_WATCH"
