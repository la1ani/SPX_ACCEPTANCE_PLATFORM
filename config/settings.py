"""Application configuration.

This module defines a dataclass `Settings` that holds all runtime
configuration options.  Values are loaded from environment variables
where present, otherwise sensible defaults are used.  The settings
object is initialised once per process and cached via the
``get_settings`` function.

Environment variables allow you to configure:

* **DB_PATH** – path to the SQLite database file (default: ``spx_acceptance.db``)
* **GOOGLE_SHEET_ID** – ID of the Google Sheet used for price feed
* **GOOGLE_CREDENTIALS_JSON** – path to a JSON service account key for Google API
* **TELEGRAM_BOT_TOKEN** – Telegram bot token
* **TELEGRAM_CHAT_ID** – Chat ID (integer) for Telegram alerts
* **ZONE_TOLERANCE_POINTS** – allowed distance between local highs/lows when clustering zones
* **ZONE_MIN_TOUCHES** – minimum number of touches required to form a zone
* **REJECTION_POINTS** – number of points price must move away from a zone to count as rejection/bounce
* **RETURN_WINDOW_MINUTES** – minutes allowed for price to return to a zone after rejection
* **CONFIDENCE_THRESHOLD** – minimum confidence percentage required to send a trade signal
* **PEAK_HOLD_THRESHOLD** – fractional distance from extreme considered as "near the extreme" when calculating hold time

Additional environment variables may be added in future without breaking
the API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv


@dataclass
class Settings:
    """Dataclass containing application settings.

    Do not instantiate directly; use :func:`get_settings` to load values
    from the environment.  All attributes have defaults but may be
    overridden by environment variables.
    """

    db_path: str = "spx_acceptance.db"
    google_sheet_id: str = ""
    google_credentials_json: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    zone_tolerance_points: float = 1.5
    zone_min_touches: int = 2
    rejection_points: float = 3.0
    return_window_minutes: int = 3
    confidence_threshold: int = 80
    peak_hold_threshold: float = 0.1

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables.

        Environment variables override the default values defined in
        the dataclass.  Numeric fields are converted from strings with
        appropriate error handling.  ``dotenv`` is loaded implicitly to
        support local development.
        """
        # Load variables from a .env file if present
        load_dotenv()

        def _get_env(name: str, default: Optional[str]) -> Optional[str]:
            value = os.getenv(name)
            return value if value is not None and value != "" else default

        def _to_int(name: str, default: int) -> int:
            value = _get_env(name, None)
            if value is None:
                return default
            try:
                return int(value)
            except ValueError:
                return default

        def _to_float(name: str, default: float) -> float:
            value = _get_env(name, None)
            if value is None:
                return default
            try:
                return float(value)
            except ValueError:
                return default

        return cls(
            db_path=_get_env("DB_PATH", cls.db_path),
            google_sheet_id=_get_env("GOOGLE_SHEET_ID", cls.google_sheet_id),
            google_credentials_json=_get_env("GOOGLE_CREDENTIALS_JSON", cls.google_credentials_json),
            telegram_bot_token=_get_env("TELEGRAM_BOT_TOKEN", cls.telegram_bot_token),
            telegram_chat_id=_get_env("TELEGRAM_CHAT_ID", cls.telegram_chat_id),
            zone_tolerance_points=_to_float("ZONE_TOLERANCE_POINTS", cls.zone_tolerance_points),
            zone_min_touches=_to_int("ZONE_MIN_TOUCHES", cls.zone_min_touches),
            rejection_points=_to_float("REJECTION_POINTS", cls.rejection_points),
            return_window_minutes=_to_int("RETURN_WINDOW_MINUTES", cls.return_window_minutes),
            confidence_threshold=_to_int("CONFIDENCE_THRESHOLD", cls.confidence_threshold),
            peak_hold_threshold=_to_float("PEAK_HOLD_THRESHOLD", cls.peak_hold_threshold),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached instance of :class:`Settings` loaded from the environment.

    Subsequent calls return the same object.  This function should be
    used throughout the codebase to access configuration values.
    """
    return Settings.from_env()
