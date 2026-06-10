"""Telegram alert agent.

This agent sends trade alerts via a Telegram bot.  It reads the bot
token and chat ID from the application settings.  If either is not
configured, sending is skipped with a warning.  The agent uses the
``python-telegram-bot`` library in synchronous mode.  Should the
library be unavailable, an error is logged.
"""

from __future__ import annotations

import logging
from typing import Optional

try:
    from telegram import Bot
except ImportError:
    Bot = None  # type: ignore

from ..config import get_settings


logger = logging.getLogger(__name__)


class TelegramAgent:
    """Sends formatted messages to a Telegram chat."""

    def __init__(self) -> None:
        settings = get_settings()
        self.token: str = settings.telegram_bot_token
        self.chat_id: str = settings.telegram_chat_id
        self.bot: Optional[Bot] = None
        if self.token and Bot is not None:
            try:
                self.bot = Bot(token=self.token)
            except Exception as exc:
                logger.error("Failed to initialise Telegram bot: %s", exc)
                self.bot = None

    def send_alert(self, message: str) -> None:
        """Send an alert message to the configured Telegram chat.

        If the bot token or chat ID is missing, the message will not be
        sent.  Errors during sending are logged but do not raise.
        """
        if not self.token or not self.chat_id:
            logger.warning("Telegram credentials are not configured; skipping alert.")
            return
        if Bot is None:
            logger.error(
                "python-telegram-bot is not installed; cannot send Telegram messages."
            )
            return
        if self.bot is None:
            logger.error("Telegram bot not initialised; cannot send message.")
            return
        try:
            self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode="HTML")
            logger.info("Sent Telegram alert")
        except Exception as exc:
            logger.error("Failed to send Telegram alert: %s", exc)
