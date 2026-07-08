# Python MTF Timing Blocker + Rejection / Recovery Detector

This module is separate from the LLM battle-zone system. It does not use any LLM.

## Purpose

Do **not** find trades first.

The engine blocks bad timing first, then only allows a trade when timing becomes clean.

Main philosophy:

```text
Block first.
Wait second.
Allow last.
```

## Google Sheet input

Default spreadsheet:

```text
https://docs.google.com/spreadsheets/d/1kdjheVgAkeJWrL7qJjUZZhY4Ms2HI_mC_kovWMXFkXE/edit
```

Default raw tabs:

```text
calls
puts
Manual_Signal_Input
```

Expected columns:

```text
Server Time
Ticker
Exchange
Interval
Candle Time
Open
Close
High
Low
Volume
Signal
Comment
```

Example row:

```text
6/22/2026 20:28:06 | SPXW260623P7490.0 | OPRA | 1m | 2026-06-22T14:57:00Z | 40.2 | 37.1 | 40.2 | 37.1 | 4 | SELL | PUT 1m SELL
```

## Output tabs created by Python

Python creates and writes these tabs:

```text
MTF_Current_Blocker
MTF_Blocker_History
MTF_Event_Log
MTF_Rejection_Watch
MTF_Blocked_Trades
MTF_Allowed_Trades
MTF_Exit_Watch
MTF_Latest_State
MTF_Engine_State
```

Most important live display:

```text
MTF_Current_Blocker
```

Most important analysis history:

```text
MTF_Event_Log
```

## Rules included

### Hard blockers

```text
CALL SELL + PUT SELL = BLOCKED_NO_TRADE
5m BUY + 1m SELL = BLOCKED_TIMING_NOT_READY
Both sides conflict = BLOCKED_CONFLICT
Too many fast flips without price displacement = CHOP_SIGNAL_NO_TRADE
```

### Entry rule

```text
5m BUY = setup
1m BUY = entry trigger
velocity + body stacking + opposite bleeding = full hand
```

### Rejection rule

```text
Weak side BUY → SELL = rejection
Rejection + velocity + level failure = real move
Rejection without velocity = fake flip / no trade
```

### Weak-side recovery rule

```text
Weak side SELL → BUY fast
+ velocity
+ volume
+ body stacking
+ opposite side bleeding
= weak-side recovery trade setup
```

## Main live statuses

Most of the time:

```text
BLOCKED_NO_TRADE
BLOCKED_TIMING_NOT_READY
BLOCKED_5M_BUY_1M_SELL
BLOCKED_BOTH_SIDE_SELL
BLOCKED_CONFLICT
WAIT_FOR_1M_FLIP
CHOP_SIGNAL_NO_TRADE
```

Few times:

```text
READY_TO_TRADE
```

Very rare:

```text
GOOD_TIMING_FULL_HAND
```

## Manual signal input

You can manually enter CALL/PUT signals into:

```text
Manual_Signal_Input
```

If no new auto or manual signal appears, Python keeps analyzing the latest saved signal and marks the source as:

```text
CARRIED_FORWARD
```

## Run

From the `SPX_LLM_VISION_TRADER` folder:

```powershell
python mtf_timing_blocker_main.py
```

Continuous mode:

```powershell
python mtf_timing_blocker_main.py --loop --seconds 15
```

Override sheet or tabs:

```powershell
python mtf_timing_blocker_main.py --sheet-id 1kdjheVgAkeJWrL7qJjUZZhY4Ms2HI_mC_kovWMXFkXE --call-tab calls --put-tab puts
```

## Environment variables

This module reuses the existing Google service account setting from the main program:

```text
GOOGLE_SERVICE_ACCOUNT_FILE
```

Optional MTF-specific settings:

```text
MTF_GOOGLE_SHEET_ID
MTF_CALL_TAB=calls
MTF_PUT_TAB=puts
MTF_MANUAL_TAB=Manual_Signal_Input
MTF_LOOP_SECONDS=15
MTF_LOOKBACK_ROWS=500
MTF_FRESH_REJECTION_SECONDS=120
MTF_FAST_FLIP_SECONDS=90
MTF_MIN_VELOCITY_PER_MIN=0.10
MTF_HIGH_VELOCITY_MULTIPLIER=1.45
MTF_VOLUME_EXPANSION_MULTIPLIER=1.25
MTF_MAX_CHOP_FLIPS=3
MTF_CHOP_LOOKBACK_ROWS=6
```

## Clean sentence

Python does not chase BUY signals.

Python waits for timing, rejection, velocity, and opposite-side failure.

Only then it allows the trade.
