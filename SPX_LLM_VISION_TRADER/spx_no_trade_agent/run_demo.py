"""
Demo / smoke test: runs the full reasoning pipeline against the real SPXW
7515C / 7520P CSV data used earlier in this conversation, using
DerivedChartConnector (built from the same OHLCV data) as a stand-in for
the live LLM chart read.

Run: python run_demo.py
"""

from collections import Counter

from spx_agent import (
    Boss,
    ChartReasoningAgent,
    CsvSheetConnector,
    DataReasoningAgent,
    DerivedChartConnector,
    FinalCall,
    SelfLearningLog,
    Side,
    SpxNoTradeAgent,
)

CALL_CSV = "/mnt/user-data/uploads/OPRA_SPXW260714C7515_0__3.csv"
PUT_CSV = "/mnt/user-data/uploads/OPRA_SPXW260714P7520_0__3.csv"


def run_side(side: Side, log_path: str):
    sheet_connector = CsvSheetConnector(CALL_CSV, PUT_CSV)
    chart_connector = DerivedChartConnector(CALL_CSV, PUT_CSV)

    agent = SpxNoTradeAgent(
        side=side,
        sheet_connector=sheet_connector,
        chart_connector=chart_connector,
        chart_agent=ChartReasoningAgent(),
        data_agent=DataReasoningAgent(),
        boss=Boss(min_confidence_for_trade=0.65),
        learning_log=SelfLearningLog(path=log_path),
        chart_refresh_every_n_ticks=20,
        tick_window=15,
    )

    print(f"\n{'=' * 70}\n{side.value.upper()} SIDE — live reasoning walk-through\n{'=' * 70}")
    decisions = agent.run_over_history(verbose=True)

    calls = Counter(d.final_call for d in decisions)
    aligned = sum(1 for d in decisions if d.aligned)

    print(f"\n--- {side.value.upper()} summary ---")
    print(f"Total decisions: {len(decisions)}")
    for call, count in calls.items():
        pct = count / len(decisions) * 100 if decisions else 0
        print(f"  {call.value:>16}: {count:4d}  ({pct:5.1f}%)")
    print(f"  Agents aligned:  {aligned}/{len(decisions)} "
          f"({aligned / len(decisions) * 100:.1f}%)" if decisions else "")

    no_trade_pct = calls.get(FinalCall.NO_TRADE, 0) / len(decisions) * 100 if decisions else 0
    print(f"\nNo-trade rate: {no_trade_pct:.1f}% "
          f"(objective is for this to be the majority outcome most of the time)")

    return decisions


if __name__ == "__main__":
    call_decisions = run_side(Side.CALL, "/home/claude/call_log.jsonl")
    put_decisions = run_side(Side.PUT, "/home/claude/put_log.jsonl")

    print(f"\n{'=' * 70}\nSample commentary lines\n{'=' * 70}")
    from spx_agent import narrate
    for d in call_decisions[:5]:
        print(narrate(d))
