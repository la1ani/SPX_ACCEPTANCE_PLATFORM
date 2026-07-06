# SPX_LLM_VISION_TRADER

LLM Vision trading-analysis controller for SPX options.

## Architecture rule

This project follows one rule:

- TradingView chart = visual battlefield
- Playwright = camera / eyes
- Google Sheet = live CALL and PUT evidence
- Python = controller / watcher / loop runner only
- LLM Vision = only brain

Python does not create trading intelligence. Python captures screenshots, reads CALL/PUT sheet evidence, watches LLM-created triggers, sends updated evidence back to the LLM during the battle, stores history, and reports the LLM decision.

## Current active status

GitHub now has an active health-check workflow:

`.github/workflows/spx_llm_vision_trader_ci.yml`

The workflow runs on push, pull request, and manual `workflow_dispatch`. It checks:

1. Python dependencies install
2. Project compiles
3. Strict-mode scan runs
4. Database initialization works

Live TradingView battle watching cannot run inside GitHub Actions because it needs your local browser session, manual TradingView login, your private `.env`, your Google service account file, and live Google Sheet access. The live runner is meant to run on your Windows machine or VPS.

## Fast Windows activation

Open the project folder:

```powershell
cd SPX_LLM_VISION_TRADER
```

Run local health test:

```powershell
.\TEST_WINDOWS.bat
```

Run live watcher:

```powershell
.\RUN_WINDOWS.bat
```

The first live run will create `.env` from `.env.example` if it does not exist. Fill `.env`, then run `RUN_WINDOWS.bat` again.

## Manual Windows setup

```powershell
cd SPX_LLM_VISION_TRADER
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
python main.py --test-strict
python main.py --test-db
python main.py --test-screenshot
python main.py --test-sheets
python main.py
```

## Required `.env` values

Fill these before a live run:

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini
LLM_API_KEY=your_key_here
TRADINGVIEW_URL=https://www.tradingview.com/chart/your-chart
GOOGLE_SHEET_ID=your_google_sheet_id
CALL_SHEET_TAB=CALL
PUT_SHEET_TAB=PUT
GOOGLE_SERVICE_ACCOUNT_FILE=./service_account.json
SCREENSHOT_INTERVAL_SECONDS=30
BATTLE_LOOP_SECONDS=10
DATABASE_PATH=./outputs/spx_llm_vision_trader.db
OUTPUT_DIR=./outputs
BROWSER_PROFILE_DIR=./tradingview_profile
ALERT_MODE=terminal
STRICT_MODE_ENABLED=true
STRICT_MODE_BLOCK=false
```

Do not commit your real `.env` or `service_account.json` to GitHub.

## Run order

Use this sequence:

1. `TEST_WINDOWS.bat`
2. Fill `.env`
3. Put `service_account.json` inside `SPX_LLM_VISION_TRADER/`
4. Share the Google Sheet with the service account email
5. `RUN_WINDOWS.bat`
6. TradingView opens; log in manually if needed
7. System captures the chart, asks the LLM for battle triggers, watches CALL/PUT sheet data, starts battle analysis when trigger conditions activate, and stores results in `outputs/`

## Main commands

```powershell
python main.py --test-strict
python main.py --test-db
python main.py --test-screenshot
python main.py --test-sheets
python main.py --test-alert
python main.py --test-llm-trigger --image outputs\screenshots\your_image.png
python main.py
```

## Project map

```text
SPX_LLM_VISION_TRADER/
├── main.py
├── .env.example
├── requirements.txt
├── README.md
├── RUN_WINDOWS.bat
├── TEST_WINDOWS.bat
├── config/settings.py
├── playwright_engine/
│   ├── chart_capture.py
│   └── tradingview_session.py
├── llm/
│   ├── llm_client.py
│   ├── prompts.py
│   ├── vision_trigger_creator.py
│   └── battle_analyzer.py
├── sheets/google_sheet_reader.py
├── watcher/
│   ├── trigger_watcher.py
│   ├── battle_loop.py
│   └── strict_mode.py
├── storage/
│   ├── database.py
│   └── models.py
├── alerts/alert_manager.py
└── outputs/
```

## Important behavior

The LLM creates the trigger plan from screenshots. Python only watches the trigger plan against Google Sheet evidence. When the trigger activates, Python sends the latest screenshot plus CALL/PUT data back to the LLM. The LLM decides the battle status, winner, grade, missing confirmations, and next action.
