"""Entry point for SPX_LLM_VISION_TRADER.

This program captures evidence, calls the LLM, and stores the LLM response.
"""

from __future__ import annotations

import argparse
import asyncio
from rich.console import Console

from alerts.alert_manager import AlertManager
from config.settings import load_settings
from llm.battle_analyzer import BattleAnalyzer
from llm.llm_client import LLMClient
from llm.vision_trigger_creator import VisionTriggerCreator
from playwright_engine.chart_capture import ChartCapture
from playwright_engine.tradingview_session import TradingViewSession
from sheets.google_sheet_reader import GoogleSheetReader
from storage.database import Database
from watcher.battle_loop import BattleLoop
from watcher.strict_mode import StrictModeScanner
from watcher.trigger_watcher import TriggerWatcher

console = Console()


async def run_live(args: argparse.Namespace) -> None:
    settings = load_settings()
    if settings.strict_mode_enabled:
        StrictModeScanner(settings.root_dir).print_report(block=settings.strict_mode_block)
    settings.validate_for_live_run()

    db = Database(settings.database_path)
    client = LLMClient(settings.llm_provider, settings.llm_model, settings.llm_api_key)
    trigger_creator = VisionTriggerCreator(client)
    battle_analyzer = BattleAnalyzer(client)
    sheet_reader = GoogleSheetReader(settings.google_sheet_id, settings.google_service_account_file, settings.call_sheet_tab, settings.put_sheet_tab)
    capture = ChartCapture(settings.output_dir)
    alert_manager = AlertManager(settings.alert_mode, settings.telegram_bot_token, settings.telegram_chat_id, settings.email_alert_to)

    session = TradingViewSession(settings.tradingview_url, settings.browser_profile_dir, headless=False)
    page = await session.start()
    try:
        console.print("[green]TradingView opened. Log in manually if needed.[/green]")
        initial_screenshot = await capture.capture(page, prefix="initial")
        console.print(f"Initial screenshot saved: {initial_screenshot}")

        trigger_plan_model, raw = trigger_creator.create_trigger_plan(initial_screenshot)
        trigger_plan = trigger_plan_model.model_dump()
        db.save_raw_llm_response("trigger", raw, trigger_plan)
        trigger_plan_id = db.save_trigger_plan(initial_screenshot, trigger_plan)
        watcher = TriggerWatcher(trigger_plan, max_age_seconds=max(120, settings.screenshot_interval_seconds * 10))
        console.print("[green]LLM trigger plan saved. Watch loop started.[/green]")

        while True:
            call_rows, put_rows = sheet_reader.read_recent(limit=80)
            db.save_sheet_snapshot(call_rows, put_rows)
            watch_result = watcher.check(call_rows, put_rows)
            console.print(f"Watch action: {watch_result.action} | {watch_result.reason}")

            if watch_result.action == "START_BATTLE":
                loop = BattleLoop(db, battle_analyzer, capture, sheet_reader, settings.battle_loop_seconds, alert_manager)
                result = await loop.run(page, trigger_plan_id, trigger_plan, watch_result.trigger_type, max_cycles=args.max_battle_cycles)
                console.print(f"LLM battle result: {result.get('decision')} | {result.get('battle_status')}")
                if str(result.get("battle_status", "")).upper() in {"NEW_TRIGGER_REQUIRED", "INVALID"} or str(result.get("decision", "")).upper() == "NEW_TRIGGER_REQUIRED":
                    new_screenshot = await capture.capture(page, prefix="new_trigger")
                    trigger_plan_model, raw = trigger_creator.create_trigger_plan(new_screenshot)
                    trigger_plan = trigger_plan_model.model_dump()
                    db.save_raw_llm_response("trigger", raw, trigger_plan)
                    trigger_plan_id = db.save_trigger_plan(new_screenshot, trigger_plan)
                    watcher.update_plan(trigger_plan)
                else:
                    await asyncio.sleep(settings.screenshot_interval_seconds)

            elif watch_result.action == "NEW_TRIGGER_REQUIRED":
                new_screenshot = await capture.capture(page, prefix="new_trigger")
                trigger_plan_model, raw = trigger_creator.create_trigger_plan(new_screenshot)
                trigger_plan = trigger_plan_model.model_dump()
                db.save_raw_llm_response("trigger", raw, trigger_plan)
                trigger_plan_id = db.save_trigger_plan(new_screenshot, trigger_plan)
                watcher.update_plan(trigger_plan)
                console.print("[green]New LLM trigger plan saved.[/green]")
            else:
                await asyncio.sleep(settings.screenshot_interval_seconds)
    finally:
        await session.stop()


async def test_screenshot() -> None:
    settings = load_settings()
    session = TradingViewSession(settings.tradingview_url, settings.browser_profile_dir, headless=False)
    page = await session.start()
    try:
        path = await ChartCapture(settings.output_dir).capture(page, prefix="test")
        console.print(f"Screenshot saved: {path}")
    finally:
        await session.stop()


def test_sheets() -> None:
    settings = load_settings()
    reader = GoogleSheetReader(settings.google_sheet_id, settings.google_service_account_file, settings.call_sheet_tab, settings.put_sheet_tab)
    call_rows, put_rows = reader.read_recent(limit=5)
    console.print("CALL rows:")
    console.print(call_rows)
    console.print("PUT rows:")
    console.print(put_rows)


def test_db() -> None:
    settings = load_settings()
    Database(settings.database_path).save_sheet_snapshot([], [])
    console.print(f"Database ready: {settings.database_path}")


def test_alert() -> None:
    settings = load_settings()
    alerts = AlertManager(settings.alert_mode, settings.telegram_bot_token, settings.telegram_chat_id, settings.email_alert_to)
    alerts.send_battle_update({"battle_status": "ACTIVE", "decision": "CONTINUE_ANALYZING", "winner": "NONE", "trade_grade": "WATCH_ONLY", "confidence": "LOW", "reason": "Test alert only.", "next_action_for_python": "KEEP_WATCHING", "war_grading": {"missing_confirmations": ["test missing item"]}})


def test_strict() -> None:
    settings = load_settings()
    StrictModeScanner(settings.root_dir).print_report(block=False)


async def test_llm_trigger(image_path: str | None) -> None:
    settings = load_settings()
    if image_path is None:
        console.print("Provide --image path/to/screenshot.png")
        return
    creator = VisionTriggerCreator(LLMClient(settings.llm_provider, settings.llm_model, settings.llm_api_key))
    plan, raw = creator.create_trigger_plan(image_path)
    Database(settings.database_path).save_raw_llm_response("test_trigger", raw, plan.model_dump())
    console.print(plan.model_dump())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SPX_LLM_VISION_TRADER")
    parser.add_argument("--test-screenshot", action="store_true")
    parser.add_argument("--test-sheets", action="store_true")
    parser.add_argument("--test-db", action="store_true")
    parser.add_argument("--test-alert", action="store_true")
    parser.add_argument("--test-strict", action="store_true")
    parser.add_argument("--test-llm-trigger", action="store_true")
    parser.add_argument("--image", default=None)
    parser.add_argument("--max-battle-cycles", type=int, default=60)
    return parser


async def async_main() -> None:
    args = build_parser().parse_args()
    if args.test_screenshot:
        await test_screenshot()
    elif args.test_sheets:
        test_sheets()
    elif args.test_db:
        test_db()
    elif args.test_alert:
        test_alert()
    elif args.test_strict:
        test_strict()
    elif args.test_llm_trigger:
        await test_llm_trigger(args.image)
    else:
        await run_live(args)


if __name__ == "__main__":
    asyncio.run(async_main())
