"""Return to zone agent.

After a rejection or bounce from a zone, this agent determines whether
price eventually returns to that zone and how long it takes.  It can
also count how many times price attempts to return.  This information
is useful for refining trade confidence – a quick return suggests
acceptance, whereas failing to return suggests rejection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

from agents.zone_detection_agent import Zone


logger = logging.getLogger(__name__)


@dataclass
class ReturnToZoneResult:
    status: str  # RETURNED or NOT_RETURNED
    time_to_return_minutes: Optional[float]
    attempts: int


class ReturnToZoneAgent:
    """Evaluate whether and when price returns to a zone after rejection."""

    def evaluate(self, df: pd.DataFrame, zone: Zone, rejection_time: datetime) -> ReturnToZoneResult:
        """Check if price returns to the zone after the given time.

        Parameters
        ----------
        df : pandas.DataFrame
            Must contain at least ``timestamp`` and ``price`` columns.
        zone : Zone
            The support/resistance zone being evaluated.
        rejection_time : datetime
            The time when price first rejected or bounced off the zone.

        Returns
        -------
        ReturnToZoneResult
            Indicates whether price returned, how long it took (in minutes)
            and how many distinct attempts occurred.
        """
        data = df.copy()
        data["timestamp"] = pd.to_datetime(data["timestamp"])
        data["price"] = data["price"].astype(float)
        after_rejection = data[data["timestamp"] > rejection_time].copy()
        if after_rejection.empty:
            return ReturnToZoneResult(status="NOT_RETURNED", time_to_return_minutes=None, attempts=0)
        attempts = 0
        returned_time: Optional[datetime] = None
        in_zone_prev = False
        for _, row in after_rejection.iterrows():
            price = row["price"]
            in_zone = zone.low <= price <= zone.high
            if in_zone:
                if not in_zone_prev:
                    # New attempt
                    attempts += 1
                if returned_time is None:
                    returned_time = row["timestamp"]
            in_zone_prev = in_zone
        if returned_time is not None:
            elapsed = (returned_time - rejection_time).total_seconds() / 60.0
            return ReturnToZoneResult(status="RETURNED", time_to_return_minutes=round(elapsed, 2), attempts=attempts)
        return ReturnToZoneResult(status="NOT_RETURNED", time_to_return_minutes=None, attempts=attempts)
