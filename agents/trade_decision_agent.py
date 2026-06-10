"""Trade decision agent.

This agent combines signals from several other agents to produce a
final trading decision.  It takes into account:

* The outcome of the acceptance/rejection analysis (`AcceptanceResult`)
* The peak hold time scores (`PeakHoldTimeResult`)
* Whether price returned to the zone and how long it took (`ReturnToZoneResult`)

The final decision is either `PLAY_CALL`, `PLAY_PUT` or `WAIT`.  The
confidence score is calculated by weighting the different inputs and
compared against a threshold defined in the configuration.  When the
confidence is below the threshold, the decision defaults to `WAIT`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from ..config import get_settings
from .acceptance_rejection_agent import AcceptanceResult
from .peak_hold_time_agent import PeakHoldTimeResult
from .return_to_zone_agent import ReturnToZoneResult


logger = logging.getLogger(__name__)

TradeDecision = Literal["PLAY_CALL", "PLAY_PUT", "WAIT"]


@dataclass
class TradeDecisionResult:
    decision: TradeDecision
    confidence: int
    reason: str


class TradeDecisionAgent:
    """Combine multiple signals to produce a trade decision."""

    def __init__(self, confidence_threshold: int | None = None) -> None:
        settings = get_settings()
        self.confidence_threshold = confidence_threshold if confidence_threshold is not None else settings.confidence_threshold

    def decide(
        self,
        acceptance: AcceptanceResult,
        peak: PeakHoldTimeResult,
        rtn: ReturnToZoneResult,
    ) -> TradeDecisionResult:
        """Generate a trade decision based on combined signals.

        Parameters
        ----------
        acceptance : AcceptanceResult
            Outcome from the acceptance/rejection analysis.
        peak : PeakHoldTimeResult
            Scores from the peak hold time analysis.
        rtn : ReturnToZoneResult
            Information about whether price returned to the zone.

        Returns
        -------
        TradeDecisionResult
            Final decision, confidence percentage and rationale.
        """
        # If acceptance outcome is waiting, pass through
        if acceptance.decision == "WAITING_FOR_CONFIRMATION" or acceptance.bias == "WAIT":
            return TradeDecisionResult(
                decision="WAIT",
                confidence=50,
                reason="Acceptance analysis not yet confirmed; waiting for more data.",
            )
        # Base score from acceptance
        score = float(acceptance.confidence)
        reason_parts = [f"Base confidence from acceptance analysis: {score}%"]
        # Influence of peak hold time
        peak_weight = 0.3
        score += peak.acceptance_score * peak_weight
        score -= peak.rejection_score * peak_weight
        reason_parts.append(
            f"Adjusted for peak hold time (acceptance {peak.acceptance_score}%, rejection {peak.rejection_score}%): now {score:.1f}%"
        )
        # Influence of return to zone behaviour
        if rtn.status == "RETURNED":
            # Quick return implies acceptance; slower return implies caution
            if rtn.time_to_return_minutes is not None:
                if rtn.time_to_return_minutes <= 1.0:
                    score += 5
                    reason_parts.append("Price returned to zone very quickly; increasing confidence.")
                else:
                    score -= 5
                    reason_parts.append(
                        f"Price returned after {rtn.time_to_return_minutes:.2f} minutes; decreasing confidence slightly."
                    )
            else:
                # Should not happen but handle gracefully
                score += 0
        else:  # NOT_RETURNED
            # Not returning after rejection could imply strong rejection when the decision is opposite
            if acceptance.decision in ["RESISTANCE_REJECTED_PLAY_PUT", "SUPPORT_REJECTED_PLAY_CALL"]:
                score += 5
                reason_parts.append("Price did not return after rejection; reinforcing the rejection decision.")
            else:
                score -= 5
                reason_parts.append("Price did not return but acceptance decision was signalled; reducing confidence.")
        # Normalise score to [0, 100]
        if score > 100:
            score = 100.0
        if score < 0:
            score = 0.0
        # Determine final trade decision
        bias = acceptance.bias
        if score < self.confidence_threshold:
            final_decision: TradeDecision = "WAIT"
            reason_parts.append(
                f"Final confidence {score:.1f}% below threshold {self.confidence_threshold}%; decision is WAIT."
            )
        else:
            final_decision = "PLAY_CALL" if bias == "CALL" else "PLAY_PUT"
            reason_parts.append(
                f"Final confidence {score:.1f}% above threshold {self.confidence_threshold}%; decision is {final_decision}."
            )
        return TradeDecisionResult(
            decision=final_decision,
            confidence=int(score),
            reason="\n".join(reason_parts),
        )
