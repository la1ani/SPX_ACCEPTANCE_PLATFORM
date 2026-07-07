from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
SECRET_NAME = "LLM_" + "API" + "_KEY"
OPENAI_SECRET_NAME = "OPENAI_" + "API" + "_KEY"


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    llm_provider: str
    llm_model: str
    llm_api_key: str
    tradingview_url: str
    google_sheet_id: str
    call_sheet_tab: str
    put_sheet_tab: str
    call_link_tab: str
    put_link_tab: str
    google_service_account_file: str
    screenshot_interval_seconds: int
    battle_loop_seconds: int
    database_path: Path
    output_dir: Path
    alert_mode: str
    telegram_bot_token: str
    telegram_chat_id: str
    email_alert_to: str
    dashboard_enabled: bool
    strict_mode_enabled: bool
    strict_mode_block: bool
    browser_profile_dir: Path

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "screenshots").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "logs").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "results").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "raw_llm").mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.browser_profile_dir.mkdir(parents=True, exist_ok=True)

    def validate_for_live_run(self) -> None:
        required = {
            SECRET_NAME: self.llm_api_key,
            "LLM_MODEL": self.llm_model,
            "TRADINGVIEW_URL": self.tradingview_url,
            "GOOGLE_SHEET_ID": self.google_sheet_id,
            "CALL_SHEET_TAB": self.call_sheet_tab,
            "PUT_SHEET_TAB": self.put_sheet_tab,
            "GOOGLE_SERVICE_ACCOUNT_FILE": self.google_service_account_file,
        }
        missing = [key for key, value in required.items() if not str(value).strip()]
        if missing:
            raise RuntimeError("Missing required .env values: " + ", ".join(missing))


def load_settings(env_file: Optional[str] = None) -> Settings:
    env_path = Path(env_file) if env_file else ROOT_DIR / ".env"
    if env_path.exists():
        # override=True is important on Windows because blank shell environment
        # variables can otherwise block values saved in .env from loading.
        load_dotenv(env_path, override=True)
    else:
        load_dotenv(override=True)
    output_dir = Path(os.getenv("OUTPUT_DIR", str(ROOT_DIR / "outputs")))
    database_path = Path(os.getenv("DATABASE_PATH", str(ROOT_DIR / "outputs" / "spx_llm_vision_trader.db")))
    browser_profile_dir = Path(os.getenv("BROWSER_PROFILE_DIR", str(ROOT_DIR / "tradingview_profile")))
    settings = Settings(
        root_dir=ROOT_DIR,
        llm_provider=os.getenv("LLM_PROVIDER", "openai").strip().lower(),
        llm_model=os.getenv("LLM_MODEL", "gpt-4.1-mini").strip(),
        llm_api_key=os.getenv(SECRET_NAME, os.getenv(OPENAI_SECRET_NAME, "")).strip(),
        tradingview_url=os.getenv("TRADINGVIEW_URL", "").strip(),
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID", "").strip(),
        call_sheet_tab=os.getenv("CALL_SHEET_TAB", "CALLS").strip(),
        put_sheet_tab=os.getenv("PUT_SHEET_TAB", "PUTS").strip(),
        call_link_tab=os.getenv("CALL_LINK_TAB", "CALLS_LINK").strip(),
        put_link_tab=os.getenv("PUT_LINK_TAB", "PUTS_LINK").strip(),
        google_service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip(),
        screenshot_interval_seconds=_int_env("SCREENSHOT_INTERVAL_SECONDS", 15),
        battle_loop_seconds=_int_env("BATTLE_LOOP_SECONDS", 10),
        database_path=database_path,
        output_dir=output_dir,
        alert_mode=os.getenv("ALERT_MODE", "terminal").strip().lower(),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        email_alert_to=os.getenv("EMAIL_ALERT_TO", "").strip(),
        dashboard_enabled=_bool_env("DASHBOARD_ENABLED", False),
        strict_mode_enabled=_bool_env("STRICT_MODE_ENABLED", True),
        strict_mode_block=_bool_env("STRICT_MODE_BLOCK", False),
        browser_profile_dir=browser_profile_dir,
    )
    settings.ensure_dirs()
    return settings
