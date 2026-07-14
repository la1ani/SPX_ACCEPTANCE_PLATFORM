"""
Self-learning loop.

Every decision the boss makes gets logged with the inputs that produced it.
Later, once we know what actually happened (did the strong side really move
fast after a "rejection"? did a called "no trade" zone actually stay flat?),
that outcome gets attached to the same record.

This is deliberately simple — not a black-box model. The whole point of the
project is that the reasoning stays legible and auditable, so the learning
mechanism is transparent too: it tracks hit/miss rates per zone and per
agent, and nudges the tunable thresholds in chart_agent.py / data_agent.py
in the direction the evidence supports, rather than fitting an opaque model.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import Decision, FinalCall, Zone


@dataclass
class OutcomeRecord:
    decision_id: str
    timestamp: str
    side: str
    final_call: str
    chart_zone: str
    data_zone: str
    aligned: bool
    confidence: float
    chart_evidence: dict
    data_evidence: dict
    outcome: Optional[str] = None
    outcome_notes: str = ""


class SelfLearningLog:
    def __init__(self, path: str | Path = "spx_agent_log.jsonl"):
        self.path = Path(path)
        self._records: dict[str, OutcomeRecord] = {}
        if self.path.exists():
            self._load()

    def record_decision(self, decision: Decision) -> str:
        decision_id = f"{decision.side.value}-{decision.timestamp.isoformat()}"
        record = OutcomeRecord(
            decision_id=decision_id,
            timestamp=decision.timestamp.isoformat(),
            side=decision.side.value,
            final_call=decision.final_call.value,
            chart_zone=decision.chart_verdict.zone.value,
            data_zone=decision.data_verdict.zone.value,
            aligned=decision.aligned,
            confidence=decision.confidence,
            chart_evidence=_json_safe(decision.chart_verdict.evidence),
            data_evidence=_json_safe(decision.data_verdict.evidence),
        )
        self._records[decision_id] = record
        self._append(record)
        return decision_id

    def record_outcome(self, decision_id: str, outcome: str, notes: str = "") -> None:
        if decision_id not in self._records:
            raise KeyError(f"No decision logged with id {decision_id}")
        record = self._records[decision_id]
        record.outcome = outcome
        record.outcome_notes = notes
        self._rewrite()

    def hit_rate_by_zone(self) -> dict[str, float]:
        by_zone: dict[str, list[bool]] = {}
        for r in self._records.values():
            if r.outcome is None:
                continue
            zone = r.chart_zone if r.aligned else "disagreement"
            by_zone.setdefault(zone, []).append(r.outcome == "confirmed")
        return {zone: sum(hits) / len(hits) for zone, hits in by_zone.items() if hits}

    def false_no_trade_rate(self) -> Optional[float]:
        no_trades = [
            r for r in self._records.values()
            if r.final_call == FinalCall.NO_TRADE.value and r.outcome is not None
        ]
        if not no_trades:
            return None
        false_count = sum(1 for r in no_trades if r.outcome == "false_signal")
        return false_count / len(no_trades)

    def false_trade_rate(self) -> Optional[float]:
        trades = [
            r for r in self._records.values()
            if r.final_call in (FinalCall.TRADE_BULLISH.value, FinalCall.TRADE_BEARISH.value,
                                 FinalCall.CAUTIOUS_TRADE.value)
            and r.outcome is not None
        ]
        if not trades:
            return None
        false_count = sum(1 for r in trades if r.outcome == "false_signal")
        return false_count / len(trades)

    def suggest_threshold_adjustment(self) -> dict[str, str]:
        suggestions = {}
        false_trade = self.false_trade_rate()
        false_no_trade = self.false_no_trade_rate()

        if false_trade is not None and false_trade > 0.35:
            suggestions["confidence_threshold"] = (
                f"False-trade rate is {false_trade:.0%} — consider raising "
                "Boss.min_confidence_for_trade to be more conservative."
            )
        if false_no_trade is not None and false_no_trade > 0.5:
            suggestions["no_trade_sensitivity"] = (
                f"False-no-trade rate is {false_no_trade:.0%} — the system may be "
                "over-calling no-trade and missing real moves; consider loosening "
                "velocity_flat_threshold / body_ratio_conviction slightly."
            )
        return suggestions

    def _append(self, record: OutcomeRecord) -> None:
        with self.path.open("a") as f:
            f.write(json.dumps(asdict(record)) + "\n")

    def _rewrite(self) -> None:
        with self.path.open("w") as f:
            for record in self._records.values():
                f.write(json.dumps(asdict(record)) + "\n")

    def _load(self) -> None:
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                self._records[data["decision_id"]] = OutcomeRecord(**data)


def _json_safe(evidence: dict) -> dict:
    import dataclasses
    import enum

    def convert(value):
        if isinstance(value, enum.Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {f.name: convert(getattr(value, f.name)) for f in dataclasses.fields(value)}
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(v) for v in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    return {k: convert(v) for k, v in evidence.items()}
