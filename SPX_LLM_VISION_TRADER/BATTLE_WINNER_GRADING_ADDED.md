# Battle Winner Grading Added

The system now asks the LLM to grade the battle winner continuously.

New required LLM object:

```json
"battle_winner_grading": {
  "current_winner": "CALL | PUT | NONE | UNCLEAR",
  "winner_power_grade": "A_PLUS | A | B | C | D | F | UNCLEAR",
  "winner_power_score": "0-100",
  "power_status": "DOMINANT | STRONG | WINNING | SLIGHT_EDGE | UNCLEAR | FAILED",
  "trade_size_suggestion": "FULL_HAND | LIGHT_HAND | SINGLE | WATCH_ONLY | NO_TRADE | EXIT | FLIP_WATCH",
  "support_break_grade": "A_PLUS | A | B | C | D | F | UNCLEAR",
  "rejection_grade": "A_PLUS | A | B | C | D | F | UNCLEAR",
  "holding_time_grade": "A_PLUS | A | B | C | D | F | UNCLEAR",
  "volume_imbalance_grade": "A_PLUS | A | B | C | D | F | UNCLEAR",
  "velocity_after_failure_grade": "A_PLUS | A | B | C | D | F | UNCLEAR",
  "power_transfer_grade": "A_PLUS | A | B | C | D | F | UNCLEAR",
  "winner_explanation": "why CALL/PUT is winning or not",
  "why_not_a_plus": "what is missing",
  "upgrade_to_a_plus": "what must happen next",
  "downgrade_warning": "what would reduce grade or trigger exit"
}
```

Grade meaning:

- A_PLUS = dominant winner, full-hand quality if risk is clean.
- A = strong winner, full-hand or light-hand depending on risk.
- B = winning but missing key confirmation, light-hand/single.
- C = slight edge, watch only.
- D = unclear or dangerous, no trade.
- F = failed side or invalid battle.
- UNCLEAR = not enough evidence.

Sheet output now includes these fields in:

- Battle_Commentary
- Entry_Exit_Log

Alert output also prints Current Winner, Winner Power Grade, Winner Power Score, Power Status, and trade size suggestion.
