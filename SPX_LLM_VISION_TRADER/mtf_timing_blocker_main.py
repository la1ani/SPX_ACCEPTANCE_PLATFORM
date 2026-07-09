from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from config.settings import load_settings
from mtf_timing_blocker.engine import EngineConfig, EngineState, MTFTimingBlockerEngine
from mtf_timing_blocker.google_sheet_io import MTFSheetIO


DEFAULT_MTF_SHEET_ID = "1kdjheVgAkeJWrL7qJjUZZhY4Ms2HI_mC_kovWMXFkXE"


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    return int(value)


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    return float(value)


def build_engine_config() -> EngineConfig:
    return EngineConfig(
        fresh_rejection_seconds=_int_env("MTF_FRESH_REJECTION_SECONDS", 120),
        fast_flip_seconds=_int_env("MTF_FAST_FLIP_SECONDS", 90),
        high_velocity_multiplier=_float_env("MTF_HIGH_VELOCITY_MULTIPLIER", 1.45),
        min_velocity_per_min=_float_env("MTF_MIN_VELOCITY_PER_MIN", 0.10),
        volume_expansion_multiplier=_float_env("MTF_VOLUME_EXPANSION_MULTIPLIER", 1.25),
        max_chop_flips=_int_env("MTF_MAX_CHOP_FLIPS", 3),
        chop_lookback_rows=_int_env("MTF_CHOP_LOOKBACK_ROWS", 6),
    )


def build_sheet_io(args: argparse.Namespace) -> tuple[MTFSheetIO, int]:
    settings = load_settings(args.env_file)
    sheet_id = (
        args.sheet_id
        or os.getenv("MTF_GOOGLE_SHEET_ID", "").strip()
        or os.getenv("GOOGLE_SHEET_ID", "").strip()
        or DEFAULT_MTF_SHEET_ID
    )
    call_tab = args.call_tab or os.getenv("MTF_CALL_TAB", "calls").strip() or "calls"
    put_tab = args.put_tab or os.getenv("MTF_PUT_TAB", "puts").strip() or "puts"
    manual_tab = args.manual_tab or os.getenv("MTF_MANUAL_TAB", "Manual_Signal_Input").strip() or "Manual_Signal_Input"
    lookback_rows = args.lookback_rows or _int_env("MTF_LOOKBACK_ROWS", 200)

    sheet_io = MTFSheetIO(
        sheet_id=sheet_id,
        service_account_file=settings.google_service_account_file,
        call_tab=call_tab,
        put_tab=put_tab,
        manual_tab=manual_tab,
    )
    sheet_io.ensure_output_tabs()
    return sheet_io, lookback_rows


def run_once(args: argparse.Namespace, sheet_io: MTFSheetIO | None = None, lookback_rows: int | None = None) -> None:
    if sheet_io is None or lookback_rows is None:
        sheet_io, lookback_rows = build_sheet_io(args)

    state_json = sheet_io.read_engine_state_json()
    state = EngineState.from_json(state_json)

    input_rows = sheet_io.read_input_rows(lookback_rows=lookback_rows)
    engine = MTFTimingBlockerEngine(build_engine_config())
    decision, events, new_state, latest_state_rows = engine.analyze(input_rows=input_rows, state=state)

    sheet_io.snapshot(
        decision=decision,
        events=events,
        latest_state_rows=latest_state_rows,
        state_json=new_state.to_json(),
        updated_at=new_state.updated_at,
    )

    print(
        f"{decision.timestamp} | {decision.candidate_side} | "
        f"{decision.blocking_status} | {decision.trade_status} | "
        f"{decision.grade} | {decision.action} | {decision.reason}"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Python MTF Timing Blocker + Rejection / Recovery Detector."
    )
    parser.add_argument("--env-file", default=None, help="Optional .env file path.")
    parser.add_argument("--sheet-id", default="", help="Google Sheet ID. Defaults to MTF_GOOGLE_SHEET_ID, GOOGLE_SHEET_ID, then Sam's MTF sheet.")
    parser.add_argument("--call-tab", default="", help="Calls tab name. Default: calls")
    parser.add_argument("--put-tab", default="", help="Puts tab name. Default: puts")
    parser.add_argument("--manual-tab", default="", help="Manual signal tab name. Default: Manual_Signal_Input")
    parser.add_argument("--lookback-rows", type=int, default=0, help="Rows to read from each input tab. Default: MTF_LOOKBACK_ROWS or 200.")
    parser.add_argument("--loop", action="store_true", help="Run continuously.")
    parser.add_argument("--seconds", type=int, default=0, help="Loop interval seconds. Default: MTF_LOOP_SECONDS or 30.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not args.loop:
        run_once(args)
        return 0

    seconds = args.seconds or _int_env("MTF_LOOP_SECONDS", 30)
    sheet_io, lookback_rows = build_sheet_io(args)
    print(f"MTF Timing Blocker running every {seconds} seconds. Press Ctrl+C to stop.")
    while True:
        try:
            run_once(args, sheet_io=sheet_io, lookback_rows=lookback_rows)
        except KeyboardInterrupt:
            print("Stopped.")
            return 0
        except Exception as exc:
            print(f"MTF Timing Blocker error: {exc}")
        time.sleep(seconds)


if __name__ == "__main__":
    raise SystemExit(main())
