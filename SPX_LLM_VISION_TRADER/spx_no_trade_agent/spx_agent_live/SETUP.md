# Setup guide — no technical background needed

Everything is already written for you. This is a checklist of things only
YOU can provide (your accounts, your VPS), typed exactly as shown. If
something goes wrong at any step, copy the exact error message and paste it
back — that's all that's needed to fix it.

## What you need before starting

1. **Your VPS** — the one already running your Python/Google Sheets setup.
   You'll need to be able to log into it (usually via a program called SSH,
   or whatever your VPS provider gives you — e.g. a "Console" or "Terminal"
   button on their website).
2. **An Anthropic API key** — go to https://console.anthropic.com, sign in,
   click "API Keys", click "Create Key". Copy it somewhere safe. This is
   what lets the agent read the chart.
3. **Your TradingView login** (username/password you already use).
4. **Your Google Sheet's two CSV export links** (the call sheet and the put
   sheet). If you don't already have these, tell me the sheet names and I
   can walk you through getting them — it's copying a URL, nothing more.

## Step 1 — Get the files onto your VPS

On your own computer, download the two things I've given you in this chat:
- `spx_no_trade_agent.zip` (the reasoning engine)
- The `spx_agent_live` folder (the live-connection code) — ask me to zip
  this one too if you don't see a download link for it yet, and I'll
  package it the same way.

Upload both to your VPS. If you don't know how, tell me what your VPS
provider is (e.g. DigitalOcean, AWS, Linode) and I'll give you the exact
steps for that provider.

## Step 2 — Log into your VPS

Open a terminal / SSH connection to your VPS (your provider's dashboard
will show you how — usually a button that says "Console" or a command like
`ssh yourname@your-vps-ip`).

## Step 3 — Unzip everything

```
unzip spx_no_trade_agent.zip
cd spx_agent_live
```

## Step 4 — Run the setup script

```
bash setup.sh
```

This installs everything automatically. It will take a few minutes. If it
stops with a red error message, copy the whole message and send it to me.

## Step 5 — Fill in your settings

```
cp .env.example .env
nano .env
```

This opens a simple text editor. Replace each placeholder with your real
values (your sheet links, your chart links, your Anthropic API key). To
save and exit: press `Ctrl+O`, then `Enter`, then `Ctrl+X`.

## Step 6 — Log into TradingView once

```
python save_tradingview_session.py
```

This opens a browser window. Log into TradingView in that window exactly
like you always do. Then come back to the terminal and press Enter. This
saves your login so the agent doesn't need to ask again.

## Step 7 — Test it

```
python run_live.py
```

You should see lines start printing — that's the agent narrating what it's
seeing live. Let it run for a few minutes and watch the output. Press
`Ctrl+C` to stop it.

If you see an error instead of narration lines, copy the error and send it
to me — most first-run errors are a typo in the `.env` file (Step 5) and
take one line to fix.

## Step 8 — (Optional) Make it run automatically, all the time

This makes it restart itself if the VPS reboots or it crashes, so you don't
have to babysit it.

```
sudo cp spx-agent.service /etc/systemd/system/
sudo nano /etc/systemd/system/spx-agent.service
```

Replace every `YOUR_USERNAME` in that file with your actual VPS username
(run `whoami` in the terminal if you're not sure what that is), save
(`Ctrl+O`, `Enter`, `Ctrl+X`), then:

```
sudo systemctl daemon-reload
sudo systemctl enable spx-agent
sudo systemctl start spx-agent
```

To check it's running: `sudo systemctl status spx-agent`
To watch its live output: `tail -f agent.log`
To stop it: `sudo systemctl stop spx-agent`

## What to do if you get stuck anywhere

Come back to this conversation, tell me which step number you're on, and
paste whatever error or output you're seeing. I'll tell you exactly what to
type next — you don't need to understand *why*, just what to run.

## Important: this does not place trades

As built, this only watches and narrates — it tells you what it sees
(trade / no-trade / cautious) but does not connect to a broker or execute
anything. That's a deliberate, separate step for later, once you've
watched it run for a while and trust what it's calling.
