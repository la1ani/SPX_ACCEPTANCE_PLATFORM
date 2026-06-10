# SPX Acceptance Platform

The **SPX Acceptance Platform** is a trading intelligence system focused on evaluating how price interacts with support and resistance zones.  Instead of relying on traditional indicators like RSI or MACD, this project measures whether a zone is **accepted** or **rejected** based on how price behaves after touching it.  The platform ingests live price data from a Google Sheet, calculates zones, analyses price reactions, scores the strength of moves, makes trading decisions and publishes them to both a SQLite database and Telegram.  A live Streamlit dashboard is included to visualise the current state.

## Features

* **Google Sheet integration** – fetches recent price and sentiment data every minute using a service account.
* **SQLite storage** – persists raw market data, detected zones, acceptance results and trade signals.
* **Zone detection** – continuously calculates support and resistance zones using clustering of local highs and lows.
* **Acceptance/Rejection analysis** – determines if price rejects a zone and whether it comes back within a configurable time window.
* **Peak hold time scoring** – measures how long price stays near an extreme after a move to gauge acceptance vs. rejection strength.
* **Return‐to‐zone analysis** – tracks whether price returns to a zone after a rejection and how long it takes.
* **Trade decision engine** – combines the above signals into a final recommendation: `PLAY_CALL`, `PLAY_PUT` or `WAIT`.
* **Telegram alerts** – sends high‑confidence trade ideas via a Telegram bot when the confidence threshold is exceeded.
* **Streamlit dashboard** – displays current zones, scores, return status and the latest trading decision in real time.
* **Configurable and extensible** – uses environment variables and configuration files for easy tuning; the modular architecture makes it straightforward to unit test individual components.

## Installation

1. **Clone the repository** and navigate into the project directory:

   ```bash
   git clone <your‑repo‑url>
   cd SPX_ACCEPTANCE_PLATFORM
   ```

2. **Create a virtual environment** (optional but recommended) and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables**.  Copy the sample `.env.example` to `.env` and edit the values accordingly.  At minimum you need to provide:

   - `GOOGLE_SHEET_ID` – ID of your Google Sheet receiving TradingView alerts
   - `GOOGLE_CREDENTIALS_JSON` – path to your Google service account JSON credentials file
   - `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` – for sending Telegram alerts

   You can also override default zone detection parameters, confidence thresholds and database location via environment variables.  See `config/settings.py` for the full list of options.

4. **Initialise the database**.  The first time you run the platform it will automatically create the SQLite database and its tables under `database/`.

## Usage

Start the main orchestrator which periodically pulls new data from your Google Sheet, updates the database, performs analysis, makes decisions and triggers alerts:

```bash
python main.py
```

To view the live dashboard, run the Streamlit app in a separate terminal:

```bash
streamlit run dashboard/app.py
```

## Project Layout

```
SPX_ACCEPTANCE_PLATFORM/
├── agents/                  # Intelligent components performing individual tasks
│   ├── google_sheet_reader.py
│   ├── zone_detection_agent.py
│   ├── acceptance_rejection_agent.py
│   ├── peak_hold_time_agent.py
│   ├── return_to_zone_agent.py
│   ├── trade_decision_agent.py
│   └── telegram_agent.py
├── database/                # Database helpers and schema
│   └── __init__.py
├── config/                  # Configuration loading from env and defaults
│   └── settings.py
├── dashboard/               # Streamlit application
│   └── app.py
├── logs/                    # Runtime logs (created at runtime)
├── reports/                 # Placeholder for generated reports (if needed)
├── main.py                  # Main orchestrator tying everything together
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## Development Notes

* All modules are fully typed and include basic error handling and logging.
* The architecture separates data ingestion, analysis and decision making to facilitate unit testing and future enhancements.
* The Google Sheet reader is built with `gspread` and a service account; you can replace it with any other data source by implementing the same interface.

## Disclaimer

This project is provided for educational purposes only.  It does not constitute financial advice.  Trade at your own risk.