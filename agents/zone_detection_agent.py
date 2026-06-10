"""Zone detection agent.

This agent analyses recent price history to detect support and
resistance zones.  It clusters local highs and lows within a
configurable tolerance to form zones and computes simple metrics such
as strength and width.  Zones are returned as dataclasses and can be
stored in the database for further analysis.

The detection logic is deliberately simple: it uses successive local
extrema and groups them if they fall within ``tolerance_points`` of
each other.  ``min_touches`` controls the minimum number of touches
required for a valid zone.  More sophisticated algorithms can be
implemented in the future.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal

import pandas as pd

from ..config import get_settings


ZoneType = Literal["resistance", "support"]


@dataclass
class Zone:
    """Represents a support or resistance zone."""

    zone_type: ZoneType
    low: float
    high: float
    center: float
    strength: int
    touches: int

    @property
    def width(self) -> float:
        """Return the width of the zone."""
        return self.high - self.low


class ZoneDetectionAgent:
    """Finds support and resistance zones from historical price data.

    The agent looks for local highs and lows and clusters them based on
    a tolerance parameter to generate candidate zones.  Only clusters
    with at least ``min_touches`` touches are returned.
    """

    def __init__(self, tolerance_points: float | None = None, min_touches: int | None = None) -> None:
        settings = get_settings()
        self.tolerance_points = tolerance_points if tolerance_points is not None else settings.zone_tolerance_points
        self.min_touches = min_touches if min_touches is not None else settings.zone_min_touches

    def detect_zones(self, df: pd.DataFrame) -> List[Zone]:
        """Detect zones in the provided price dataframe.

        Parameters
        ----------
        df : pandas.DataFrame
            DataFrame containing at least a ``price`` column.  The
            timestamps are ignored in this simple implementation.

        Returns
        -------
        list of Zone
            Detected support and resistance zones sorted by strength
            descending.
        """
        if df.empty or "price" not in df.columns:
            return []

        prices = df["price"].astype(float).tolist()
        highs = self._local_highs(prices)
        lows = self._local_lows(prices)
        resistance_zones = self._cluster_levels(highs, "resistance")
        support_zones = self._cluster_levels(lows, "support")
        return sorted(resistance_zones + support_zones, key=lambda z: z.strength, reverse=True)

    def _local_highs(self, prices: List[float]) -> List[float]:
        levels: List[float] = []
        for i in range(1, len(prices) - 1):
            if prices[i] >= prices[i - 1] and prices[i] >= prices[i + 1]:
                levels.append(prices[i])
        return levels

    def _local_lows(self, prices: List[float]) -> List[float]:
        levels: List[float] = []
        for i in range(1, len(prices) - 1):
            if prices[i] <= prices[i - 1] and prices[i] <= prices[i + 1]:
                levels.append(prices[i])
        return levels

    def _cluster_levels(self, levels: List[float], zone_type: ZoneType) -> List[Zone]:
        """Cluster similar levels into zones."""
        zones: List[Zone] = []
        used: set[int] = set()
        for i, level in enumerate(levels):
            if i in used:
                continue
            cluster = [level]
            used.add(i)
            for j, other in enumerate(levels):
                if j in used:
                    continue
                if abs(other - level) <= self.tolerance_points:
                    cluster.append(other)
                    used.add(j)
            if len(cluster) >= self.min_touches:
                low = min(cluster) - self.tolerance_points
                high = max(cluster) + self.tolerance_points
                center = sum(cluster) / len(cluster)
                zones.append(
                    Zone(
                        zone_type=zone_type,
                        low=round(low, 2),
                        high=round(high, 2),
                        center=round(center, 2),
                        strength=len(cluster),
                        touches=len(cluster),
                    )
                )
        return zones
