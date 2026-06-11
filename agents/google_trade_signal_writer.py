"""Google Sheet output writer for visible platform decisions."""

from __future__ import annotations

import logging
from dataclasses import dataclass

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    HAS_GSPREAD = True
except ImportError:
    HAS_GSPREAD = False

from config import get_settings

logger = logging.getLogger(__name__)


HEADERS = [
    "Time",
    "Price",
    "Zone",
    "Support",
    "Resistance",
    "Acceptance",
    "Rejection",
    "Return_Time",
    "Decision",
    "Confidence",
    "Reason",
]


@dataclass
class SheetSignalRow:
    time: str
    price: float
    zone: str
    support: str
    resistance: str
    acceptance: str
    rejection: str
    return_time: str
    decision: str
    confidence: int
    reason: str


class GoogleTradeSignalWriter:
    """Append final decision rows to the TRADE_SIGNALS Google Sheet tab."""

    def __init__(self, worksheet_name: str = "TRADE_SIGNALS") -> None:
        settings = get_settings()
        self.sheet_id = settings.google_sheet_id
        self.credentials_path = settings.google_credentials_json
        self.worksheet_name = worksheet_name
        self.client = None
        self.worksheet = None

    def _connect(self):
        if not HAS_GSPREAD:
            raise RuntimeError("gspread and oauth2client are required.")
        if self.worksheet is not None:
            return self.worksheet

        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_path, scope)
        self.client = gspread.authorize(creds)
        spreadsheet = self.client.open_by_key(self.sheet_id)

        try:
            self.worksheet = spreadsheet.worksheet(self.worksheet_name)
        except gspread.WorksheetNotFound:
            self.worksheet = spreadsheet.add_worksheet(
                title=self.worksheet_name,
                rows=1000,
                cols=len(HEADERS),
            )

        current = self.worksheet.get_all_values()
        if not current or current[0][: len(HEADERS)] != HEADERS:
            self.worksheet.clear()
            self.worksheet.append_row(HEADERS, value_input_option="USER_ENTERED")

        return self.worksheet

    def append(self, row: SheetSignalRow) -> None:
        worksheet = self._connect()
        worksheet.append_row(
            [
                row.time,
                round(float(row.price), 2),
                row.zone,
                row.support,
                row.resistance,
                row.acceptance,
                row.rejection,
                row.return_time,
                row.decision,
                int(row.confidence),
                row.reason,
            ],
            value_input_option="USER_ENTERED",
        )
        logger.info("Wrote row to %s", self.worksheet_name)
