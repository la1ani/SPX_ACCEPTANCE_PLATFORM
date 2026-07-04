"""SPX weak-side failure multi-agent system.

This module converts the user's SPX Weak-Side Failure Pattern into small,
separate agents.  Each agent reports facts only.  The final decision agent
combines the facts into WAIT, PLAY_CALL, PLAY_PUT, EXIT, or WARNING.

Core rule:
    Velocity comes AFTER failure.

Clean bearish setup:
    CALL reaches resistance -> CALL short hold/rejects -> CALL support breaks
    -> PUT holds support -> PUT volume imbalance -> PUT velocity expands.

Clean bullish setup:
    PUT reaches resistance/high pressure zone -> PUT short hold/rejects
    -> PUT support breaks -> CALL holds support -> CALL volume imbalance
    -> CALL velocity expands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Side = Literal["CALL", "PUT"]
TradeAction = Literal["WAIT", "PLAY_CALL", "PLAY_PUT", "EXIT", "WARNING"]


@dataclass
class SideSnapshot:
    """Current facts for one option side.

    The caller can build this from Google Sheet rows, TradingView webhook data,
    option-chain data, or backtest candles.
    """

    side: Side
    price: float | None = None
    resistance: float | None = None
    support: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float = 0.0
    velocity: float = 0.0
    hold_seconds_at_resistance: float = 0.0
    candles_held_at_resistance: int = 0
    rejected_from_resistance: bool = False
    support_broken: bool = False
    support_holding: bool = False
    reclaimed_broken_support: bool = False
    above_failure_zone: bool = False


@dataclass
class MarketSnapshot:
    """Both sides plus SPX direction context."""

    call: SideSnapshot
    put: SideSnapshot
    spx_direction: Literal["UP", "DOWN", "CHOP", "UNKNOWN"] = "UNKNOWN"
    timestamp: str | None = None


@dataclass
class AgentReport:
    agent: str
    status: str
    confidence: int
    details: dict = field(default_factory=dict)
    reason: str = ""


@dataclass
class WeakSideDecision:
    action: TradeAction
    confidence: int
    failed_side: Side | None
    strong_side: Side | None
    reason: str
    reports: list[AgentReport] = field(default_factory=list)


def _opposite(side: Side) -> Side:
    return "PUT" if side == "CALL" else "CALL"


def _snap(market: MarketSnapshot, side: Side) -> SideSnapshot:
    return market.call if side == "CALL" else market.put


def _score_to_100(value: float) -> int:
    return max(0, min(100, int(round(value))))


class ResistanceDetectionAgent:
    """Detect whether CALL or PUT reached resistance/high zone."""

    def analyze(self, market: MarketSnapshot) -> AgentReport:
        reached: list[Side] = []
        for side in ("CALL", "PUT"):
            s = _snap(market, side)
            at_resistance = False
            if s.price is not None and s.resistance is not None:
                at_resistance = s.price >= s.resistance
            if s.high is not None and s.resistance is not None:
                at_resistance = at_resistance or s.high >= s.resistance
            if at_resistance:
                reached.append(side)

        status = "RESISTANCE_REACHED" if reached else "NO_RESISTANCE_TOUCH"
        return AgentReport(
            agent="ResistanceDetectionAgent",
            status=status,
            confidence=90 if reached else 50,
            details={"sides_reached": reached},
            reason="One side reached resistance/high zone." if reached else "No side reached resistance yet.",
        )


class HoldingTimeAgent:
    """Find weak behavior: short hold at resistance, fast rejection, 1-3 candles only."""

    def __init__(self, weak_seconds: int = 120, strong_seconds: int = 300) -> None:
        self.weak_seconds = weak_seconds
        self.strong_seconds = strong_seconds

    def analyze(self, market: MarketSnapshot, side: Side) -> AgentReport:
        s = _snap(market, side)
        weak_hold = s.hold_seconds_at_resistance < self.weak_seconds or s.candles_held_at_resistance <= 3
        strong_hold = s.hold_seconds_at_resistance >= self.strong_seconds

        if strong_hold:
            status = "STRONG_HOLD"
            confidence = 85
            reason = f"{side} held resistance for {s.hold_seconds_at_resistance:.0f}s; not weak."
        elif weak_hold or s.rejected_from_resistance:
            status = "WEAK_HOLD"
            confidence = 90 if s.rejected_from_resistance else 75
            reason = f"{side} holding time is short; weak behavior detected."
        else:
            status = "UNCLEAR_HOLD"
            confidence = 50
            reason = f"{side} holding time is unclear."

        return AgentReport(
            agent="HoldingTimeAgent",
            status=status,
            confidence=confidence,
            details={
                "side": side,
                "hold_seconds": s.hold_seconds_at_resistance,
                "candles_held": s.candles_held_at_resistance,
                "rejected": s.rejected_from_resistance,
            },
            reason=reason,
        )


class ResistanceFailureAgent:
    """Confirm the first failure from resistance."""

    def analyze(self, market: MarketSnapshot, side: Side) -> AgentReport:
        s = _snap(market, side)
        failed = s.rejected_from_resistance and s.hold_seconds_at_resistance < 300
        return AgentReport(
            agent="ResistanceFailureAgent",
            status="RESISTANCE_FAILED" if failed else "NO_RESISTANCE_FAILURE",
            confidence=85 if failed else 45,
            details={"side": side, "rejected_from_resistance": s.rejected_from_resistance},
            reason=f"{side} rejected from resistance." if failed else f"{side} has not clearly failed resistance.",
        )


class SameSideVolumeTrapAgent:
    """Prevent chasing big same-side volume when that side cannot hold resistance."""

    def analyze(self, market: MarketSnapshot, side: Side) -> AgentReport:
        s = _snap(market, side)
        other = _snap(market, _opposite(side))
        total_volume = s.volume + other.volume
        volume_share = s.volume / total_volume if total_volume else 0.0
        trap = volume_share >= 0.60 and (s.rejected_from_resistance or s.hold_seconds_at_resistance < 120)

        return AgentReport(
            agent="SameSideVolumeTrapAgent",
            status="LIQUIDITY_TRAP" if trap else "NO_TRAP",
            confidence=85 if trap else 55,
            details={"side": side, "volume_share": round(volume_share, 3)},
            reason=f"{side} has big volume but cannot hold resistance; do not chase." if trap else "Volume is not acting like a clear trap yet.",
        )


class WeakSideSupportBreakAgent:
    """The real confirmation: weak side breaks its own support."""

    def analyze(self, market: MarketSnapshot, weak_side: Side) -> AgentReport:
        s = _snap(market, weak_side)
        broken = s.support_broken
        return AgentReport(
            agent="WeakSideSupportBreakAgent",
            status="WEAK_SUPPORT_BROKEN" if broken else "SUPPORT_NOT_BROKEN",
            confidence=95 if broken else 40,
            details={"weak_side": weak_side, "support_broken": broken},
            reason=f"{weak_side} support broke; weak-side failure confirmed." if broken else f"{weak_side} support has not broken; no full confirmation.",
        )


class OppositeSideSupportHoldingAgent:
    """Find the strong side: the side that holds support after weak-side failure."""

    def analyze(self, market: MarketSnapshot, strong_side: Side) -> AgentReport:
        s = _snap(market, strong_side)
        holding = s.support_holding
        return AgentReport(
            agent="OppositeSideSupportHoldingAgent",
            status="OPPOSITE_SUPPORT_HOLDING" if holding else "OPPOSITE_SUPPORT_NOT_HOLDING",
            confidence=90 if holding else 35,
            details={"strong_side": strong_side, "support_holding": holding},
            reason=f"{strong_side} is holding support; this is the strong side." if holding else f"{strong_side} is not holding support yet.",
        )


class PowerTransferAgent:
    """Detect pressure shifting from failed side to opposite side."""

    def analyze(self, market: MarketSnapshot, failed_side: Side) -> AgentReport:
        strong_side = _opposite(failed_side)
        failed = _snap(market, failed_side)
        strong = _snap(market, strong_side)
        transfer = failed.support_broken and strong.support_holding and strong.volume > failed.volume
        return AgentReport(
            agent="PowerTransferAgent",
            status="POWER_TRANSFER_CONFIRMED" if transfer else "POWER_TRANSFER_UNCLEAR",
            confidence=90 if transfer else 50,
            details={
                "from": failed_side,
                "to": strong_side,
                "failed_volume": failed.volume,
                "strong_volume": strong.volume,
            },
            reason=f"Power shifted from {failed_side} to {strong_side}." if transfer else "Power transfer is not fully confirmed.",
        )


class VolumeImbalanceAgent:
    """Confirm money shifting to the opposite side after failure."""

    def __init__(self, min_share: float = 0.60) -> None:
        self.min_share = min_share

    def analyze(self, market: MarketSnapshot, strong_side: Side) -> AgentReport:
        strong = _snap(market, strong_side)
        weak = _snap(market, _opposite(strong_side))
        total = strong.volume + weak.volume
        share = strong.volume / total if total else 0.0
        confirmed = share >= self.min_share
        return AgentReport(
            agent="VolumeImbalanceAgent",
            status="VOLUME_IMBALANCE_CONFIRMED" if confirmed else "NO_VOLUME_IMBALANCE",
            confidence=_score_to_100(share * 100),
            details={"strong_side": strong_side, "volume_share": round(share, 3)},
            reason=f"{strong_side} volume imbalance confirmed after weak-side failure." if confirmed else "Volume imbalance not strong enough yet.",
        )


class VelocityExpansionAgent:
    """Velocity is the result, not the first signal."""

    def __init__(self, min_velocity: float = 1.0) -> None:
        self.min_velocity = min_velocity

    def analyze(self, market: MarketSnapshot, strong_side: Side) -> AgentReport:
        s = _snap(market, strong_side)
        expanding = s.velocity >= self.min_velocity
        return AgentReport(
            agent="VelocityExpansionAgent",
            status="VELOCITY_EXPANDING" if expanding else "VELOCITY_NOT_READY",
            confidence=85 if expanding else 45,
            details={"strong_side": strong_side, "velocity": s.velocity},
            reason=f"{strong_side} velocity is expanding after failure." if expanding else "Velocity has not expanded yet; wait.",
        )


class EntryTimingAgent:
    """Allow entry only when failure sequence is complete."""

    def decide(self, failed_side: Side, reports: list[AgentReport]) -> WeakSideDecision:
        strong_side = _opposite(failed_side)
        required = {
            "ResistanceFailureAgent": "RESISTANCE_FAILED",
            "WeakSideSupportBreakAgent": "WEAK_SUPPORT_BROKEN",
            "OppositeSideSupportHoldingAgent": "OPPOSITE_SUPPORT_HOLDING",
            "VolumeImbalanceAgent": "VOLUME_IMBALANCE_CONFIRMED",
        }
        by_agent = {r.agent: r for r in reports}
        passed = [by_agent.get(agent) and by_agent[agent].status == status for agent, status in required.items()]
        velocity_ready = by_agent.get("VelocityExpansionAgent") and by_agent["VelocityExpansionAgent"].status == "VELOCITY_EXPANDING"

        if all(passed):
            confidence = int(sum(by_agent[a].confidence for a in required) / len(required))
            if velocity_ready:
                confidence = min(100, confidence + 5)
            action: TradeAction = "PLAY_PUT" if failed_side == "CALL" else "PLAY_CALL"
            return WeakSideDecision(
                action=action,
                confidence=confidence,
                failed_side=failed_side,
                strong_side=strong_side,
                reason=f"{failed_side} failed, broke support, {strong_side} held support, volume imbalance confirmed. Velocity is secondary confirmation.",
                reports=reports,
            )

        return WeakSideDecision(
            action="WAIT",
            confidence=50,
            failed_side=failed_side,
            strong_side=strong_side,
            reason="Full weak-side failure sequence is not complete. Wait.",
            reports=reports,
        )


class WeakSideRecoveryAgent:
    """After entry, check whether the failed side is coming back."""

    def analyze(self, market: MarketSnapshot, failed_side: Side) -> AgentReport:
        s = _snap(market, failed_side)
        recovery = s.reclaimed_broken_support or s.above_failure_zone or s.hold_seconds_at_resistance >= 300
        return AgentReport(
            agent="WeakSideRecoveryAgent",
            status="RECOVERY_WARNING" if recovery else "NO_RECOVERY",
            confidence=90 if recovery else 60,
            details={
                "failed_side": failed_side,
                "reclaimed_support": s.reclaimed_broken_support,
                "above_failure_zone": s.above_failure_zone,
                "hold_seconds": s.hold_seconds_at_resistance,
            },
            reason=f"{failed_side} is recovering; danger." if recovery else f"{failed_side} is not recovering yet.",
        )


class SupportFlipAgent:
    """Broken support should become resistance. If reclaimed, warning."""

    def analyze(self, market: MarketSnapshot, failed_side: Side) -> AgentReport:
        s = _snap(market, failed_side)
        if s.reclaimed_broken_support:
            return AgentReport(
                agent="SupportFlipAgent",
                status="SUPPORT_RECLAIMED_WARNING",
                confidence=90,
                details={"failed_side": failed_side},
                reason=f"{failed_side} broke back above old support; warning.",
            )
        return AgentReport(
            agent="SupportFlipAgent",
            status="BROKEN_SUPPORT_ACTING_AS_RESISTANCE",
            confidence=75,
            details={"failed_side": failed_side},
            reason=f"{failed_side} broken support is still acting as resistance; trade can continue.",
        )


class HoldingTimeChangeAgent:
    """If weak side starts holding longer, it may no longer be weak."""

    def __init__(self, danger_seconds: int = 300) -> None:
        self.danger_seconds = danger_seconds

    def analyze(self, market: MarketSnapshot, failed_side: Side) -> AgentReport:
        s = _snap(market, failed_side)
        danger = s.hold_seconds_at_resistance >= self.danger_seconds
        return AgentReport(
            agent="HoldingTimeChangeAgent",
            status="WEAK_SIDE_NO_LONGER_WEAK" if danger else "WEAK_SIDE_STILL_WEAK",
            confidence=88 if danger else 65,
            details={"failed_side": failed_side, "hold_seconds": s.hold_seconds_at_resistance},
            reason=f"{failed_side} started holding longer; exit warning." if danger else f"{failed_side} holding time remains short.",
        )


class OppositeSideFailureAgent:
    """Protect the trade by checking if the strong side stops holding support."""

    def analyze(self, market: MarketSnapshot, strong_side: Side) -> AgentReport:
        s = _snap(market, strong_side)
        failing = not s.support_holding or s.velocity < 0
        return AgentReport(
            agent="OppositeSideFailureAgent",
            status="STRONG_SIDE_FAILURE_EXIT" if failing else "STRONG_SIDE_STILL_VALID",
            confidence=90 if failing else 70,
            details={"strong_side": strong_side, "support_holding": s.support_holding, "velocity": s.velocity},
            reason=f"{strong_side} is failing; exit." if failing else f"{strong_side} still holds support.",
        )


class WeakSideFailureOrchestrator:
    """Run the whole pattern in the correct order.

    The orchestrator does not chase volume first.  It first finds the side
    with resistance failure and short holding time, then requires support
    break and opposite-side support hold before entry.
    """

    def __init__(self) -> None:
        self.resistance = ResistanceDetectionAgent()
        self.holding = HoldingTimeAgent()
        self.failure = ResistanceFailureAgent()
        self.trap = SameSideVolumeTrapAgent()
        self.support_break = WeakSideSupportBreakAgent()
        self.opposite_support = OppositeSideSupportHoldingAgent()
        self.power = PowerTransferAgent()
        self.volume = VolumeImbalanceAgent()
        self.velocity = VelocityExpansionAgent()
        self.entry = EntryTimingAgent()

    def decide(self, market: MarketSnapshot) -> WeakSideDecision:
        reports: list[AgentReport] = [self.resistance.analyze(market)]

        candidate_reports: dict[Side, list[AgentReport]] = {}
        candidate_scores: dict[Side, int] = {}

        for side in ("CALL", "PUT"):
            side_reports = [
                self.holding.analyze(market, side),
                self.failure.analyze(market, side),
                self.trap.analyze(market, side),
            ]
            candidate_reports[side] = side_reports
            candidate_scores[side] = sum(r.confidence for r in side_reports if r.status in {"WEAK_HOLD", "RESISTANCE_FAILED", "LIQUIDITY_TRAP"})

        failed_side: Side = "CALL" if candidate_scores["CALL"] >= candidate_scores["PUT"] else "PUT"
        strong_side = _opposite(failed_side)
        reports.extend(candidate_reports[failed_side])
        reports.extend(
            [
                self.support_break.analyze(market, failed_side),
                self.opposite_support.analyze(market, strong_side),
                self.power.analyze(market, failed_side),
                self.volume.analyze(market, strong_side),
                self.velocity.analyze(market, strong_side),
            ]
        )
        return self.entry.decide(failed_side, reports)

    def protect_trade(self, market: MarketSnapshot, failed_side: Side) -> WeakSideDecision:
        strong_side = _opposite(failed_side)
        reports = [
            WeakSideRecoveryAgent().analyze(market, failed_side),
            SupportFlipAgent().analyze(market, failed_side),
            HoldingTimeChangeAgent().analyze(market, failed_side),
            OppositeSideFailureAgent().analyze(market, strong_side),
        ]
        danger = [r for r in reports if r.status in {"RECOVERY_WARNING", "SUPPORT_RECLAIMED_WARNING", "WEAK_SIDE_NO_LONGER_WEAK", "STRONG_SIDE_FAILURE_EXIT"}]
        if danger:
            return WeakSideDecision(
                action="EXIT",
                confidence=max(r.confidence for r in danger),
                failed_side=failed_side,
                strong_side=strong_side,
                reason="In-trade protection warning: " + "; ".join(r.reason for r in danger),
                reports=reports,
            )
        return WeakSideDecision(
            action="WAIT",
            confidence=65,
            failed_side=failed_side,
            strong_side=strong_side,
            reason="Trade protection is clean; no exit warning yet.",
            reports=reports,
        )
