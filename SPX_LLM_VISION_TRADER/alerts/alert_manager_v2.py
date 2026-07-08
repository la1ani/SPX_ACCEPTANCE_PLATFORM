from __future__ import annotations

from typing import Any

from watcher.alert_intelligence import build_rule_commentary, get_alert_level, get_battle_phase, get_entry_exit_action, get_war_grading


class AlertManagerV2:
    def __init__(self, mode: str = "terminal", telegram_bot_token: str = "", telegram_chat_id: str = "", email_to: str = ""):
        self.mode = (mode or "terminal").lower()
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id
        self.email_to = email_to

    def _format(self, response: dict[str, Any]) -> str:
        grading = get_war_grading(response)
        phase = get_battle_phase(response)
        entry_action = response.get("entry_exit_action") or get_entry_exit_action(response)
        grade_value = grading.get("trade_grade") or response.get("trade_grade") or "WATCH_ONLY"
        confidence = response.get("confidence") or grading.get("grade_confidence") or "LOW"
        commentary = response.get("user_commentary") or build_rule_commentary(response)
        return (
            "SPX BATTLE ALERT\n"
            f"Alert Level: {get_alert_level(response)}\n"
            f"Phase: {phase}\n"
            f"Action: {entry_action}\n"
            f"Decision: {response.get('decision')}\n"
            f"Heavy/Strong Side: {response.get('heavy_side') or response.get('strong_side')}\n"
            f"Weak Side: {response.get('weak_side')}\n"
            f"Winner: {response.get('winner')}\n"
            f"Trade Grade: {grade_value}\n"
            f"Confidence: {confidence}\n"
            f"Entry Reason: {response.get('entry_reason', '')}\n"
            f"Exit Reason: {response.get('exit_reason', '')}\n"
            f"Missing: {', '.join(grading.get('missing_confirmations', []) or [])}\n"
            f"Danger: {', '.join(grading.get('danger_signals', []) or [])}\n"
            f"Next: {response.get('next_action_for_python')}\n"
            f"Commentary:\n{commentary}"
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
            requests.post(url, json={"chat_id": self.telegram_chat_id, "text": text[:3900]}, timeout=10)
        except Exception as exc:
            print(f"[alert] Telegram failed: {exc}")
            print(text)
