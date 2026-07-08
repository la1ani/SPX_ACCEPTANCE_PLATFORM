# Alert Fix

The user asked for alerts to clearly show when the battle zone is touched and when the fight starts.

Added:

- `llm/prompts_battle_v2.py`
- `llm/battle_analyzer_v2.py`
- `watcher/alert_intelligence.py`
- upgraded `main.py` to use `BattleAnalyzerV2`
- upgraded `watcher/battle_loop.py` to write readable logs to Google Sheet tabs:
  - `Battle_Commentary`
  - `Entry_Exit_Log`

The LLM is now required to return:

- `FIGHTING_STARTED`
- `battle_phase`
- `user_commentary`
- `entry_exit_action`
- `entry_reason`
- `exit_reason`
- `heavy_side`
- `weak_side`
- factor grades for rejection, holding time, support break, volume imbalance, velocity after failure, and risk

Run:

```powershell
python main.py --test-alert
python main.py
```

Set `.env`:

```text
ALERT_MODE=terminal
```

For Telegram:

```text
ALERT_MODE=telegram
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```
