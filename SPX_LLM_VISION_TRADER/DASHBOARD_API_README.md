# SPX War Room Dashboard API

This is a read-only API for the existing SPX_LLM_VISION_TRADER system.

It does not make trading decisions, change triggers, modify battle logic, or write to the trading database. It only reads the SQLite data already produced by the live SPX system and exposes dashboard-friendly JSON for Base44 or another frontend.

## Install

From `SPX_LLM_VISION_TRADER`:

```bash
pip install -r requirements.txt
```

## Run

```bash
python dashboard_api.py
```

Default address:

```text
http://0.0.0.0:8000
```

## Main endpoints

### Current War Room state

```text
GET /api/dashboard/current
```

Returns:

- system status
- battle active/inactive state
- battle phase
- current winner
- strong side / weak side / attacking side
- winner power grade and score
- trade size suggestion
- trade grade and confidence
- support-break grade
- rejection grade
- holding-time grade
- opposite-side support-hold grade
- volume-imbalance grade
- velocity-after-failure grade
- power-transfer grade
- trade-risk grade
- missing confirmations
- danger signals
- why not A+
- what upgrades to A+
- downgrade warning
- latest commentary
- current trigger/battle zones
- CALL and PUT latest prices when available
- last completed battle result
- key timestamps

### Health

```text
GET /api/health
```

### Battle history

```text
GET /api/dashboard/history?limit=50
```

### Grade progression

```text
GET /api/dashboard/grade-progression
```

Optional specific session:

```text
GET /api/dashboard/grade-progression?battle_session_id=123
```

### Battle timeline

```text
GET /api/dashboard/timeline?limit=100
```

## API documentation

FastAPI automatically provides:

```text
GET /docs
```

## Environment settings

Optional:

```env
DASHBOARD_API_HOST=0.0.0.0
DASHBOARD_API_PORT=8000
DASHBOARD_ALLOWED_ORIGINS=*
```

For production, replace `*` with the exact Base44 app origin when known.

Example:

```env
DASHBOARD_ALLOWED_ORIGINS=https://your-base44-app-domain.example
```

## Recommended VPS architecture

```text
Existing SPX Live System
    -> SQLite database + Google Sheet logs
    -> dashboard_api.py (read-only)
    -> HTTPS reverse proxy/domain
    -> Base44 SPX War Room dashboard
```

## Important

The dashboard API should be deployed behind HTTPS before connecting it to a public Base44 app. Use a reverse proxy such as Nginx or Caddy, or expose it through your existing VPS domain.
