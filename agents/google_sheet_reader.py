"""Google Sheets reader agent.

This agent encapsulates the logic required to connect to a Google Sheet
and retrieve the latest rows of trading data.  It relies on a service
account JSON file pointed to by the ``GOOGLE_CREDENTIALS_JSON``
environment variable and expects the sheet to contain at least the
columns ``timestamp`` and ``price``.  Optional columns include
``signal``, ``call_pressure`` and ``put_pressure``.  If those columns
are present they will be included in the returned dataframe.

For unit testing or offline operation, you can subclass this class and
override :meth:`read_latest_rows` to return synthetic data.
"""

from __future__ import annotations

import logging
from typing import List

import pandas as pd
from pyparsing import col

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    HAS_GSPREAD = True
except ImportError:
    HAS_GSPREAD = False

from config import get_settings

logger = logging.getLogger(__name__)

class GoogleSheetReader:
    """Reads price data from a Google Sheet.

    The sheet must have a header row with at least ``timestamp`` and
    ``price``.  Timestamps should be ISO 8601 strings and prices
    numeric.  Additional columns are optional.  All rows are returned as
    a Pandas dataframe with appropriate data types.
    """

    def __init__(self, worksheet_name: str = "ES_PRICE") -> None:
        settings = get_settings()
        self.sheet_id = settings.google_sheet_id
        self.credentials_path = settings.google_credentials_json
        self.worksheet_name = worksheet_name
        self.client = None

        if not HAS_GSPREAD:
            logger.warning(
                "gspread is not installed. GoogleSheetReader will not work."
            )

    def _authorize(self) -> gspread.Client:
        """Authorise the service account and return a gspread client."""
        if not HAS_GSPREAD:
            raise RuntimeError(
                "gspread is missing. Install gspread and oauth2client to use GoogleSheetReader."
            )
        if self.client is not None:
            return self.client
        scope = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        if not self.credentials_path:
            raise ValueError(
                "GOOGLE_CREDENTIALS_JSON is not set. Provide the path to a service account JSON file."
            )
        creds = ServiceAccountCredentials.from_json_keyfile_name(self.credentials_path, scope)
        self.client = gspread.authorize(creds)
        return self.client

    def read_latest_rows(self, limit: int = 1000) -> pd.DataFrame:
        """Read the most recent rows from the sheet.

        Parameters
        ----------
        limit : int
            Maximum number of rows to return.  The newest rows will be
            returned first.

        Returns
        -------
        pandas.DataFrame
            A dataframe with the columns present in the sheet.  The
            ``timestamp`` column is converted to datetime and ``price``
            to float.  Missing optional columns are filled with ``None``.
        """
        if not self.sheet_id:
            raise ValueError("GOOGLE_SHEET_ID is not configured.")
        client = self._authorize()
        try:
            sheet = client.open_by_key(self.sheet_id)
            worksheet = sheet.worksheet(self.worksheet_name)
            print("CONNECTED TO:", worksheet.title)
        except Exception as exc:
            logger.error("Failed to open Google Sheet: %s", exc)
            raise

        rows: List[List[str]]
        try:
            # Fetch all values including header row
            rows = worksheet.get_all_values()
        except Exception as exc:
            logger.error("Failed to read data from Google Sheet: %s", exc)
            raise

        if not rows:
            return pd.DataFrame()
        header = [h.strip() for h in rows[0]]
        print("HEADERS FOUND:", header)
        data_rows = rows[1:][-limit:]
        df = pd.DataFrame(data_rows, columns=header)
        # Ensure expected columns exist
        # ES_PRICE sheet columns:
        # Time | Ticker | Open | High | Low | Close | Volume

        # Build a case-insensitive mapping of available columns
        col_map = {c.lower(): c for c in df.columns}
        def _find(name: str):
            return col_map.get(name.lower())

        # Required columns
        for col in ["Time", "Close"]:
            if not _find(col):
                raise ValueError(f"Google Sheet must contain a '{col}' column.")

        time_col = _find("Time")
        close_col = _find("Close")

        # Convert time and price
        df["timestamp"] = (
            pd.to_datetime(df[time_col], utc=True, errors="coerce")
            .dt.tz_convert("America/Chicago")
        )
        df["price"] = pd.to_numeric(df[close_col], errors="coerce")

        # Numeric columns commonly present in ES_PRICE
        for num in ["Open", "High", "Low", "Volume"]:
            act = _find(num)
            if act:
                df[num] = pd.to_numeric(df[act], errors="coerce")
            else:
                df[num] = None

        # Ticker as string (preserve if present)
        ticker_act = _find("Ticker")
        if ticker_act:
            df["Ticker"] = df[ticker_act].astype(str)
        else:
            df["Ticker"] = None

        # Preserve older optional columns
        optional = ["signal", "call_pressure", "put_pressure"]
        for col in optional:
            act = _find(col)
            if act:
                if col in ["call_pressure", "put_pressure"]:
                    df[col] = pd.to_numeric(df[act], errors="coerce")
                else:
                    df[col] = df[act]
            else:
                df[col] = None

        # Drop rows missing timestamp or price
        df = df.dropna(subset=["timestamp", "price"])
        # Sort by timestamp ascending
        df = df.sort_values("timestamp")
        return df.reset_index(drop=True)
