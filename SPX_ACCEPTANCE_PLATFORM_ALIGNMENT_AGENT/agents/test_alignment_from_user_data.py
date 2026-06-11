from datetime import datetime
from agents.alignment_agent import AlignmentAgent, SignalEvent


def t(hm: str):
    return datetime.strptime("2026-06-10 " + hm, "%Y-%m-%d %H:%M")


signals = [
    ("09:06", "SPY", "SELL", "SPY"),
    ("09:15", "SPY", "BUY", "SPY"),
    ("09:24", "SPY", "SELL", "SPY"),
    ("09:57", "SPY", "BUY", "SPY"),
    ("10:03", "SPY", "SELL", "SPY"),
    ("11:42", "SPY", "BUY", "SPY"),
    ("14:45", "SPY", "BUY", "SPY"),
    ("15:00", "SPY", "SELL", "SPY"),

    ("08:52", "CALL", "BUY", "SPXW260610C7265"),
    ("09:18", "CALL", "SELL", "SPXW260610C7265"),
    ("10:45", "CALL", "BUY", "SPXW260610C7265"),
    ("10:48", "CALL", "SELL", "SPXW260610C7265"),
    ("11:33", "CALL", "BUY", "SPXW260610C7265"),
    ("11:36", "CALL", "SELL", "SPXW260610C7265"),
    ("12:54", "CALL", "BUY", "SPXW260610C7265"),
    ("13:06", "CALL", "SELL", "SPXW260610C7265"),
    ("14:36", "CALL", "BUY", "SPXW260610C7265"),
    ("14:48", "CALL", "SELL", "SPXW260610C7265"),

    ("09:42", "PUT", "BUY", "SPXW260610P7270"),
    ("10:15", "PUT", "BUY", "SPXW260610P7270"),
    ("10:21", "PUT", "SELL", "SPXW260610P7270"),
    ("10:48", "PUT", "SELL", "SPXW260610P7270"),
    ("11:48", "PUT", "BUY", "SPXW260610P7270"),
    ("12:00", "PUT", "SELL", "SPXW260610P7270"),
    ("12:12", "PUT", "BUY", "SPXW260610P7270"),
    ("12:48", "PUT", "SELL", "SPXW260610P7270"),
    ("13:42", "PUT", "BUY", "SPXW260610P7270"),
    ("14:24", "PUT", "SELL", "SPXW260610P7270"),
    ("14:48", "PUT", "BUY", "SPXW260610P7270"),
]

agent = AlignmentAgent(window_minutes=15)

for hm, inst, sig, symbol in sorted(signals, key=lambda x: x[0]):
    result = agent.add_signal(SignalEvent(t(hm), inst, sig, symbol))
    if result.aligned or result.score >= 70:
        print(
            hm,
            inst,
            sig,
            "|",
            result.direction,
            result.grade,
            result.score,
            "|",
            result.explanation,
        )
