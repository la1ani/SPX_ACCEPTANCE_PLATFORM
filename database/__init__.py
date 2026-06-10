"""SQLite database helper functions.

This module encapsulates all interactions with the SQLite database used
by the SPX Acceptance Platform.  It defines a number of functions to
initialise the schema and insert or query data.  Using a single module
for database access makes it easier to migrate to a different backend
in the future and facilitates unit testing by allowing the database
functions to be mocked.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Optional, Tuple, List, Dict, Any

from ..config import get_settings


def _get_connection() -> sqlite3.Connection:
    """Return a SQLite connection using the configured database path.

    Connections are opened in autocommit mode and row factory returns
    dictionaries for convenience.
    """
    settings = get_settings()
    db_path = settings.db_path
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_cursor() -> Iterator[sqlite3.Cursor]:
    """Context manager yielding a database cursor and committing on exit.

    Use this in a ``with`` block to ensure that transactions are
    committed or rolled back properly.
    """
    conn = _get_connection()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    finally:
        cur.close()
        conn.close()


def init_db() -> None:
    """Initialise the database schema if it does not already exist.

    This function creates all tables defined for the platform.  It is
    idempotent and can be called multiple times without side effects.
    """
    with get_cursor() as cur:
        # Market data table stores raw price feed and pressures
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS market_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                price REAL NOT NULL,
                signal TEXT,
                call_pressure REAL,
                put_pressure REAL
            )
            """
        )
        # Detected zones (support/resistance)
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS support_resistance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_type TEXT NOT NULL,
                low REAL NOT NULL,
                high REAL NOT NULL,
                strength INTEGER,
                touches INTEGER,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        # Zone events record entry/rejection/return events
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS zone_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_id INTEGER,
                event_type TEXT,
                timestamp TEXT,
                price REAL,
                FOREIGN KEY(zone_id) REFERENCES support_resistance(id)
            )
            """
        )
        # Acceptance results summarise the zone analysis
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS acceptance_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                zone_id INTEGER,
                zone_type TEXT,
                zone_low REAL,
                zone_high REAL,
                entered_time TEXT,
                rejection_time TEXT,
                returned_time TEXT,
                decision TEXT,
                bias TEXT,
                confidence INTEGER,
                reason TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(zone_id) REFERENCES support_resistance(id)
            )
            """
        )
        # Trade signals combine acceptance results with additional scoring
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acceptance_id INTEGER,
                hold_time REAL,
                acceptance_score INTEGER,
                rejection_score INTEGER,
                return_status TEXT,
                time_to_return REAL,
                decision TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY(acceptance_id) REFERENCES acceptance_results(id)
            )
            """
        )


def insert_market_data(rows: Iterable[Tuple[str, float, Optional[str], Optional[float], Optional[float]]]) -> None:
    """Insert multiple rows into the ``market_data`` table.

    Parameters
    ----------
    rows : iterable of tuples
        Each tuple must contain `(timestamp, price, signal, call_pressure, put_pressure)`.
    """
    with get_cursor() as cur:
        cur.executemany(
            """INSERT INTO market_data (timestamp, price, signal, call_pressure, put_pressure)
            VALUES (?, ?, ?, ?, ?)""",
            rows,
        )


def fetch_recent_market_data(limit: int = 1000) -> List[sqlite3.Row]:
    """Fetch the most recent market data rows.

    Returns a list of sqlite3.Row objects sorted by timestamp ascending.
    """
    with get_cursor() as cur:
        cur.execute(
            """SELECT * FROM market_data ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        )
        rows = cur.fetchall()
    return list(reversed(rows))


def insert_zone(zone_type: str, low: float, high: float, strength: int, touches: int) -> int:
    """Insert a detected zone and return its database ID."""
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO support_resistance (zone_type, low, high, strength, touches)
            VALUES (?, ?, ?, ?, ?)""",
            (zone_type, low, high, strength, touches),
        )
        zone_id = cur.lastrowid
    return zone_id


def insert_acceptance_result(
    zone_id: Optional[int],
    zone_type: str,
    zone_low: float,
    zone_high: float,
    entered_time: str,
    rejection_time: Optional[str],
    returned_time: Optional[str],
    decision: str,
    bias: str,
    confidence: int,
    reason: str,
) -> int:
    """Insert an acceptance result and return its database ID."""
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO acceptance_results (
                zone_id, zone_type, zone_low, zone_high, entered_time, rejection_time,
                returned_time, decision, bias, confidence, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                zone_id,
                zone_type,
                zone_low,
                zone_high,
                entered_time,
                rejection_time,
                returned_time,
                decision,
                bias,
                confidence,
                reason,
            ),
        )
        acceptance_id = cur.lastrowid
    return acceptance_id


def insert_trade_signal(
    acceptance_id: int,
    hold_time: float,
    acceptance_score: int,
    rejection_score: int,
    return_status: str,
    time_to_return: Optional[float],
    decision: str,
) -> int:
    """Insert a trade signal and return its ID."""
    with get_cursor() as cur:
        cur.execute(
            """INSERT INTO trade_signals (
                acceptance_id, hold_time, acceptance_score, rejection_score,
                return_status, time_to_return, decision
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                acceptance_id,
                hold_time,
                acceptance_score,
                rejection_score,
                return_status,
                time_to_return,
                decision,
            ),
        )
        signal_id = cur.lastrowid
    return signal_id
