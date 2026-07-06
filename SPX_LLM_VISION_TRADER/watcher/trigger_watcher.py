from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
import time


@dataclass
class WatchResult:
    action: str
    trigger_type: str = "BATTLE_ZONE_TRIGGER"
    reason: str = ""


class TriggerWatcher:
    def __init__(self, plan: dict[str, Any], max_age_seconds: int = 300):
        self.plan = plan
        self.created_at = time.time()
        self.max_age_seconds = max_age_seconds

    def update_plan(self, plan: dict[str, Any]) -> None:
        self.plan = plan
        self.created_at = time.time()

    def _latest_price(self, rows: list[dict[str, Any]]) -> Optional[float]:
        if not rows:
            return None
        row = rows[-1]
        for key in ("price", "close", "last", "ltp"):
            value = row.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            try:
                if value not in (None, ""):
                    return float(str(value).replace(",", ""))
            except ValueError:
                continue
        return None

    def _in_zone(self, value: Optional[float], zone: dict[str, Any]) -> bool:
        if value is None:
            return False
        if not zone or not zone.get("exists", False):
            return False
        low = zone.get("zone_low")
        high = zone.get("zone_high")
        if low is None or high is None:
            return False
        low_f, high_f = sorted((float(low), float(high)))
        return low_f <= value <= high_f

    def check(self, call_rows: list[dict[str, Any]], put_rows: list[dict[str, Any]]) -> WatchResult:
        if time.time() - self.created_at > self.max_age_seconds:
            return WatchResult(action="NEW_TRIGGER_REQUIRED", reason="Plan age exceeded max_age_seconds")
        if str(self.plan.get("battlefield_status", "")).upper() in {"INVALID", "NEW_TRIGGER_REQUIRED"}:
            return WatchResult(action="NEW_TRIGGER_REQUIRED", reason="LLM plan status requests new plan")
        next_action = str(self.plan.get("next_action", "WATCH")).upper()
        if next_action == "START_BATTLE":
            return WatchResult(action="START_BATTLE", trigger_type="BATTLE_ZONE_TRIGGER", reason="LLM next_action requested battle session")
        if next_action == "NEW_SCREENSHOT":
            return WatchResult(action="NEW_TRIGGER_REQUIRED", reason="LLM next_action requested new screenshot")
        call_price = self._latest_price(call_rows)
        put_price = self._latest_price(put_rows)
        if self._in_zone(call_price, self.plan.get("call_battle_area", {})):
            return WatchResult(action="START_BATTLE", trigger_type="BATTLE_ZONE_TRIGGER", reason="CALL rows touched LLM call area")
        if self._in_zone(put_price, self.plan.get("put_battle_area", {})):
            return WatchResult(action="START_BATTLE", trigger_type="BATTLE_ZONE_TRIGGER", reason="PUT rows touched LLM put area")
        consolidation = self.plan.get("consolidation_zone", {})
        if self._in_zone(call_price, consolidation) or self._in_zone(put_price, consolidation):
            return WatchResult(action="START_BATTLE", trigger_type="CONSOLIDATION_ZONE_TRIGGER", reason="Rows touched LLM consolidation area")
        return WatchResult(action="WATCH", reason="No LLM trigger condition touched")
