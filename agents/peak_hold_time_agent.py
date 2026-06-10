"""Peak hold time agent.

This agent assesses how long price stays near its extreme after a trade
signal.  A long hold time near the extreme is interpreted as
acceptance (strength on the direction of the signal) whereas a very
short stay indicates strong rejection.  The hold time is converted to
an acceptance score between 0 and 100, with the rejection score being
the complement (100 minus acceptance score).

``decision`` must be either ``CALL`` or ``PUT``; the agent will look
for the maximum or minimum price after the decision time respectively.
Prices are considered "near" the extreme when the fractional distance
from the extreme is less than ``peak_hold_threshold`` from the
configuration.  The scoring assumes that staying near the extreme for
``peak_hold_base_minutes`` minutes yields a perfect score of 100.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, Tuple

import pandas as pd

from ..config import get_settings


logger = logging.getLogger(__name__)

DecisionBias = Literal["CALL", "PUT"]


@dataclass
class PeakHoldTimeResult:
    hold_time_minutes: float
    acceptance_score: int
    rejection_score: int


class PeakHoldTimeAgent:
    """Analyse how long price stays near the extreme following a decision."""

    def __init__(self, peak_hold_threshold: float | None = None, peak_hold_base_minutes: float = 5.0) -> None:
        settings = get_settings()
        self.peak_hold_threshold = (
            peak_hold_threshold if peak_hold_threshold is not None else settings.peak_hold_threshold
        )
        # The number of minutes considered to achieve a 100% acceptance score
        self.peak_hold_base_minutes = peak_hold_base_minutes

    def analyse(self, df: pd.DataFrame, decision: DecisionBias, decision_time: datetime) -> PeakHoldTimeResult:
        """Compute the peak hold time and scores.

        Parameters
        ----------
        df : pandas.DataFrame
            DataFrame containing at least ``timestamp`` and ``price``.
        decision : str
            ``CALL`` or ``PUT`` indicating the direction of the trade.
        decision_time : datetime
            Timestamp when the trade decision was made; only data after
            this time is considered.

        Returns
        -------
        PeakHoldTimeResult
            Contains the total hold time in minutes and acceptance/rejection
            scores.
        """
        data = df.copy()
        data["timestamp"] = pd.to_datetime(data["timestamp"])
        data["price"] = data["price"].astype(float)
        # Filter data after decision time
        after_decision = data[data["timestamp"] >= decision_time].copy()
        if after_decision.empty:
            return PeakHoldTimeResult(hold_time_minutes=0.0, acceptance_score=0, rejection_score=100)
        prices = after_decision["price"]
        if decision == "CALL":
            extreme = prices.max()
            # Near extreme when price within threshold fraction below the max
            threshold = extreme * (1 - self.peak_hold_threshold)
            mask = prices >= threshold
        elif decision == "PUT":
            extreme = prices.min()
            threshold = extreme * (1 + self.peak_hold_threshold)
            mask = prices <= threshold
        else:
            raise ValueError(f"Invalid decision bias: {decision}")
        # Compute time differences where price stays near extreme
        hold_time_seconds = 0.0
        timestamps = after_decision["timestamp"].tolist()
        flags = mask.tolist()
        last_on_time: Optional[datetime] = None
        for i, flag in enumerate(flags):
            if flag:
                if last_on_time is None:
                    last_on_time = timestamps[i]
            else:
                if last_on_time is not None:
                    # Off period, accumulate hold time
                    hold_time_seconds += (timestamps[i] - last_on_time).total_seconds()
                    last_on_time = None
        # If still in hold at end, accumulate till end
        if last_on_time is not None:
            hold_time_seconds += (timestamps[-1] - last_on_time).total_seconds()
        hold_time_minutes = hold_time_seconds / 60.0
        # Compute acceptance score scaled to base minutes
        acceptance_score = int(
            max(0.0, min(1.0, hold_time_minutes / self.peak_hold_base_minutes)) * 100
        )
        rejection_score = 100 - acceptance_score
        return PeakHoldTimeResult(
            hold_time_minutes=round(hold_time_minutes, 2),
            acceptance_score=acceptance_score,
            rejection_score=rejection_score,
        )
