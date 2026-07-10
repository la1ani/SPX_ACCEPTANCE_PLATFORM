"""Pydantic models for LLM responses and saved records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stringify_llm_value(value: Any, default: str = "") -> str:
    """Coerce flexible LLM outputs into safe strings for strict Pydantic fields."""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " | ".join(str(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}: {v}" for k, v in value.items())
    return str(value)


def coerce_llm_bool(value: Any) -> bool:
    """Coerce flexible LLM confirmation outputs without creating trading logic.

    The LLM sometimes returns graded words such as MILD, MODERATE, or STRONG
    for fields whose storage schema is boolean. This function only normalizes
    response shape so Pydantic validation does not crash the live battle loop.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, dict):
        for key in ("confirmed", "present", "exists", "value", "status"):
            if key in value:
                return coerce_llm_bool(value[key])
        return bool(value)
    if isinstance(value, list):
        return any(coerce_llm_bool(v) for v in value)

    text = str(value).strip().upper()
    false_values = {
        "", "0", "FALSE", "NO", "NONE", "NULL", "N/A", "NA",
        "ABSENT", "NOT_PRESENT", "NOT CONFIRMED", "UNCONFIRMED",
        "UNCLEAR", "UNKNOWN", "NEGATIVE", "FAILED", "FAIL",
    }
    true_values = {
        "1", "TRUE", "YES", "Y", "PRESENT", "CONFIRMED", "POSITIVE",
        "MILD", "WEAK", "MODERATE", "MEDIUM", "STRONG", "HIGH",
        "VERY_STRONG", "VERY STRONG", "PARTIAL", "DEVELOPING",
    }
    if text in false_values:
        return False
    if text in true_values:
        return True

    if any(token in text for token in ("NO ", "NOT ", "ABSENT", "UNCONFIRMED", "FAILED")):
        return False
    if any(token in text for token in ("CONFIRMED", "PRESENT", "MILD", "MODERATE", "STRONG", "PARTIAL", "DEVELOPING")):
        return True
    return False


class Zone(BaseModel):
    model_config = ConfigDict(extra="allow")
    exists: bool = False
    zone_low: Optional[float] = None
    zone_high: Optional[float] = None
    visual_reason: str = ""
    trigger_condition: str = ""
    invalidation_condition: str = ""


class ConsolidationZone(Zone):
    possible_outcomes: list[str] = Field(default_factory=list)


class LiquidityZone(BaseModel):
    model_config = ConfigDict(extra="allow")
    exists: bool = False
    zone_low: Optional[float] = None
    zone_high: Optional[float] = None
    visual_reason: str = ""


class WatchPlan(BaseModel):
    model_config = ConfigDict(extra="allow")
    conditions_to_watch: list[Any] = Field(default_factory=list)
    call_llm_when: list[Any] = Field(default_factory=list)
    cancel_trigger_when: list[Any] = Field(default_factory=list)
    new_screenshot_when: list[Any] = Field(default_factory=list)


class PythonInstructions(BaseModel):
    allowed_actions: list[str] = Field(default_factory=list)
    not_allowed_actions: list[str] = Field(default_factory=list)


