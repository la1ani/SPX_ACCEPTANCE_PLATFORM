"""Pydantic models for LLM responses and saved records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class FactorGrade(BaseModel):
    model_config = ConfigDict(extra="allow")
    factor: str = ""
    grade: str = "UNCLEAR"
    status: str = "UNCLEAR"
    direction_impact: str = "NEUTRAL"
    reason: str = ""


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
