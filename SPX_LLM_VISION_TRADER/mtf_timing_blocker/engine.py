from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable
import json
import math
import re
import statistics


TRACKED_INTERVALS = ("15s", "30s", "1m", "3m", "5m")
PRIMARY_ENTRY_INTERVAL = "1m"
SETUP_INTERVAL = "5m"


@dataclass
class SignalRow:
    server_time: str = ""
    ticker: str = ""
    exchange: str = ""
    interval: str = ""
    candle_time: str = ""
    open: float | None = None
    close: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None
    signal: str = ""
    comment: str = ""
    side: str = ""
    source: str = "AUTO"
    row_key: str = ""
    parsed_time: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Transition:
    side: str
    interval: str
    old_signal: str
    new_signal: str
    old_close: float | None
    new_close: float | None
    old_volume: float | None
    new_volume: float | None
    seconds_between: float
    velocity_per_min: float
    price_delta: float
    volume_ratio: float
    flip_speed: str
    transition_type: str
    is_fast: bool
    is_high_velocity: bool
    is_volume_expanding: bool
    is_rejection: bool
    is_recovery: bool
    price_level_status: str
    reason: str


@dataclass
class Decision:
    timestamp: str
    source: str
    call_symbol: str
    put_symbol: str
    candidate_side: str
    blocking_status: str
    trade_status: str
    grade: str
    action: str
    reason: str
    call_15s: str = ""
    call_30s: str = ""
    call_1m: str = ""
    call_3m: str = ""
    call_5m: str = ""
    put_15s: str = ""
    put_30s: str = ""
    put_1m: str = ""
    put_3m: str = ""
    put_5m: str = ""
    fast_flip: str = ""
    rejection_status: str = ""
    recovery_status: str = ""
    velocity_status: str = ""
    volume_status: str = ""
    body_stack_status: str = ""
    opposite_bleeding: str = ""
    price_level_status: str = ""
    event_type: str = "BLOCKER_CHECK"

    def row(self) -> list[Any]:
        return [
            self.timestamp,
            self.source,
            self.call_symbol,
            self.put_symbol,
            self.candidate_side,
            self.call_15s,
            self.call_30s,
            self.call_1m,
            self.call_3m,
            self.call_5m,
            self.put_15s,
            self.put_30s,
            self.put_1m,
            self.put_3m,
            self.put_5m,
            self.fast_flip,
            self.rejection_status,
            self.recovery_status,
            self.velocity_status,
            self.volume_status,
            self.body_stack_status,
            self.opposite_bleeding,
            self.price_level_status,
            self.blocking_status,
            self.trade_status,
            self.grade,
            self.action,
            self.reason,
            self.event_type,
        ]


@dataclass
class Event:
    timestamp: str
    source: str
    event_type: str
    symbol: str
    side: str
    interval: str
    old_signal: str
    new_signal: str
    candidate_side: str
    blocking_status: str
    trade_status: str
    grade: str
    action: str
    reason: str
    flip_speed: str = ""
    seconds_between: float | str = ""
    price_delta: float | str = ""
    velocity_per_min: float | str = ""
    volume_ratio: float | str = ""
    price_level_status: str = ""
    opposite_side_status: str = ""

    def row(self) -> list[Any]:
        return [
            self.timestamp,
            self.source,
            self.event_type,
            self.symbol,
            self.side,
            self.interval,
            self.old_signal,
            self.new_signal,
            self.candidate_side,
            self.blocking_status,
            self.trade_status,
            self.grade,
            self.action,
            self.reason,
            self.flip_speed,
            self.seconds_between,
            self.price_delta,
            self.velocity_per_min,
            self.volume_ratio,
            self.price_level_status,
            self.opposite_side_status,
        ]


@dataclass
class EngineState:
    latest: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    seen_row_keys: list[str] = field(default_factory=list)
    last_decision_status: str = ""
    last_trade_status: str = ""
    last_event_signature: str = ""
    last_rejections: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_recoveries: dict[str, dict[str, Any]] = field(default_factory=dict)
    updated_at: str = ""

    @classmethod
    def from_json(cls, text: str | None) -> "EngineState":
        if not text:
            return cls()
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                return cls()
            return cls(
                latest=data.get("latest") or {},
                seen_row_keys=list(data.get("seen_row_keys") or [])[-2000:],
                last_decision_status=data.get("last_decision_status", ""),
                last_trade_status=data.get("last_trade_status", ""),
                last_event_signature=data.get("last_event_signature", ""),
                last_rejections=data.get("last_rejections") or {},
                last_recoveries=data.get("last_recoveries") or {},
                updated_at=data.get("updated_at", ""),
            )
        except Exception:
            return cls()

    def to_json(self) -> str:
        self.seen_row_keys = self.seen_row_keys[-2000:]
        return json.dumps(asdict(self), ensure_ascii=False, default=str)


