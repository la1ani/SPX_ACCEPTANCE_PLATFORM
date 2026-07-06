from __future__ import annotations

from pathlib import Path
from typing import Any
import re

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


class GoogleSheetReader:
    def __init__(self, sheet_id: str, service_account_file: str | Path, call_tab: str, put_tab: str):
        self.sheet_id = sheet_id
        self.service_account_file = Path(service_account_file)
        self.call_tab = call_tab
        self.put_tab = put_tab
        self.client = None
        self.sheet = None

    def connect(self) -> None:
        if not self.sheet_id:
            raise RuntimeError("GOOGLE_SHEET_ID is missing in .env")
        if not self.service_account_file.exists():
            raise FileNotFoundError(f"Google service account file not found: {self.service_account_file}")
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError as exc:
            raise RuntimeError("Install Google Sheet packages: pip install gspread google-auth") from exc
        creds = Credentials.from_service_account_file(str(self.service_account_file), scopes=SCOPES)
        self.client = gspread.authorize(creds)
        self.sheet = self.client.open_by_key(self.sheet_id)

    def _worksheet_rows(self, tab_name: str) -> list[dict[str, Any]]:
        if self.sheet is None:
            self.connect()
        assert self.sheet is not None
        return self.sheet.worksheet(tab_name).get_all_records()

    def _clean_key(self, key: str) -> str:
        key = str(key or "").strip().lower()
        return re.sub(r"[^a-z0-9]+", "_", key).strip("_")

    def _number(self, value: Any) -> Any:
        if isinstance(value, (int, float)):
            return value
        text = str(value).replace(",", "").strip()
        if text == "":
            return None
        try:
            return float(text) if "." in text else int(text)
        except ValueError:
            return value

    def _normalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        normalized = {self._clean_key(k): self._number(v) for k, v in row.items()}
        aliases = {"timestamp": ["time", "datetime", "date_time", "created_at"], "price": ["close", "last", "ltp", "option_price"], "high": ["h"], "low": ["l"], "volume": ["vol", "contracts"], "velocity": ["speed", "delta_speed"]}
        for target, keys in aliases.items():
            if target not in normalized or normalized.get(target) in (None, ""):
                for candidate in keys:
                    if candidate in normalized and normalized.get(candidate) not in (None, ""):
                        normalized[target] = normalized[candidate]
                        break
        return normalized

    def read_recent(self, limit: int = 50) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        call_rows = [self._normalize_row(row) for row in self._worksheet_rows(self.call_tab)]
        put_rows = [self._normalize_row(row) for row in self._worksheet_rows(self.put_tab)]
        return call_rows[-limit:], put_rows[-limit:]
