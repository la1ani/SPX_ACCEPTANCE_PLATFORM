"""
Data-reasoning agent.

Reasons over the live Google Sheet ticks (call price, put price, volumes)
to judge velocity, volume, holding time, and the call/put see-saw
correlation. Learns to tell the difference between:

  - a consolidation signature: flat velocity, thin volume, no correlation
  - a momentum signature: real velocity + volume in one direction
  - a rejection signature: a spike toward a level, then a fast reversal
    on the other side (the "rejection -> other side moves fast" pattern)

This agent never looks at the chart image or candle shapes — it only sees
numbers. Its whole value is being an independent check on the chart agent
using completely different evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev

from .models import LevelRead, SheetTick, Verdict, Zone


@dataclass
class DataAgentParams:
    """Tunable parameters, nudged over time by the self-learning loop."""
    velocity_flat_threshold: float = 0.02      # price change per second below this = "dead"
    volume_spike_multiplier: float = 1.8       # current volume vs. recent avg to count as a spike
    holding_window_seconds: int = 45           # how long price must sit near a level to count as "holding"
    near_level_pct: float = 0.0015
    correlation_lookback: int = 20


class DataReasoningAgent:
    """
    Works purely from live tick data (no chart image). Classifies the
    current zone using velocity, volume, holding time, and the call/put
    see-saw correlation.
    """

    def __init__(self, params: DataAgentParams | None = None):
        self.params = params or DataAgentParams()

    # -- public API ---------------------------------------------------

    def evaluate(
        self,
        ticks: list[SheetTick],
        nearby_level: LevelRead | None = None,
        level_side_is_call: bool = True,
        previous_holding_seconds: float | None = None,
    ) -> Verdict:
        if len(ticks) < 3:
            return Verdict(
                zone=Zone.CONSOLIDATION,
                confidence=0.3,
                reasoning="Not enough live ticks yet to judge velocity or volume — default to no-trade.",
                evidence={},
            )

        call_velocity = self._velocity([t.call_price for t in ticks], [t.timestamp for t in ticks])
        put_velocity = self._velocity([t.put_price for t in ticks], [t.timestamp for t in ticks])
        volume_signature = self._volume_signature(ticks)
        seesaw = self._seesaw_correlation(ticks)
        holding = None
        if nearby_level is not None:
            level_prices = [t.call_price if level_side_is_call else t.put_price for t in ticks]
            holding = self._holding_time(ticks, level_prices, nearby_level)

        # Rejection-just-occurred check: was clearly dwelling at a level moments
        # ago (previous_holding_seconds was substantial), and is now NOT holding
        # anymore (holding dropped back near zero) — that transition IS the
        # rejection event itself, the earliest possible entry trigger, distinct
        # from waiting for the strong side's own momentum to build up separately.
        this_side_velocity = call_velocity if level_side_is_call else put_velocity
        rejection_just_occurred = bool(
            previous_holding_seconds is not None
            and previous_holding_seconds >= self.params.holding_window_seconds * 0.5
            and (holding is None or holding < self.params.holding_window_seconds * 0.2)
        )

        evidence = {
            "call_velocity": call_velocity,
            "put_velocity": put_velocity,
            "volume_signature": volume_signature,
            "seesaw_correlation": seesaw,
            "holding_seconds": holding,
            "entry_price": ticks[-1].call_price if level_side_is_call else ticks[-1].put_price,
            "rejection_just_occurred": rejection_just_occurred,
        }

        return self._classify(call_velocity, put_velocity, volume_signature, seesaw, holding, evidence)

    # -- individual measures --------------------------------------------

    @staticmethod
    def _velocity(prices: list[float], timestamps) -> float:
        """Average |price change| per second over the window."""
        if len(prices) < 2:
            return 0.0
        total_change = 0.0
        total_seconds = 0.0
        for i in range(1, len(prices)):
            dt = (timestamps[i] - timestamps[i - 1]).total_seconds()
            if dt <= 0:
                continue
            total_change += abs(prices[i] - prices[i - 1])
            total_seconds += dt
        return total_change / total_seconds if total_seconds > 0 else 0.0

    def _volume_signature(self, ticks: list[SheetTick]) -> dict:
        call_vols = [t.call_volume for t in ticks]
        put_vols = [t.put_volume for t in ticks]
        recent_call, recent_put = call_vols[-3:], put_vols[-3:]
        base_call = mean(call_vols[:-3]) if len(call_vols) > 3 else mean(call_vols)
        base_put = mean(put_vols[:-3]) if len(put_vols) > 3 else mean(put_vols)
        call_spike = mean(recent_call) / max(base_call, 1e-6)
        put_spike = mean(recent_put) / max(base_put, 1e-6)
        return {"call_spike_ratio": call_spike, "put_spike_ratio": put_spike}

    def _seesaw_correlation(self, ticks: list[SheetTick]) -> float:
        """
        -1..+1. Strongly negative = healthy see-saw (call up, put down, or
        vice versa) as expected by the core thesis. Near zero = the two
        sides are moving independently, which itself is a weaker/less
        reliable regime.
        """
        window = ticks[-self.params.correlation_lookback:]
        calls = [t.call_price for t in window]
        puts = [t.put_price for t in window]
        if len(calls) < 3:
            return 0.0

        call_mean, put_mean = mean(calls), mean(puts)
        call_sd, put_sd = pstdev(calls) or 1e-9, pstdev(puts) or 1e-9

        cov = sum((c - call_mean) * (p - put_mean) for c, p in zip(calls, puts)) / len(calls)
        return cov / (call_sd * put_sd)

    def _holding_time(
        self, ticks: list[SheetTick], prices: list[float], level: LevelRead
    ) -> float:
        """
        Seconds price has dwelled within `near_level_pct` of the given
        level, counting back from the most recent tick. This is dwell time
        AT the level, not time spent climbing to it.
        """
        p = self.params
        held_since = None
        for tick, price in zip(reversed(ticks), reversed(prices)):
            near = abs(price - level.price) / level.price <= p.near_level_pct
            if near:
                held_since = tick.timestamp
            else:
                break
        if held_since is None:
            return 0.0
        return (ticks[-1].timestamp - held_since).total_seconds()

    # -- classification --------------------------------------------------

    def _classify(
        self,
        call_velocity: float,
        put_velocity: float,
        volume_signature: dict,
        seesaw: float,
        holding: float | None,
        evidence: dict,
    ) -> Verdict:
        p = self.params
        max_velocity = max(call_velocity, put_velocity)
        max_spike = max(volume_signature["call_spike_ratio"], volume_signature["put_spike_ratio"])

        # Rejection signature: a volume/velocity spike right at a level, held briefly, we don't
        # decide direction here — the boss combines this with the chart agent's directional read.
        if holding is not None and holding >= p.holding_window_seconds and max_spike < p.volume_spike_multiplier:
            return Verdict(
                zone=Zone.CONSOLIDATION,
                confidence=0.7,
                reasoning=(
                    f"Price has been dwelling at the level for {holding:.0f}s with no volume "
                    "conviction behind it — classic zero-holding-strength rejection signature."
                ),
                evidence=evidence,
            )

        # Flat velocity + no volume spike + weak see-saw = plain consolidation.
        if max_velocity < p.velocity_flat_threshold and max_spike < p.volume_spike_multiplier:
            return Verdict(
                zone=Zone.CONSOLIDATION,
                confidence=0.7,
                reasoning=(
                    "Velocity and volume are both flat right now — nothing is actually moving, "
                    "this is dead/chop conditions."
                ),
                evidence=evidence,
            )

        # Real momentum: velocity + volume spike + healthy negative see-saw correlation.
        if max_velocity >= p.velocity_flat_threshold and max_spike >= p.volume_spike_multiplier:
            direction_is_call = call_velocity >= put_velocity
            if seesaw <= -0.3:
                zone = Zone.BULLISH if direction_is_call else Zone.BEARISH
                return Verdict(
                    zone=zone,
                    confidence=min(0.5 + max_spike / 10 + abs(seesaw) * 0.2, 0.95),
                    reasoning=(
                        f"Velocity and volume both confirm a real move on the "
                        f"{'call' if direction_is_call else 'put'} side, with the expected "
                        "see-saw reaction on the other side — this looks like genuine momentum."
                    ),
                    evidence=evidence,
                )
            # velocity/volume moving but the see-saw isn't confirming it -> treat as slow/uncertain
            zone = Zone.BULLISH if direction_is_call else Zone.BEARISH
            return Verdict(
                zone=Zone.SLOW_MOVING,
                confidence=0.45,
                reasoning=(
                    "Velocity and volume are picking up, but the call/put see-saw correlation "
                    "isn't confirming the expected mirrored reaction — treating this as cautious, "
                    "not a full-conviction signal."
                ),
                evidence=evidence,
            )

        # Mixed signals: some velocity or some volume, but not both together.
        return Verdict(
            zone=Zone.SLOW_MOVING,
            confidence=0.4,
            reasoning="Velocity and volume are only partially confirming each other — cautious read.",
            evidence=evidence,
        )