@dataclass
class EngineConfig:
    fresh_rejection_seconds: int = 120
    fast_flip_seconds: int = 90
    high_velocity_multiplier: float = 1.45
    min_velocity_per_min: float = 0.10
    volume_expansion_multiplier: float = 1.25
    max_chop_flips: int = 3
    chop_lookback_rows: int = 6


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isnan(value):
            return None
        return float(value)
    text = str(value).replace(",", "").strip()
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_time(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip()
    clean = text.replace("Z", "+00:00")
    formats = (
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(clean)
        if parsed.tzinfo is None:
            return parsed.timestamp()
        return parsed.astimezone(timezone.utc).timestamp()
    except ValueError:
        return 0.0


def _interval_rank(interval: str) -> int:
    order = {"15s": 0, "30s": 1, "1m": 2, "3m": 3, "5m": 4}
    return order.get(interval, 99)


def _normalize_interval(value: Any) -> str:
    text = _clean_text(value).lower().replace(" ", "")
    aliases = {
        "15sec": "15s",
        "15second": "15s",
        "15seconds": "15s",
        "30sec": "30s",
        "30second": "30s",
        "30seconds": "30s",
        "1min": "1m",
        "1minute": "1m",
        "3min": "3m",
        "3minute": "3m",
        "5min": "5m",
        "5minute": "5m",
    }
    return aliases.get(text, text)


def _detect_side(ticker: str, comment: str, explicit_side: str = "") -> str:
    explicit = _clean_text(explicit_side).upper()
    if explicit in {"CALL", "PUT"}:
        return explicit
    text = f"{ticker} {comment}".upper()
    if "CALL" in text:
        return "CALL"
    if "PUT" in text:
        return "PUT"
    # SPXW option tickers usually contain C or P before strike/decimal.
    match = re.search(r"[A-Z]+[0-9]{6}([CP])", text)
    if match:
        return "CALL" if match.group(1) == "C" else "PUT"
    if re.search(r"C[0-9]+(?:\.[0-9]+)?$", text):
        return "CALL"
    if re.search(r"P[0-9]+(?:\.[0-9]+)?$", text):
        return "PUT"
    return ""


def normalize_record(row: dict[str, Any], source: str = "AUTO") -> SignalRow | None:
    # Accept both exact sheet headers and snake_case variants.
    def pick(*names: str) -> Any:
        lower = {str(k).strip().lower().replace("_", " "): v for k, v in row.items()}
        for name in names:
            key = name.strip().lower().replace("_", " ")
            if key in lower:
                return lower[key]
        return ""

    server_time = _clean_text(pick("Server Time", "Date Time", "timestamp", "time"))
    ticker = _clean_text(pick("Ticker", "Symbol"))
    interval = _normalize_interval(pick("Interval", "Timeframe", "TF"))
    candle_time = _clean_text(pick("Candle Time", "Candle_Time"))
    signal = _clean_text(pick("Signal")).upper()
    comment = _clean_text(pick("Comment", "Notes"))
    side = _detect_side(ticker, comment, pick("Side"))
    if signal not in {"BUY", "SELL"}:
        return None
    if not side:
        return None
    if not interval:
        return None
    parsed_time = _parse_time(server_time) or _parse_time(candle_time)
    row_key = "|".join(
        [
            source,
            server_time,
            ticker,
            interval,
            candle_time,
            signal,
            comment,
        ]
    )
    return SignalRow(
        server_time=server_time,
        ticker=ticker,
        exchange=_clean_text(pick("Exchange")),
        interval=interval,
        candle_time=candle_time,
        open=_number(pick("Open")),
        close=_number(pick("Close")),
        high=_number(pick("High")),
        low=_number(pick("Low")),
        volume=_number(pick("Volume")),
        signal=signal,
        comment=comment,
        side=side,
        source=source,
        row_key=row_key,
        parsed_time=parsed_time,
    )


def _row_from_state(data: dict[str, Any] | None) -> SignalRow | None:
    if not isinstance(data, dict):
        return None
    try:
        return SignalRow(**{field_name: data.get(field_name) for field_name in SignalRow.__dataclass_fields__})
    except Exception:
        return None


def _latest_signal(latest: dict[str, dict[str, SignalRow]], side: str, interval: str) -> SignalRow | None:
    return latest.get(side, {}).get(interval)


def _signal_value(latest: dict[str, dict[str, SignalRow]], side: str, interval: str) -> str:
    row = _latest_signal(latest, side, interval)
    return row.signal if row else ""


def _close_value(row: SignalRow | None) -> float | None:
    return row.close if row and row.close is not None else None


def _symbol_value(latest: dict[str, dict[str, SignalRow]], side: str) -> str:
    for interval in ("1m", "30s", "15s", "3m", "5m"):
        row = _latest_signal(latest, side, interval)
        if row and row.ticker:
            return row.ticker
    return ""


def _recent_for(rows: Iterable[SignalRow], side: str, interval: str, n: int = 6) -> list[SignalRow]:
    filtered = [r for r in rows if r.side == side and r.interval == interval]
    filtered.sort(key=lambda r: (r.parsed_time, r.server_time, r.candle_time))
    return filtered[-n:]


def _body_stack_up(rows: list[SignalRow], min_count: int = 2) -> bool:
    recent = [r for r in rows[-3:] if r.open is not None and r.close is not None]
    if len(recent) < min_count:
        return False
    up_count = sum(1 for r in recent if r.close is not None and r.open is not None and r.close >= r.open)
    close_up = True
    if len(recent) >= 2:
        close_up = all((recent[i].close or 0) >= (recent[i - 1].close or 0) for i in range(1, len(recent)))
    return up_count >= min_count and close_up


def _body_stack_down(rows: list[SignalRow], min_count: int = 2) -> bool:
    recent = [r for r in rows[-3:] if r.open is not None and r.close is not None]
    if len(recent) < min_count:
        return False
    down_count = sum(1 for r in recent if r.close is not None and r.open is not None and r.close <= r.open)
    close_down = True
    if len(recent) >= 2:
        close_down = all((recent[i].close or 0) <= (recent[i - 1].close or 0) for i in range(1, len(recent)))
    return down_count >= min_count and close_down


def _avg_abs_velocity(rows: list[SignalRow]) -> float:
    vals: list[float] = []
    ordered = [r for r in rows if r.close is not None and r.parsed_time]
    ordered.sort(key=lambda r: r.parsed_time)
    for old, new in zip(ordered, ordered[1:]):
        seconds = max(new.parsed_time - old.parsed_time, 1)
        vals.append(abs((new.close or 0) - (old.close or 0)) / seconds * 60)
    if not vals:
        return 0.0
    return statistics.mean(vals)


def _volume_ratio(new_volume: float | None, old_volume: float | None, recent: list[SignalRow]) -> float:
    if new_volume is None:
        return 0.0
    base_values = [r.volume for r in recent if r.volume not in (None, 0)]
    if old_volume not in (None, 0):
        base_values.append(old_volume)
    if not base_values:
        return 0.0
    base = max(statistics.mean(base_values), 1.0)
    return float(new_volume) / base


def _price_level_status(row: SignalRow, recent: list[SignalRow], transition_type: str) -> str:
    valid = [r for r in recent if r.high is not None and r.low is not None and r.close is not None]
    if not valid or row.close is None:
        return "LEVEL_UNKNOWN"
    highs = [r.high for r in valid if r.high is not None]
    lows = [r.low for r in valid if r.low is not None]
    recent_high = max(highs) if highs else None
    recent_low = min(lows) if lows else None
    if recent_high is None or recent_low is None:
        return "LEVEL_UNKNOWN"
    rng = max(recent_high - recent_low, 0.01)

    near_high = row.high is not None and (recent_high - row.high) <= 0.20 * rng
    near_low = row.low is not None and (row.low - recent_low) <= 0.20 * rng
    broke_support = row.close <= recent_low or (row.low is not None and row.low <= recent_low)
    reclaimed = row.close >= recent_high or (row.high is not None and row.high >= recent_high)

    if transition_type == "BUY_TO_SELL":
        if near_high and broke_support:
            return "REJECTED_HIGH_AND_BROKE_SUPPORT"
        if near_high:
            return "REJECTED_HIGH"
        if broke_support:
            return "BROKE_MICRO_SUPPORT"
        return "NO_CLEAR_LEVEL_REJECTION"

    if transition_type == "SELL_TO_BUY":
        if near_low and reclaimed:
            return "RECLAIMED_FROM_LOW_AND_BROKE_UP"
        if near_low:
            return "RECOVERED_FROM_LOW"
        if reclaimed:
            return "BROKE_MICRO_RESISTANCE"
        return "NO_CLEAR_LEVEL_RECOVERY"

    return "NO_TRANSITION"


def _transition_from(old: SignalRow | None, new: SignalRow, recent: list[SignalRow], config: EngineConfig) -> Transition | None:
    if old is None or not old.signal or old.signal == new.signal:
        return None

    transition_type = f"{old.signal}_TO_{new.signal}"
    seconds_between = 0.0
    if old.parsed_time and new.parsed_time:
        seconds_between = max(new.parsed_time - old.parsed_time, 0)
    else:
        seconds_between = 0.0

    price_delta = 0.0
    if old.close is not None and new.close is not None:
        price_delta = new.close - old.close

    velocity_per_min = 0.0
    if seconds_between > 0 and old.close is not None and new.close is not None:
        velocity_per_min = price_delta / seconds_between * 60

    abs_velocity = abs(velocity_per_min)
    recent_avg_velocity = _avg_abs_velocity(recent)
    is_high_velocity = (
        abs_velocity >= config.min_velocity_per_min
        and (recent_avg_velocity == 0 or abs_velocity >= recent_avg_velocity * config.high_velocity_multiplier)
    )

    v_ratio = _volume_ratio(new.volume, old.volume, recent)
    is_volume_expanding = v_ratio >= config.volume_expansion_multiplier

    fast_seconds = config.fast_flip_seconds
    if new.interval == "3m":
        fast_seconds = max(fast_seconds, 180)
    elif new.interval == "5m":
        fast_seconds = max(fast_seconds, 300)
    is_fast = seconds_between == 0 or seconds_between <= fast_seconds
    flip_speed = "FAST" if is_fast else "SLOW"

    price_status = _price_level_status(new, recent, transition_type)
    is_rejection = transition_type == "BUY_TO_SELL" and (
        is_fast and (is_high_velocity or "REJECTED" in price_status or "BROKE" in price_status)
    )
    is_recovery = transition_type == "SELL_TO_BUY" and (
        is_fast and (is_high_velocity or "RECOVERED" in price_status or "BROKE" in price_status or "RECLAIMED" in price_status)
    )

    reason_bits = [
        f"{new.side} {new.interval} {old.signal}→{new.signal}",
        f"speed={flip_speed}",
        f"velocity/min={velocity_per_min:.3f}",
        f"volume_ratio={v_ratio:.2f}",
        f"level={price_status}",
    ]
    return Transition(
        side=new.side,
        interval=new.interval,
        old_signal=old.signal,
        new_signal=new.signal,
        old_close=old.close,
        new_close=new.close,
        old_volume=old.volume,
        new_volume=new.volume,
        seconds_between=round(seconds_between, 2),
        velocity_per_min=round(velocity_per_min, 4),
        price_delta=round(price_delta, 4),
        volume_ratio=round(v_ratio, 3),
        flip_speed=flip_speed,
        transition_type=transition_type,
        is_fast=is_fast,
        is_high_velocity=is_high_velocity,
        is_volume_expanding=is_volume_expanding,
        is_rejection=is_rejection,
        is_recovery=is_recovery,
        price_level_status=price_status,
        reason=" | ".join(reason_bits),
    )


class MTFTimingBlockerEngine:
    """Rule engine for the user's SPX options timing blocker.

    The engine intentionally favors blocking. A BUY label alone never creates
    a full entry. A full entry requires 5m setup, 1m timing trigger,
    velocity, body stacking, volume, and opposite-side bleeding.
    """

    def __init__(self, config: EngineConfig | None = None):
        self.config = config or EngineConfig()

    def _build_latest_from_state(self, state: EngineState) -> dict[str, dict[str, SignalRow]]:
        latest: dict[str, dict[str, SignalRow]] = {"CALL": {}, "PUT": {}}
        for side, intervals in (state.latest or {}).items():
            for interval, row_data in (intervals or {}).items():
                row = _row_from_state(row_data)
                if row:
                    latest.setdefault(side, {})[interval] = row
        return latest

    def _new_rows(self, rows: list[SignalRow], state: EngineState) -> tuple[list[SignalRow], str]:
        seen = set(state.seen_row_keys or [])
        new_rows = [r for r in rows if r.row_key not in seen]
        if new_rows:
            return new_rows, "AUTO" if any(r.source == "AUTO" for r in new_rows) else "MANUAL"
        return [], "CARRIED_FORWARD"

    def _apply_rows_to_latest(
        self,
        rows: list[SignalRow],
        latest: dict[str, dict[str, SignalRow]],
        all_rows: list[SignalRow],
    ) -> tuple[list[Transition], list[Event]]:
        transitions: list[Transition] = []
        events: list[Event] = []
        ordered = sorted(rows, key=lambda r: (r.parsed_time, r.server_time, _interval_rank(r.interval)))
        for row in ordered:
            old = latest.setdefault(row.side, {}).get(row.interval)
            recent = _recent_for(all_rows, row.side, row.interval, n=8)
            transition = _transition_from(old, row, recent, self.config)
            latest[row.side][row.interval] = row

            if transition:
                transitions.append(transition)
                event_type = f"{row.side}_{row.interval}_{transition.transition_type}"
                if transition.is_rejection:
                    event_type = f"{row.side}_{row.interval}_BUY_TO_SELL_REJECTION"
                elif transition.is_recovery:
                    event_type = f"{row.side}_{row.interval}_SELL_TO_BUY_FAST_FLIP"
                events.append(
                    Event(
                        timestamp=now_text(),
                        source=row.source,
                        event_type=event_type,
                        symbol=row.ticker,
                        side=row.side,
                        interval=row.interval,
                        old_signal=transition.old_signal,
                        new_signal=transition.new_signal,
                        candidate_side="",
                        blocking_status="TRANSITION_DETECTED",
                        trade_status="WATCH",
                        grade="",
                        action="WATCH",
                        reason=transition.reason,
                        flip_speed=transition.flip_speed,
                        seconds_between=transition.seconds_between,
                        price_delta=transition.price_delta,
                        velocity_per_min=transition.velocity_per_min,
                        volume_ratio=transition.volume_ratio,
                        price_level_status=transition.price_level_status,
                    )
                )
            else:
                events.append(
                    Event(
                        timestamp=now_text(),
                        source=row.source,
                        event_type=f"{row.side}_{row.interval}_SIGNAL_UPDATE",
                        symbol=row.ticker,
                        side=row.side,
                        interval=row.interval,
                        old_signal=old.signal if old else "",
                        new_signal=row.signal,
                        candidate_side="",
                        blocking_status="SIGNAL_UPDATED",
                        trade_status="WATCH",
                        grade="",
                        action="WATCH",
                        reason=f"{row.side} {row.interval} latest signal = {row.signal}",
                    )
                )
        return transitions, events

    def _recent_rejection(self, side: str, transitions: list[Transition], state: EngineState) -> Transition | dict[str, Any] | None:
        now_ts = datetime.now().timestamp()
        live = [t for t in transitions if t.side == side and t.is_rejection]
        if live:
            return live[-1]
        cached = state.last_rejections.get(side)
        if not cached:
            return None
        try:
            ts = float(cached.get("timestamp_epoch", 0))
            age = now_ts - ts
            if age <= self.config.fresh_rejection_seconds:
                return cached
        except Exception:
            return None
        return None

    def _recent_recovery(self, side: str, transitions: list[Transition], state: EngineState) -> Transition | dict[str, Any] | None:
        now_ts = datetime.now().timestamp()
        live = [t for t in transitions if t.side == side and t.is_recovery]
        if live:
            return live[-1]
        cached = state.last_recoveries.get(side)
        if not cached:
            return None
        try:
            ts = float(cached.get("timestamp_epoch", 0))
            age = now_ts - ts
            if age <= self.config.fresh_rejection_seconds:
                return cached
        except Exception:
            return None
        return None

    def _transition_summary(self, obj: Transition | dict[str, Any] | None) -> str:
        if obj is None:
            return ""
        if isinstance(obj, Transition):
            return f"{obj.side} {obj.interval} {obj.transition_type} {obj.flip_speed} v/min={obj.velocity_per_min} level={obj.price_level_status}"
        return _clean_text(obj.get("summary"))

    def _opposite_bleeding(self, latest: dict[str, dict[str, SignalRow]], rows: list[SignalRow], side: str) -> tuple[bool, str]:
        opposite = "PUT" if side == "CALL" else "CALL"
        opp_1m = _latest_signal(latest, opposite, "1m")
        opp_30s = _latest_signal(latest, opposite, "30s")
        opp_15s = _latest_signal(latest, opposite, "15s")
        opp_rows = _recent_for(rows, opposite, "1m", n=3)
        signal_sell = any(r and r.signal == "SELL" for r in (opp_15s, opp_30s, opp_1m))
        stack_down = _body_stack_down(opp_rows, min_count=1)
        price_down = False
        if len(opp_rows) >= 2 and opp_rows[-1].close is not None and opp_rows[-2].close is not None:
            price_down = opp_rows[-1].close <= opp_rows[-2].close
        is_bleeding = signal_sell and (stack_down or price_down or opp_1m is None or opp_1m.signal == "SELL")
        detail = f"{opposite} signal_sell={signal_sell}, body_down={stack_down}, price_down={price_down}"
        return is_bleeding, detail

    def _candidate_body_velocity_volume(
        self,
        latest: dict[str, dict[str, SignalRow]],
        rows: list[SignalRow],
        side: str,
        transitions: list[Transition],
    ) -> tuple[bool, bool, bool, str, str, str]:
        side_rows_1m = _recent_for(rows, side, "1m", n=5)
        side_rows_30s = _recent_for(rows, side, "30s", n=5)
        stack = _body_stack_up(side_rows_1m, min_count=1) or _body_stack_up(side_rows_30s, min_count=2)

        recent_recovery = [t for t in transitions if t.side == side and t.is_recovery]
        recent_any = [t for t in transitions if t.side == side]
        velocity = any(t.is_high_velocity for t in recent_recovery + recent_any[-2:])

        # If no transition was just recorded, use latest close change as a softer velocity check.
        if not velocity and len(side_rows_1m) >= 2 and side_rows_1m[-1].close is not None and side_rows_1m[-2].close is not None:
            old, new = side_rows_1m[-2], side_rows_1m[-1]
            seconds = max((new.parsed_time or 0) - (old.parsed_time or 0), 1)
            v = abs((new.close or 0) - (old.close or 0)) / seconds * 60
            velocity = v >= self.config.min_velocity_per_min

        volume = any(t.is_volume_expanding for t in recent_recovery + recent_any[-2:])
        if not volume and side_rows_1m:
            vols = [r.volume for r in side_rows_1m[:-1] if r.volume not in (None, 0)]
            last_vol = side_rows_1m[-1].volume
            if vols and last_vol is not None:
                volume = last_vol >= statistics.mean(vols) * self.config.volume_expansion_multiplier

        velocity_status = "VELOCITY_CONFIRMED" if velocity else "VELOCITY_MISSING"
        volume_status = "VOLUME_EXPANDING" if volume else "VOLUME_NOT_EXPANDING"
        body_status = "BODY_STACKING_CORRECT" if stack else "BODY_STACKING_NOT_CLEAN"
        return velocity, volume, stack, velocity_status, volume_status, body_status

    def _is_chop(self, rows: list[SignalRow], side: str, interval: str) -> bool:
        recent = _recent_for(rows, side, interval, n=self.config.chop_lookback_rows)
        if len(recent) < 4:
            return False
        flips = 0
        for old, new in zip(recent, recent[1:]):
            if old.signal and new.signal and old.signal != new.signal:
                flips += 1
        if flips < self.config.max_chop_flips:
            return False
        closes = [r.close for r in recent if r.close is not None]
        if len(closes) < 3:
            return True
        movement = max(closes) - min(closes)
        avg_price = max(statistics.mean(abs(c) for c in closes), 0.01)
        # Too many flips and less than 2% option premium range is chop.
        return movement / avg_price <= 0.02

    def _choose_base_decision(
        self,
        latest: dict[str, dict[str, SignalRow]],
        rows: list[SignalRow],
        transitions: list[Transition],
        state: EngineState,
        source: str,
    ) -> Decision:
        call_1m = _signal_value(latest, "CALL", "1m")
        call_5m = _signal_value(latest, "CALL", "5m")
        put_1m = _signal_value(latest, "PUT", "1m")
        put_5m = _signal_value(latest, "PUT", "5m")

        call_symbol = _symbol_value(latest, "CALL")
        put_symbol = _symbol_value(latest, "PUT")

        def decision(
            candidate_side: str,
            blocking_status: str,
            trade_status: str,
            grade: str,
            action: str,
            reason: str,
            **extra: Any,
        ) -> Decision:
            return Decision(
                timestamp=now_text(),
                source=source,
                call_symbol=call_symbol,
                put_symbol=put_symbol,
                candidate_side=candidate_side,
                blocking_status=blocking_status,
                trade_status=trade_status,
                grade=grade,
                action=action,
                reason=reason,
                call_15s=_signal_value(latest, "CALL", "15s"),
                call_30s=_signal_value(latest, "CALL", "30s"),
                call_1m=call_1m,
                call_3m=_signal_value(latest, "CALL", "3m"),
                call_5m=call_5m,
                put_15s=_signal_value(latest, "PUT", "15s"),
                put_30s=_signal_value(latest, "PUT", "30s"),
                put_1m=put_1m,
                put_3m=_signal_value(latest, "PUT", "3m"),
                put_5m=put_5m,
                **extra,
            )

        # Fast chop protection comes before setup logic.
        if self._is_chop(rows, "CALL", "1m") or self._is_chop(rows, "PUT", "1m"):
            return decision(
                "NONE",
                "CHOP_SIGNAL_NO_TRADE",
                "NO_TRADE",
                "F",
                "NO_TRADE",
                "Signals are flipping rapidly without clean price displacement.",
                event_type="CHOP_SIGNAL_NO_TRADE",
            )

        # Hard blocker: both sides weak/sell. Missing 15s/30s does not hurt this rule.
        if call_1m == "SELL" and put_1m == "SELL":
            return decision(
                "NONE",
                "BLOCKED_BOTH_SIDE_SELL",
                "NO_TRADE",
                "F",
                "NO_TRADE",
                "CALL 1m SELL and PUT 1m SELL: both premiums weak, no clean direction.",
                event_type="BOTH_SIDE_SELL_NO_TRADE",
            )

        # Conflict: both sides say setup at the same time.
        if call_5m == "BUY" and put_5m == "BUY":
            return decision(
                "NONE",
                "BLOCKED_CONFLICT",
                "NO_TRADE",
                "D",
                "WAIT",
                "CALL 5m BUY and PUT 5m BUY: conflict, no clean one-direction timing.",
                event_type="CONFLICT_NO_TRADE",
            )

        # Rejection setup: opposite side tried to recover and failed.
        put_rejection = self._recent_rejection("PUT", transitions, state)
        call_rejection = self._recent_rejection("CALL", transitions, state)

        if call_5m == "BUY" and call_1m == "SELL":
            if put_rejection and (put_5m == "SELL" or put_1m == "SELL"):
                summary = self._transition_summary(put_rejection)
                return decision(
                    "CALL",
                    "BLOCKED_BUT_SETUP_FORMING",
                    "WAIT_FOR_1M_FLIP",
                    "B",
                    "GET_READY",
                    "PUT rejected/recovered failed. CALL 5m setup exists, but CALL 1m is still SELL. Wait for CALL 1m SELL→BUY.",
                    rejection_status="CALL_REJECTION_SETUP_WAIT_FOR_1M_FLIP",
                    fast_flip=summary,
                    price_level_status=summary,
                    event_type="CALL_REJECTION_SETUP_WAIT_FOR_1M_FLIP",
                )
            return decision(
                "CALL",
                "BLOCKED_5M_BUY_1M_SELL",
                "WAIT_FOR_1M_FLIP",
                "C",
                "WAIT",
                "CALL 5m BUY is setup only, but CALL 1m is still SELL. Timing is not ready.",
                event_type="FIVE_MIN_BUY_ONE_MIN_SELL_BLOCK",
            )

        if put_5m == "BUY" and put_1m == "SELL":
            if call_rejection and (call_5m == "SELL" or call_1m == "SELL"):
                summary = self._transition_summary(call_rejection)
                return decision(
                    "PUT",
                    "BLOCKED_BUT_SETUP_FORMING",
                    "WAIT_FOR_1M_FLIP",
                    "B",
                    "GET_READY",
                    "CALL rejected/recovered failed. PUT 5m setup exists, but PUT 1m is still SELL. Wait for PUT 1m SELL→BUY.",
                    rejection_status="PUT_REJECTION_SETUP_WAIT_FOR_1M_FLIP",
                    fast_flip=summary,
                    price_level_status=summary,
                    event_type="PUT_REJECTION_SETUP_WAIT_FOR_1M_FLIP",
                )
            return decision(
                "PUT",
                "BLOCKED_5M_BUY_1M_SELL",
                "WAIT_FOR_1M_FLIP",
                "C",
                "WAIT",
                "PUT 5m BUY is setup only, but PUT 1m is still SELL. Timing is not ready.",
                event_type="FIVE_MIN_BUY_ONE_MIN_SELL_BLOCK",
            )

        # Weak-side recovery trigger: side was weak and suddenly flips SELL→BUY.
        for side in ("CALL", "PUT"):
            recovery = self._recent_recovery(side, transitions, state)
            if not recovery:
                continue
            side_5m = _signal_value(latest, side, "5m")
            side_1m = _signal_value(latest, side, "1m")
            opposite_bleeding, opposite_detail = self._opposite_bleeding(latest, rows, side)
            velocity, volume, stack, velocity_status, volume_status, body_status = self._candidate_body_velocity_volume(
                latest, rows, side, transitions
            )
            summary = self._transition_summary(recovery)
            if side_1m == "BUY" and (side_5m == "BUY" or side_5m == ""):
                if velocity and stack and opposite_bleeding and volume:
                    return decision(
                        side,
                        "PASSED",
                        "GOOD_TIMING_FULL_HAND",
                        "A+",
                        "FULL_HAND",
                        f"{side} weak-side recovery is real: fast SELL→BUY, velocity, volume, body stacking, opposite bleeding.",
                        fast_flip=summary,
                        recovery_status=f"{side}_WEAK_SIDE_RECOVERY_DETECTED",
                        velocity_status=velocity_status,
                        volume_status=volume_status,
                        body_stack_status=body_status,
                        opposite_bleeding=opposite_detail,
                        event_type=f"{side}_WEAK_SIDE_RECOVERY_FULL_HAND",
                    )
                if velocity and opposite_bleeding:
                    return decision(
                        side,
                        "NOT_BLOCKED",
                        "READY_TO_TRADE",
                        "A",
                        "LIGHT_HAND",
                        f"{side} weak-side recovery with velocity. Full-hand still needs volume/body stacking confirmation.",
                        fast_flip=summary,
                        recovery_status=f"{side}_WEAK_SIDE_RECOVERY_DETECTED",
                        velocity_status=velocity_status,
                        volume_status=volume_status,
                        body_stack_status=body_status,
                        opposite_bleeding=opposite_detail,
                        event_type=f"{side}_WEAK_SIDE_RECOVERY_READY_TO_TRADE",
                    )
                return decision(
                    side,
                    "BLOCKED_FAST_FLIP_NO_CONFIRMATION",
                    "NO_TRADE",
                    "C",
                    "WAIT",
                    f"{side} flipped SELL→BUY fast, but confirmation is missing. Do not chase.",
                    fast_flip=summary,
                    recovery_status=f"{side}_WEAK_SIDE_RECOVERY_DETECTED",
                    velocity_status=velocity_status,
                    volume_status=volume_status,
                    body_stack_status=body_status,
                    opposite_bleeding=opposite_detail,
                    event_type="FAST_FLIP_NO_VELOCITY_BLOCK",
                )

        # Normal clean 5m + 1m entry path.
        for side in ("CALL", "PUT"):
            side_5m = _signal_value(latest, side, "5m")
            side_1m = _signal_value(latest, side, "1m")
            if side_5m == "BUY" and side_1m == "BUY":
                opposite_bleeding, opposite_detail = self._opposite_bleeding(latest, rows, side)
                velocity, volume, stack, velocity_status, volume_status, body_status = self._candidate_body_velocity_volume(
                    latest, rows, side, transitions
                )
                if velocity and stack and opposite_bleeding and volume:
                    return decision(
                        side,
                        "PASSED",
                        "GOOD_TIMING_FULL_HAND",
                        "A+",
                        "FULL_HAND",
                        f"{side} 5m BUY + 1m BUY with velocity, body stacking, volume expansion, and opposite bleeding.",
                        velocity_status=velocity_status,
                        volume_status=volume_status,
                        body_stack_status=body_status,
                        opposite_bleeding=opposite_detail,
                        event_type=f"{side}_FULL_TIMING_ALLOWED",
                    )
                if velocity and opposite_bleeding:
                    return decision(
                        side,
                        "NOT_BLOCKED",
                        "READY_TO_TRADE",
                        "A",
                        "LIGHT_HAND",
                        f"{side} 5m BUY + 1m BUY. Timing is ready, but full-hand still needs clean body/volume confirmation.",
                        velocity_status=velocity_status,
                        volume_status=volume_status,
                        body_stack_status=body_status,
                        opposite_bleeding=opposite_detail,
                        event_type=f"{side}_1M_SELL_TO_BUY_ENTRY_TRIGGER",
                    )
                return decision(
                    side,
                    "BLOCKED_FAST_FLIP_NO_CONFIRMATION",
                    "NO_TRADE",
                    "C",
                    "WAIT",
                    f"{side} 5m and 1m are BUY, but velocity/opposite bleeding/body stacking is not strong enough.",
                    velocity_status=velocity_status,
                    volume_status=volume_status,
                    body_stack_status=body_status,
                    opposite_bleeding=opposite_detail,
                    event_type="VELOCITY_MISSING_BLOCK",
                )

        return decision(
            "NONE",
            "BLOCKED_TIMING_NOT_READY",
            "NO_TRADE",
            "D",
            "WAIT",
            "No clean setup/timing combination. Block trade until 5m setup and 1m timing align.",
            event_type="TIMING_NOT_READY",
        )

    def analyze(
        self,
        input_rows: list[dict[str, Any]],
        state: EngineState | None = None,
    ) -> tuple[Decision, list[Event], EngineState, list[list[Any]]]:
        state = state or EngineState()

        normalized = [r for r in (normalize_record(row, source=str(row.get("_source", "AUTO"))) for row in input_rows) if r]
        normalized.sort(key=lambda r: (r.parsed_time, r.server_time, _interval_rank(r.interval)))

        latest = self._build_latest_from_state(state)
        new_rows, source = self._new_rows(normalized, state)

        # If there are no new rows, keep current state and analyze carried-forward signals.
        transitions: list[Transition] = []
        events: list[Event] = []
        if new_rows:
            transitions, events = self._apply_rows_to_latest(new_rows, latest, normalized)
            for row in new_rows:
                state.seen_row_keys.append(row.row_key)
        else:
            source = "CARRIED_FORWARD"

        # Save fresh rejection/recovery memory for future cycles.
        now_epoch = datetime.now().timestamp()
        for t in transitions:
            if t.is_rejection:
                state.last_rejections[t.side] = {
                    "timestamp_epoch": now_epoch,
                    "summary": self._transition_summary(t),
                    "side": t.side,
                    "interval": t.interval,
                    "transition_type": t.transition_type,
                    "velocity_per_min": t.velocity_per_min,
                    "price_level_status": t.price_level_status,
                }
            if t.is_recovery:
                state.last_recoveries[t.side] = {
                    "timestamp_epoch": now_epoch,
                    "summary": self._transition_summary(t),
                    "side": t.side,
                    "interval": t.interval,
                    "transition_type": t.transition_type,
                    "velocity_per_min": t.velocity_per_min,
                    "price_level_status": t.price_level_status,
                }

        decision = self._choose_base_decision(latest, normalized, transitions, state, source=source)

        # Attach candidate/status to transition events.
        for event in events:
            event.candidate_side = decision.candidate_side
            event.blocking_status = decision.blocking_status
            event.trade_status = decision.trade_status
            event.grade = decision.grade
            event.action = decision.action
            if decision.opposite_bleeding and not event.opposite_side_status:
                event.opposite_side_status = decision.opposite_bleeding

        # Write a decision event when status changed or new rows arrived.
        signature = f"{decision.blocking_status}|{decision.trade_status}|{decision.candidate_side}|{decision.action}"
        if signature != state.last_event_signature or new_rows:
            events.append(
                Event(
                    timestamp=decision.timestamp,
                    source=source,
                    event_type=decision.event_type,
                    symbol=f"{decision.call_symbol} / {decision.put_symbol}".strip(" /"),
                    side=decision.candidate_side,
                    interval="MTF",
                    old_signal="",
                    new_signal="",
                    candidate_side=decision.candidate_side,
                    blocking_status=decision.blocking_status,
                    trade_status=decision.trade_status,
                    grade=decision.grade,
                    action=decision.action,
                    reason=decision.reason,
                    flip_speed=decision.fast_flip,
                    price_level_status=decision.price_level_status,
                    opposite_side_status=decision.opposite_bleeding,
                )
            )
            state.last_event_signature = signature

        state.latest = {
            side: {interval: row.to_json() for interval, row in intervals.items()}
            for side, intervals in latest.items()
        }
        state.last_decision_status = decision.blocking_status
        state.last_trade_status = decision.trade_status
        state.updated_at = now_text()

        latest_state_rows = self._latest_state_rows(latest, source)
        return decision, events, state, latest_state_rows

    def _latest_state_rows(self, latest: dict[str, dict[str, SignalRow]], source: str) -> list[list[Any]]:
        rows: list[list[Any]] = []
        for side in ("CALL", "PUT"):
            for interval in TRACKED_INTERVALS:
                row = latest.get(side, {}).get(interval)
                if not row:
                    rows.append([now_text(), source, side, interval, "", "", "", "", "", "", "", "", ""])
                    continue
                rows.append(
                    [
                        now_text(),
                        source,
                        side,
                        interval,
                        row.ticker,
                        row.server_time,
                        row.candle_time,
                        row.open,
                        row.close,
                        row.high,
                        row.low,
                        row.volume,
                        row.signal,
                    ]
                )
        return rows
