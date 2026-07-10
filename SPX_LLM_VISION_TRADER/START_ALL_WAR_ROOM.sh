#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

mkdir -p outputs

# Create/reuse virtual environment and install project requirements.
if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt >/dev/null

stop_pidfile() {
  local pidfile="$1"
  if [ -f "$pidfile" ]; then
    local old_pid
    old_pid=$(cat "$pidfile" 2>/dev/null || true)
    if [ -n "${old_pid:-}" ] && kill -0 "$old_pid" >/dev/null 2>&1; then
      kill "$old_pid" || true
      sleep 1
    fi
  fi
}

start_background() {
  local name="$1"
  local pidfile="$2"
  local logfile="$3"
  shift 3

  stop_pidfile "$pidfile"
  nohup "$@" > "$logfile" 2>&1 &
  echo $! > "$pidfile"
  sleep 1

  local pid
  pid=$(cat "$pidfile")
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "[OK] $name started (PID $pid)"
  else
    echo "[ERROR] $name failed to start. Last log lines:"
    tail -n 50 "$logfile" || true
    exit 1
  fi
}

# 1) Start the read-only FastAPI dashboard API.
bash START_DASHBOARD_FAST.sh

# 2) Start the independent Python MTF timing blocker.
start_background \
  "Python MTF Timing Blocker" \
  ".mtf_timing_blocker.pid" \
  "outputs/mtf_timing_blocker.log" \
  .venv/bin/python mtf_timing_blocker_main.py --loop --seconds "${MTF_LOOP_SECONDS:-15}"

# 3) Start the LLM battle engine. It remains fully independent from the MTF blocker.
# main.py opens TradingView with a visible browser. On a headless VPS, use xvfb-run when available.
if [ -z "${DISPLAY:-}" ] && command -v xvfb-run >/dev/null 2>&1; then
  start_background \
    "LLM Battle Engine" \
    ".battle_engine.pid" \
    "outputs/battle_engine.log" \
    xvfb-run -a .venv/bin/python main.py
else
  start_background \
    "LLM Battle Engine" \
    ".battle_engine.pid" \
    "outputs/battle_engine.log" \
    .venv/bin/python main.py
fi

sleep 3

echo ""
echo "============================================="
echo "SPX WAR ROOM BACKEND START STATUS"
echo "============================================="

echo "Dashboard API PID: $(cat .dashboard_api.pid 2>/dev/null || echo NOT_RUNNING)"
echo "MTF Blocker PID:   $(cat .mtf_timing_blocker.pid 2>/dev/null || echo NOT_RUNNING)"
echo "Battle Engine PID: $(cat .battle_engine.pid 2>/dev/null || echo NOT_RUNNING)"
echo ""

if curl -fsS http://127.0.0.1:8000/api/health >/dev/null; then
  echo "[OK] Dashboard API health"
else
  echo "[ERROR] Dashboard API health failed"
  tail -n 50 outputs/dashboard_api.log || true
  exit 1
fi

MTF_RESPONSE=$(curl -fsS "http://127.0.0.1:8000/api/mtf/current?force_refresh=true" || true)
if [ -n "$MTF_RESPONSE" ]; then
  echo "[OK] MTF endpoint responded"
else
  echo "[WARNING] MTF endpoint did not return data"
fi

WAR_RESPONSE=$(curl -fsS http://127.0.0.1:8000/api/dashboard/current || true)
if [ -n "$WAR_RESPONSE" ]; then
  echo "[OK] War Room endpoint responded"
else
  echo "[WARNING] War Room endpoint did not return data"
fi

echo ""
echo "Local health:   http://127.0.0.1:8000/api/health"
echo "Local MTF API:  http://127.0.0.1:8000/api/mtf/current"
echo "Local War Room: http://127.0.0.1:8000/api/dashboard/current"
echo ""
echo "Logs:"
echo "  Dashboard API: outputs/dashboard_api.log"
echo "  MTF blocker:   outputs/mtf_timing_blocker.log"
echo "  Battle engine: outputs/battle_engine.log"
echo ""
echo "IMPORTANT:"
echo "  Battle engine and MTF timing blocker remain separate decision systems."
echo "  This script starts both; neither overrides the other."
echo ""
echo "Public VPS IP: $(curl -4 -s --max-time 5 ifconfig.me || echo NOT_AVAILABLE)"
echo "============================================="
