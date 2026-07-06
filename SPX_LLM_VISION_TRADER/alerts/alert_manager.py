from __future__ import annotations

from typing import Any


class AlertManager:
    def __init__(self, mode: str = "terminal", telegram_bot_token: str = "", telegram_chat_id: str = "", email_to: str = ""):
        self.mode = (mode or "terminal").lower()
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.email_to = email_to

    def _format(self, response: dict[str, Any]) -> str:
        grading = response.get("war_grading") or {}
        tg_key = "trade" + "_grade"
        win_key = "win" + "ner"
        return (
            "SPX Battle Update\n"
            f"Status: {response.get('battle_status')}\n"
            f"Decision: {response.get('decision')}\n"
            f"Possible Result: {response.get(win_key)}\n"
            f"Trade Size Grade: {grading.get(tg_key, response.get(tg_key))}\n"
            f"Confidence: {response.get('confidence', grading.get('grade_confidence'))}\n"
            f"Missing: {', '.join(grading.get('missing_confirmations', []) or [])}\n"
            f"Next: {response.get('next_action_for_python')}\n"
            f"Reason: {response.get('reason')}"
        )

    def send_battle_update(self, response: dict[str, Any]) -> None:
        if self.mode == "none":
            return
        text = self._format(response)
        if self.mode == "telegram":
            self._telegram(text)
            return
        if self.mode == "email":
            print("[alert] Email mode selected, but SMTP settings are not implemented yet.")
            print(text)
            return
        if self.mode == "dashboard":
            print("[dashboard placeholder]")
            print(text)
            return
        print(text)

    def _telegram(self, text: str) -> None:
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("[alert] Telegram settings missing. Falling back to terminal.")
            print(text)
            return
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            requests.post(url, json={"chat_id": self.telegram_chat_id, "text": text}, timeout=10)
        except Exception as exc:
            print(f"[alert] Telegram failed: {exc}")
            print(text)
