#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt >/dev/null

if [ ! -f "dashboard_api.py" ]; then
  echo "ERROR: dashboard_api.py not found"
  exit 1
fi

if [ ! -d "outputs" ]; then
  mkdir -p outputs
fi

if [ -f ".dashboard_api.pid" ]; then
  OLD_PID=$(cat .dashboard_api.pid || true)
  if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
    kill "$OLD_PID" || true
    sleep 1
  fi
fi

nohup .venv/bin/uvicorn dashboard_api:app --host 0.0.0.0 --port 8000 > outputs/dashboard_api.log 2>&1 &
echo $! > .dashboard_api.pid

sleep 3

if curl -fsS http://127.0.0.1:8000/api/health >/dev/null; then
  echo ""
  echo "============================================="
  echo "SPX DASHBOARD API IS LIVE"
  echo "Local health: http://127.0.0.1:8000/api/health"
  echo "War Room API: http://127.0.0.1:8000/api/dashboard/current"
  echo "Logs: $(pwd)/outputs/dashboard_api.log"
  echo "PID: $(cat .dashboard_api.pid)"
  echo "============================================="
else
  echo "ERROR: API did not start. Check outputs/dashboard_api.log"
  tail -n 50 outputs/dashboard_api.log || true
  exit 1
fi
