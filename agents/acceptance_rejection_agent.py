"""Acceptance and rejection analysis agent.

This agent applies the core rule of the SPX Acceptance Platform: after
price enters a support or resistance zone, does it reject/bounce and
return quickly or not?  Based on these outcomes it labels the zone as
accepted or rejected and produces a decision bias (`CALL`, `PUT` or
`WAIT`) along with a confidence score and human‑readable reason.  The
class is configurable via the application settings for the minimum
points required to count as a rejection/bounce and the time window
allowed for price to return to the zone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal, Optional

import pandas as pd

from config import get_settings
from agents.zone_detection_agent import Zone


Bias = Literal["CALL", "PUT", "WAIT"]
Decision = Literal[
    "RESISTANCE_ACCEPTED_PLAY_CALL",
    "RESISTANCE_REJECTED_PLAY_PUT",
    "SUPPORT_ACCEPTED_PLAY_PUT",
    "SUPPORT_REJECTED_PLAY_CALL",
    "WAITING_FOR_CONFIRMATION",
]


@dataclass
class AcceptanceResult:
    zone_type: str
    zone_low: float
    zone_high: float
    entered_time: str
    rejection_time: Optional[str]
    returned_time: Optional[str]
    decision: Decision
    bias: Bias
    confidence: int
    reason: str


class AcceptanceRejectionAgent:
    """Determine whether a zone is accepted or rejected.

    When price enters a resistance zone:

    - If it falls by ``rejection_points`` below the zone low and does
      not return into the zone within ``return_window_minutes``, the
      resistance is considered rejected and the bias is to play PUT.
    - If it falls by the required amount but returns into the zone
      quickly, the resistance is considered accepted and the bias is to
      play CALL.

    When price enters a support zone:

    - If it rises by ``rejection_points`` above the zone high and does
      not return into the zone within ``return_window_minutes``, the
      support is considered rejected and the bias is to play CALL.
    - If it rises and returns quickly, the support is considered
      accepted and the bias is to play PUT.

    If price has not moved sufficiently away from the zone yet, the
    decision remains in a waiting state.
    """

    def __init__(self, rejection_points: float | None = None, return_window_minutes: int | None = None) -> None:
        settings = get_settings()
        self.rejection_points = rejection_points if rejection_points is not None else settings.rejection_points
        self.return_window_minutes = return_window_minutes if return_window_minutes is not None else settings.return_window_minutes

    def analyze_zone_touch(self, df: pd.DataFrame, zone: Zone) -> Optional[AcceptanceResult]:
        """Analyse price behaviour after entering a zone.

        Parameters
        ----------
        df : pandas.DataFrame
            DataFrame containing at least ``timestamp`` and ``price``.
        zone : Zone
            A zone returned by :class:`ZoneDetectionAgent`.

        Returns
        -------
        AcceptanceResult or None
            Summary of the analysis or ``None`` if the zone was never
            touched in the provided data.
        """
        if df.empty:
            return None
        data = df.copy()
        data["timestamp"] = pd.to_datetime(data["timestamp"])
        data["price"] = data["price"].astype(float)
        # Find rows where price enters the zone
        touch_rows = data[(data["price"] >= zone.low) & (data["price"] <= zone.high)]
        if touch_rows.empty:
            return None
        first_touch = touch_rows.iloc[0]
        entered_time = first_touch["timestamp"]
        # Filter data after entry time
        after_touch = data[data["timestamp"] >= entered_time].copy()
        if zone.zone_type == "resistance":
            return self._analyze_resistance(after_touch, zone, entered_time)
        if zone.zone_type == "support":
            return self._analyze_support(after_touch, zone, entered_time)
        return None

    def _analyze_resistance(self, df: pd.DataFrame, zone: Zone, entered_time) -> AcceptanceResult:
        # Rejection occurs if price drops below zone.low minus rejection_points
        reject_price = zone.low - self.rejection_points
        rejected = df[df["price"] <= reject_price]
        if rejected.empty:
            return AcceptanceResult(
                zone_type="resistance",
                zone_low=zone.low,
                zone_high=zone.high,
                entered_time=str(entered_time),
                rejection_time=None,
                returned_time=None,
                decision="WAITING_FOR_CONFIRMATION",
                bias="WAIT",
                confidence=50,
                reason="Price entered resistance but has not dropped enough to confirm rejection.",
            )
        rejection_time = rejected.iloc[0]["timestamp"]
        # Determine window within which price must return to zone
        window_end = rejection_time + timedelta(minutes=self.return_window_minutes)
        after_rejection = df[(df["timestamp"] > rejection_time) & (df["timestamp"] <= window_end)]
        returned = after_rejection[(after_rejection["price"] >= zone.low) & (after_rejection["price"] <= zone.high)]
        if not returned.empty:
            returned_time = returned.iloc[0]["timestamp"]
            return AcceptanceResult(
                zone_type="resistance",
                zone_low=zone.low,
                zone_high=zone.high,
                entered_time=str(entered_time),
                rejection_time=str(rejection_time),
                returned_time=str(returned_time),
                decision="RESISTANCE_ACCEPTED_PLAY_CALL",
                bias="CALL",
                confidence=85,
                reason="Price rejected from resistance but returned quickly, indicating the zone is accepted.",
            )
        # Did not return
        return AcceptanceResult(
            zone_type="resistance",
            zone_low=zone.low,
            zone_high=zone.high,
            entered_time=str(entered_time),
            rejection_time=str(rejection_time),
            returned_time=None,
            decision="RESISTANCE_REJECTED_PLAY_PUT",
            bias="PUT",
            confidence=88,
            reason="Price rejected from resistance and failed to return within the window, indicating the zone is rejected.",
        )

    def _analyze_support(self, df: pd.DataFrame, zone: Zone, entered_time) -> AcceptanceResult:
        # Bounce occurs if price rises above zone.high plus rejection_points
        reject_price = zone.high + self.rejection_points
        rejected = df[df["price"] >= reject_price]
        if rejected.empty:
            return AcceptanceResult(
                zone_type="support",
                zone_low=zone.low,
                zone_high=zone.high,
                entered_time=str(entered_time),
                rejection_time=None,
                returned_time=None,
                decision="WAITING_FOR_CONFIRMATION",
                bias="WAIT",
                confidence=50,
                reason="Price entered support but has not risen enough to confirm a bounce.",
            )
        rejection_time = rejected.iloc[0]["timestamp"]
        window_end = rejection_time + timedelta(minutes=self.return_window_minutes)
        after_rejection = df[(df["timestamp"] > rejection_time) & (df["timestamp"] <= window_end)]
        returned = after_rejection[(after_rejection["price"] >= zone.low) & (after_rejection["price"] <= zone.high)]
        if not returned.empty:
            returned_time = returned.iloc[0]["timestamp"]
            return AcceptanceResult(
                zone_type="support",
                zone_low=zone.low,
                zone_high=zone.high,
                entered_time=str(entered_time),
                rejection_time=str(rejection_time),
                returned_time=str(returned_time),
                decision="SUPPORT_ACCEPTED_PLAY_PUT",
                bias="PUT",
                confidence=85,
                reason="Price bounced from support and returned quickly, indicating the zone is accepted.",
            )
        return AcceptanceResult(
            zone_type="support",
            zone_low=zone.low,
            zone_high=zone.high,
            entered_time=str(entered_time),
            rejection_time=str(rejection_time),
            returned_time=None,
            decision="SUPPORT_REJECTED_PLAY_CALL",
            bias="CALL",
            confidence=88,
            reason="Price bounced from support but failed to return within the window, indicating the zone is rejected.",
        )
