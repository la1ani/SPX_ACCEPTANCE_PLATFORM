# Alert and Battle Commentary Upgrade

The system now includes `watcher/alert_intelligence.py`, `llm/prompts_battle_v2.py`, and `llm/battle_analyzer_v2.py`.

This upgrade makes battle alerts say:

- FIGHTING_STARTED when an LLM battle zone is touched
- heavy/strong side
- weak side
- rejection status
- holding-time status
- weak-side support break status
- opposite-side support hold status
- volume imbalance status
- velocity-after-failure status
- missing confirmations
- danger signals
- entry/exit action
- full hand/light hand/single/watch/no trade/exit/flip watch grade

`main.py` now uses `BattleAnalyzerV2`, so the LLM prompt asks for the full battle commentary and grading.

If alerts still do not appear, check `.env`:

```text
ALERT_MODE=terminal
```

For Telegram, set:

```text
ALERT_MODE=telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Google Sheet tabs used for logs:

- Trigger_Zones
- LLM_Zone_View
- Watch_Log
- AI_Log
- Alert_Log
- Auto_Check
- Best_Alerts

