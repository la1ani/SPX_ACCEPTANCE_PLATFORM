"""Live SPX opposite-expansion watcher.

There is no support/resistance or level-based decision logic in this entry
point. One side expanding only arms a setup. An alert is sent only after the
other option expands in the opposite direction.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from alerts.alert_manager import AlertManager
from config.settings import load_settings
from expansion_engine import OppositeExpansionEngine
from expansion_vision import extract_candles
from llm.llm_client import LLMClient
from playwright_engine.chart_capture import ChartCapture
from playwright_engine.tradingview_session import TradingViewSession


def _event_payload(decision) -> dict:
    first = decision.first
    confirmation = decision.confirmation
    return {
        "decision": decision.status.value,
        "reason": decision.reason,
        "entry_exit_action": "NOTIFY" if decision.alert else "WAIT",
        "winner": "CALL" if decision.status.value == "CONFIRMED_CALL" else (
            "PUT" if decision.status.value == "CONFIRMED_PUT" else "NONE"
        ),
        "trade_grade": "CONFIRMED" if decision.alert else "NO_TRADE",
        "confidence": "CONFIRMED" if decision.alert else "WAIT",
        "user_commentary": decision.reason,
        "first_expansion": vars(first) if first else None,
        "confirmation_expansion": vars(confirmation) if confirmation else None,
    }


def _write_state(output_dir: Path, payload: dict) -> None:
    path = output_dir / "results" / "expansion_state.json"
    serializable = json.loads(json.dumps(payload, default=str))
    path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")


async def run_live(once: bool = False) -> None:
    settings = load_settings()
    if not settings.llm_api_key or not settings.llm_model or not settings.tradingview_url:
        raise RuntimeError("LLM_API_KEY/OPENAI_API_KEY, LLM_MODEL, and TRADINGVIEW_URL are required.")

    client = LLMClient(settings.llm_provider, settings.llm_model, settings.llm_api_key)
    capture = ChartCapture(settings.output_dir)
    alerts = AlertManager(
        settings.alert_mode,
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        settings.email_alert_to,
    )
    engine = OppositeExpansionEngine()
    session = TradingViewSession(settings.tradingview_url, settings.browser_profile_dir, headless=False)
    page = await session.start()

    print("SPX opposite-expansion watcher started. Support/resistance logic is disabled.")
    try:
        while True:
            screenshot = await capture.capture(page, prefix="expansion")
            streams = extract_candles(client, screenshot)
            decision = engine.process(streams, datetime.now().astimezone())
            payload = _event_payload(decision)
            _write_state(settings.output_dir, payload)
            print(f"{decision.status.value}: {decision.reason}")
            if decision.alert:
                alerts.send_expansion_update(payload)
            if once:
                return
            await asyncio.sleep(settings.screenshot_interval_seconds)
    finally:
        await session.stop()


async def async_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Capture and evaluate one screenshot.")
    args = parser.parse_args()
    await run_live(once=args.once)


if __name__ == "__main__":
    asyncio.run(async_main())
