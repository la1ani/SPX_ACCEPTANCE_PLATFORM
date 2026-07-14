"""
Trade logger.

Writes every simulated trade (entry through exit) as one row, so results
can be reviewed like a trade journal — exactly what's needed to answer
"is the rule correct or wrong."

CSV logging always works, no setup required. Google Sheets write-back is
optional and requires a service account (see README section on this) since
writing to a sheet needs different credentials than the read-only CSV
export URL used elsewhere in this project — that's a real, unavoidable
extra setup step if you want results to land directly in your sheet
instead of / in addition to a local file.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .models import SimulatedTrade

FIELDNAMES = [
    "trade_id", "side", "entry_timestamp", "entry_price", "entry_reasoning",
    "exit_timestamp", "exit_price", "exit_reason", "peak_price", "pnl_pct",
]


class CsvTradeLogger:
    def __init__(self, path: str | Path = "simulated_trades.csv"):
        self.path = Path(path)
        if not self.path.exists():
            with self.path.open("w", newline="") as f:
                csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()

    def log(self, trade: SimulatedTrade) -> None:
        with self.path.open("a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writerow({
                "trade_id": trade.trade_id,
                "side": trade.side.value,
                "entry_timestamp": trade.entry_timestamp.isoformat(),
                "entry_price": trade.entry_price,
                "entry_reasoning": trade.entry_reasoning,
                "exit_timestamp": trade.exit_timestamp.isoformat() if trade.exit_timestamp else "",
                "exit_price": trade.exit_price,
                "exit_reason": trade.exit_reason,
                "peak_price": trade.peak_price,
                "pnl_pct": round(trade.pnl_pct, 2) if trade.pnl_pct is not None else "",
            })

    def summary(self) -> dict:
        """Read the log back and compute win rate / avg P&L — the direct answer to 'is the rule correct'."""
        if not self.path.exists():
            return {}
        rows = []
        with self.path.open() as f:
            for row in csv.DictReader(f):
                if row["pnl_pct"] not in ("", None):
                    rows.append(row)

        if not rows:
            return {"total_trades": 0}

        pnls = [float(r["pnl_pct"]) for r in rows]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        exit_reasons = {}
        for r in rows:
            exit_reasons[r["exit_reason"]] = exit_reasons.get(r["exit_reason"], 0) + 1

        return {
            "total_trades": len(rows),
            "win_rate_pct": round(len(wins) / len(rows) * 100, 1),
            "avg_pnl_pct": round(sum(pnls) / len(pnls), 2),
            "avg_win_pct": round(sum(wins) / len(wins), 2) if wins else 0,
            "avg_loss_pct": round(sum(losses) / len(losses), 2) if losses else 0,
            "exit_reason_breakdown": exit_reasons,
        }


class GoogleSheetTradeLogger:
    """
    Optional write-back to a Google Sheet tab, using a service account.
    Requires: pip install gspread google-auth

    Setup (one-time, on your side):
      1. In Google Cloud Console, create a service account and download its
         JSON key file.
      2. Share your Google Sheet with that service account's email address
         (found inside the JSON key file), giving it Editor access.
      3. Pass the JSON key file path and the sheet name below.

    This is a genuinely separate setup step from the read-only CSV export
    URL used elsewhere in this project — reading a published sheet needs no
    credentials, but WRITING to one always requires an authenticated
    service account. There's no way around that on Google's side.
    """

    def __init__(self, service_account_json_path: str, sheet_id: str, worksheet_name: str = "Simulated Trades"):
        import gspread

        gc = gspread.service_account(filename=service_account_json_path)
        sh = gc.open_by_key(sheet_id)
        try:
            self.worksheet = sh.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            self.worksheet = sh.add_worksheet(title=worksheet_name, rows=1000, cols=len(FIELDNAMES))
            self.worksheet.append_row(FIELDNAMES)

    def log(self, trade: SimulatedTrade) -> None:
        self.worksheet.append_row([
            trade.trade_id,
            trade.side.value,
            trade.entry_timestamp.isoformat(),
            trade.entry_price,
            trade.entry_reasoning,
            trade.exit_timestamp.isoformat() if trade.exit_timestamp else "",
            trade.exit_price,
            trade.exit_reason,
            trade.peak_price,
            round(trade.pnl_pct, 2) if trade.pnl_pct is not None else "",
        ])
