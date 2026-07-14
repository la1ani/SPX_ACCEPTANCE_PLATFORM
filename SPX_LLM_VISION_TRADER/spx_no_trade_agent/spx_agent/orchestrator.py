"""
Orchestrator.

Ties everything together: pulls live ticks from the sheet connector, pulls a
periodic chart read from the chart connector, runs both reasoning agents,
reconciles through the boss, logs the decision for self-learning, and emits
live commentary.

In production this runs continuously during market hours, refreshing the
chart read on a cycle (60s was the figure discussed) while the sheet stream
is checked far more frequently. In the demo below it steps through
historical ticks and re-reads the chart connector every N ticks to
approximate that same cadence.
"""

from __future__ import annotations

from datetime import datetime

from .boss import Boss
from .chart_agent import ChartReasoningAgent
from .commentary import narrate
from .connectors import ChartConnector, SheetConnector
from .data_agent import DataReasoningAgent
from .learning import SelfLearningLog
from .models import Decision, LevelType, Side


class SpxNoTradeAgent:
    def __init__(
        self,
        side: Side,
        sheet_connector: SheetConnector,
        chart_connector: ChartConnector,
        chart_agent: ChartReasoningAgent | None = None,
        data_agent: DataReasoningAgent | None = None,
        boss: Boss | None = None,
        learning_log: SelfLearningLog | None = None,
        chart_refresh_every_n_ticks: int = 20,
        tick_window: int = 30,
    ):
        self.side = side
        self.sheet_connector = sheet_connector
        self.chart_connector = chart_connector
        self.chart_agent = chart_agent or ChartReasoningAgent()
        self.data_agent = data_agent or DataReasoningAgent()
        self.boss = boss or Boss()
        self.learning_log = learning_log or SelfLearningLog()
        self.chart_refresh_every_n_ticks = chart_refresh_every_n_ticks
        self.tick_window = tick_window

    def run_over_history(self, verbose: bool = True) -> list[Decision]:
        all_ticks = self.sheet_connector.get_ticks()
        decisions: list[Decision] = []
        last_chart_extraction = None

        for i in range(len(all_ticks)):
            window = all_ticks[max(0, i - self.tick_window + 1): i + 1]
            if len(window) < 3:
                continue

            current_ts = window[-1].timestamp

            if last_chart_extraction is None or i % self.chart_refresh_every_n_ticks == 0:
                last_chart_extraction = self.chart_connector.read_chart(self.side, current_ts)

            decision = self._decide(window, last_chart_extraction, current_ts)
            decisions.append(decision)
            self.learning_log.record_decision(decision)

            if verbose:
                print(narrate(decision))

        return decisions

    def step(
        self, recent_ticks: list, force_chart_refresh: bool = False
    ) -> Decision:
        current_ts = recent_ticks[-1].timestamp
        extraction = self.chart_connector.read_chart(self.side, current_ts)
        decision = self._decide(recent_ticks, extraction, current_ts)
        self.learning_log.record_decision(decision)
        return decision

    def _decide(self, ticks: list, extraction, current_ts: datetime) -> Decision:
        chart_verdict = self.chart_agent.evaluate(extraction)

        nearby_level = self._closest_level(extraction, ticks[-1])
        data_verdict = self.data_agent.evaluate(
            ticks,
            nearby_level=nearby_level,
            level_side_is_call=(self.side == Side.CALL),
        )

        return self.boss.decide(self.side, chart_verdict, data_verdict, timestamp=current_ts)

    @staticmethod
    def _closest_level(extraction, latest_tick):
        if not extraction.levels:
            return None
        price = latest_tick.call_price if extraction.side == Side.CALL else latest_tick.put_price
        return min(extraction.levels, key=lambda lv: abs(lv.price - price))
