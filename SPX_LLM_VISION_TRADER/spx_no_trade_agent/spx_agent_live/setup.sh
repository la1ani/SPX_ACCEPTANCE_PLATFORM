#!/usr/bin/env bash
# One-time setup on a fresh Ubuntu VPS. Run as: bash setup.sh
set -e

echo "== Installing Python + system deps =="
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip

echo "== Creating virtual environment =="
python3 -m venv venv
source venv/bin/activate

echo "== Installing Python packages =="
pip install --upgrade pip
pip install -r requirements.txt
pip install -e ../spx_no_trade_agent

echo "== Installing Playwright browser =="
playwright install --with-deps chromium

echo ""
echo "Setup done. Remaining manual steps (see SETUP.md):"
echo "  1. Copy .env.example to .env and fill in your values"
echo "  2. Run 'python save_tradingview_session.py' once to log into TradingView"
echo "     and save the session (avoids logging in every run)"
echo "  3. Run 'python run_live.py' to start, or install the systemd service"
echo "     for it to run automatically (see spx-agent.service)"
