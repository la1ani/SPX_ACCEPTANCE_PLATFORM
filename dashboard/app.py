"""Streamlit dashboard for the SPX Acceptance Platform.

Run this script with ``streamlit run dashboard/app.py`` to launch a
web interface showing the most recent zone detections, acceptance
results and trade decisions.  The dashboard refreshes automatically
every few seconds to display up‑to‑date information.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, Any

import pandas as pd
import streamlit as st

import sys
from pathlib import Path

# Adjust sys.path so that 'config' and 'database' packages are importable when
# running via `streamlit run dashboard/app.py`.  Streamlit executes this file
# as a script, so relative imports using ``..`` will not resolve.  We append
# the project root to the path to allow ``import config`` to succeed.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import get_settings


def get_db_connection() -> sqlite3.Connection:
    settings = get_settings()
    conn = sqlite3.connect(settings.db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(ttl=10)
def fetch_dashboard_data() -> Dict[str, Any]:
    """Fetch latest data for the dashboard from the database."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        # Latest zone
        cur.execute(
            """
            SELECT * FROM support_resistance ORDER BY id DESC LIMIT 1
            """
        )
        zone_row = cur.fetchone()
        # Latest acceptance result
        cur.execute(
            "SELECT * FROM acceptance_results ORDER BY id DESC LIMIT 1"
        )
        acceptance_row = cur.fetchone()
        # Latest trade signal
        cur.execute("SELECT * FROM trade_signals ORDER BY id DESC LIMIT 1")
        signal_row = cur.fetchone()
    return {
        "zone": dict(zone_row) if zone_row else None,
        "acceptance": dict(acceptance_row) if acceptance_row else None,
        "signal": dict(signal_row) if signal_row else None,
    }


def main() -> None:
    st.set_page_config(page_title="SPX Acceptance Dashboard", page_icon="📈", layout="wide")
    st.title("SPX Acceptance Platform Dashboard")
    data = fetch_dashboard_data()
    zone = data.get("zone")
    acceptance = data.get("acceptance")
    signal = data.get("signal")
    # Show zones
    st.subheader("Latest Zone")
    if zone:
        st.write(f"Type: {zone['zone_type'].title()}")
        st.write(f"Low: {zone['low']:.2f}")
        st.write(f"High: {zone['high']:.2f}")
        st.write(f"Strength: {zone['strength']}")
        st.write(f"Touches: {zone['touches']}")
    else:
        st.info("No zones detected yet.")
    # Acceptance result
    st.subheader("Latest Acceptance Analysis")
    if acceptance:
        st.write(f"Decision: {acceptance['decision']}")
        st.write(f"Bias: {acceptance['bias']}")
        st.write(f"Confidence: {acceptance['confidence']}%")
        st.write(f"Reason: {acceptance['reason']}")
    else:
        st.info("No acceptance results available.")
    # Trade signal
    st.subheader("Latest Trade Signal")
    if signal:
        st.metric(
            label="Decision",
            value=signal['decision'],
        )
        st.metric(
            label="Hold time (min)",
            value=f"{signal['hold_time']:.2f}"
            if signal['hold_time'] is not None
            else "N/A",
        )
        st.metric(
            label="Acceptance score",
            value=f"{signal['acceptance_score']}%",
        )
        st.metric(
            label="Rejection score",
            value=f"{signal['rejection_score']}%",
        )
        st.write(f"Return status: {signal['return_status']}")
        if signal['time_to_return'] is not None:
            st.write(f"Time to return: {signal['time_to_return']:.2f} min")
    else:
        st.info("No trade signals generated yet.")
    st.caption("Data refreshes every 10 seconds.")


if __name__ == "__main__":
    main()