class TriggerPlan(BaseModel):
    model_config = ConfigDict(extra="allow")
    battlefield_status: str = "WAITING"
    market_context: str = ""
    call_battle_area: Zone = Field(default_factory=Zone)
    put_battle_area: Zone = Field(default_factory=Zone)
    consolidation_zone: ConsolidationZone = Field(default_factory=ConsolidationZone)
    liquidity_zone: LiquidityZone = Field(default_factory=LiquidityZone)
    rejection_zones: list[Any] = Field(default_factory=list)
    watch_plan: WatchPlan = Field(default_factory=WatchPlan)
    python_instructions: PythonInstructions = Field(default_factory=PythonInstructions)
    next_action: str = "WATCH"

    @field_validator("battlefield_status", "market_context", "next_action", mode="before")
    @classmethod
    def _coerce_trigger_strings(cls, value: Any) -> str:
        return stringify_llm_value(value)

    @field_validator("call_battle_area", "put_battle_area", mode="before")
    @classmethod
    def _coerce_zone(cls, value: Any) -> Any:
        if value is None or isinstance(value, str) or isinstance(value, list):
            return Zone().model_dump()
        return value

    @field_validator("consolidation_zone", mode="before")
    @classmethod
    def _coerce_consolidation_zone(cls, value: Any) -> Any:
        if value is None or isinstance(value, str) or isinstance(value, list):
            return ConsolidationZone().model_dump()
        return value

    @field_validator("liquidity_zone", mode="before")
    @classmethod
    def _coerce_liquidity_zone(cls, value: Any) -> Any:
        if value is None or isinstance(value, str) or isinstance(value, list):
            return LiquidityZone().model_dump()
        return value

    @field_validator("rejection_zones", mode="before")
    @classmethod
    def _coerce_rejection_zones(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        return [value]

    @field_validator("watch_plan", mode="before")
    @classmethod
    def _coerce_watch_plan(cls, value: Any) -> Any:
        if value is None:
            return WatchPlan().model_dump()
        if isinstance(value, str):
            return {
                "conditions_to_watch": [value],
                "call_llm_when": ["chart becomes readable", "new screenshot available"],
                "cancel_trigger_when": [],
                "new_screenshot_when": ["TradingView finishes loading", "user logs in", "chart data becomes visible"],
            }
        if isinstance(value, list):
            return {"conditions_to_watch": value}
        return value

    @field_validator("python_instructions", mode="before")
    @classmethod
    def _coerce_python_instructions(cls, value: Any) -> Any:
        if value is None:
            return PythonInstructions().model_dump()
        if isinstance(value, list):
            return {"allowed_actions": [str(v) for v in value], "not_allowed_actions": []}
        if isinstance(value, str):
            return {"allowed_actions": [value], "not_allowed_actions": []}
        return value


class FactorGrade(BaseModel):
    model_config = ConfigDict(extra="allow")
    factor: str = ""
    grade: str = "UNCLEAR"
    status: str = "UNCLEAR"
    direction_impact: str = "NEUTRAL"
    reason: str = ""

    @field_validator("factor", "grade", "status", "direction_impact", "reason", mode="before")
    @classmethod
    def _coerce_factor_strings(cls, value: Any) -> str:
        return stringify_llm_value(value)


class WarGrade(BaseModel):
    model_config = ConfigDict(extra="allow")
    overall_grade: str = "UNCLEAR"
    trade_grade: str = "WATCH_ONLY"
    grade_confidence: str = "LOW"
    grade_direction: str = "NONE"
    factor_grades: list[FactorGrade] = Field(default_factory=list)
    missing_confirmations: list[str] = Field(default_factory=list)
    danger_signals: list[str] = Field(default_factory=list)
    why_not_full_hand: str = ""
    what_would_upgrade_grade: str = ""
    what_would_downgrade_grade: str = ""

    @field_validator("overall_grade", "trade_grade", "grade_confidence", "grade_direction", "why_not_full_hand", "what_would_upgrade_grade", "what_would_downgrade_grade", mode="before")
    @classmethod
    def _coerce_war_strings(cls, value: Any) -> str:
        return stringify_llm_value(value)

    @field_validator("missing_confirmations", "danger_signals", mode="before")
    @classmethod
    def _coerce_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [stringify_llm_value(v) for v in value]
        return [stringify_llm_value(value)]


class BattleDecision(BaseModel):
    model_config = ConfigDict(extra="allow")
    battle_status: str = "ACTIVE"
    decision: str = "CONTINUE_ANALYZING"
    trigger_type: str = "BATTLE_ZONE_TRIGGER"
    attacking_side: str = "UNKNOWN"
    weak_side: str = "UNKNOWN"
    strong_side: str = "UNKNOWN"
    holding_time_status: str = "UNCLEAR"
    rejection_confirmed: bool = False
    weak_side_support_broken: bool = False
    opposite_side_holding_support: bool = False
    opposite_side_volume_imbalance: bool = False
    velocity_after_failure: bool = False
    war_grading: WarGrade = Field(default_factory=WarGrade)
    winner: str = "NONE"
    trade_grade: str = "WATCH_ONLY"
    confidence: str = "LOW"
    reason: str = ""
    memory_update: str = ""
    next_action_for_python: str = "GET_NEW_SCREENSHOT_AND_SHEET_DATA"
    next_check_seconds: int = 10

    @field_validator(
        "battle_status",
        "decision",
        "trigger_type",
        "attacking_side",
        "weak_side",
        "strong_side",
        "holding_time_status",
        "winner",
        "trade_grade",
        "confidence",
        "reason",
        "memory_update",
        "next_action_for_python",
        mode="before",
    )
    @classmethod
    def _coerce_decision_strings(cls, value: Any) -> str:
        return stringify_llm_value(value)

    @field_validator(
        "rejection_confirmed",
        "weak_side_support_broken",
        "opposite_side_holding_support",
        "opposite_side_volume_imbalance",
        "velocity_after_failure",
        mode="before",
    )
    @classmethod
    def _coerce_confirmation_bools(cls, value: Any) -> bool:
        return coerce_llm_bool(value)


class SheetSnapshot(BaseModel):
    timestamp: str = Field(default_factory=utc_now_iso)
    call_data: list[dict[str, Any]] = Field(default_factory=list)
    put_data: list[dict[str, Any]] = Field(default_factory=list)


class BattleSession(BaseModel):
    id: Optional[int] = None
    trigger_plan_id: int
    started_at: str = Field(default_factory=utc_now_iso)
    ended_at: Optional[str] = None
    trigger_type: str = "BATTLE_ZONE_TRIGGER"
    status: str = "ACTIVE"
    final_decision: str = ""
    winner: str = "NONE"
    trade_grade: str = "WATCH_ONLY"
    confidence: str = "LOW"
    final_reason: str = ""
    memory: list[dict[str, Any]] = Field(default_factory=list)


class FinalResult(BaseModel):
    timestamp: str = Field(default_factory=utc_now_iso)
    winner: str = "NONE"
    confidence: str = "LOW"
    trade_grade: str = "WATCH_ONLY"
    reason: str = ""
    screenshot_path: str = ""
    result_json: dict[str, Any] = Field(default_factory=dict)
    final_overall_grade: str = "UNCLEAR"
    final_trade_grade: str = "WATCH_ONLY"
    final_factor_grades_json: list[dict[str, Any]] = Field(default_factory=list)
    grade_progression_json: list[dict[str, Any]] = Field(default_factory=list)
