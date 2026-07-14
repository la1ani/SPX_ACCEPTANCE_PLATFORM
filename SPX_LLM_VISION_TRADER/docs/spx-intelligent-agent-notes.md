# SPX 0DTE call/put intelligent agent — consolidated notes

## 0. What we're actually building

**Why this matters:** most traders already make money on their winning trades — the profit isn't the hard part. What erodes it is continuing to trade through no-trade zones afterward and giving those gains back. This system's value isn't primarily about catching more winning trades; it's about **not giving back what's already been made**, by refusing to trade during the conditions (consolidation, unconfirmed short-timeframe noise, weak rejections) where that giveback happens.

**This is a reasoning agent, not a rule-following agent.** It combines Python calculation with LLM input, together with the live data coming in from the Google Sheet — the judgment comes from that combination, not from Python alone applying fixed thresholds and not from the LLM alone interpreting the chart.

**The core purpose: knowing when NOT to trade.** Everyone already knows the "trade" condition — support breaks with velocity and volume, trade the direction. That part is well-known and not the hard problem. What's actually missing, and the entire point of building this, is a real-time "no-trade" signal — synthesizing the chart (candle stacking), the live data (velocity, volume, holding time), and the level (support/resistance) together to recognize, live, when conditions do *not* support a trade. Everything else in this system — the rejection logic, the fork between rejection and break, the two evidence streams, the alignment check between them — exists to make that no-trade call trustworthy in real time. It is not a trade-entry tool with a no-trade filter added on; the no-trade detection is the core deliverable.

**It's one classification process, not several separate ones.** Since everything reduces to pattern and data, the agent reads candle stacking, wicks, and the sheet data together — combined, these classify the current zone as one of: **bullish** (price will move up), **bearish** (price will move down), **consolidation** (flat, no directional attempt), or a **slow-moving zone** (some attempt at movement, but the body isn't confirming with conviction — the cautious/reduced case, distinct from flat consolidation). The agent isn't "look for a trade, and if nothing is found, default to no-trade" — it is actively pattern-matching for all four states with equal rigor. A wrongly-called no-trade zone (mistaking real momentum for chop) is just as much a failure as mistaking chop for a real signal.

**The goal, restated simply:** the reasoning agent understands the pattern (chart + data together) and then issues a call — and most of the time, the correct call is no-trade. Clean bullish/bearish setups (candle stacking and sheet data both confirming a real move) are the rare case, not the common one. The agent should be calibrated to expect and correctly call "no trade" as the default state, with a real trade call being the exception it earns only when both evidence streams genuinely align.

A live, automated trading-assistant system for SPX 0DTE call/put options that:

1. **Watches two live data streams continuously** during market hours — the raw call/put price and volume feed (via Google Sheet, fed by TradingView) and the chart itself (support/resistance levels, indicators, candle shape, and buy/sell signal markers, extracted via an LLM/vision step + Playwright).
2. **Combines Python calculation with LLM input** — a chart-side path (candle stacking, wick/body shape, consolidation, holding time, informed by what the LLM reads off the chart) and a data-side path (velocity, volume, price action, the call/put see-saw correlation, from the Google Sheet) — each asking the same underlying question ("is this consolidation, momentum, rejection, or a real break-and-reverse?") from different evidence.
3. **Cross-checks the two sides against each other** using the principle that the same pattern should show up in both streams; a "boss" layer compares them and issues the final call only when they agree, or flags a no-trade situation when they don't.
4. **Prioritizes calling the no-trade zone correctly** as much as calling the trade itself — since avoiding chop/liquidity traps matters as much as catching the real setups on 0DTE premium.
5. **Learns from outcomes over time** — logging what the level, velocity, volume, and holding time looked like going into each reaction, and what actually happened after, so its thresholds/judgment improve rather than staying fixed.
6. **Narrates its reasoning live** in plain language as it goes, rather than only firing silent binary alerts.

**Where the LLM fits:** it reads the TradingView chart image and extracts structured facts (support/resistance level, indicator readings, candle body stacking) that Python can't derive from raw numbers alone — but its output feeds directly into the reasoning, it isn't a separate mechanical step bolted onto a purely-Python decision engine. The reasoning is the combination of what the LLM reads off the chart and what Python calculates from the sheet data, not either one in isolation.

Estimated added cost for the LLM chart-reading step, at a 60-second refresh, full market hours: roughly $15–43/month depending on how much is extracted per call (see section 8).

---

## 1. The core trade thesis (the foundation — everything else supports this)

SPX 0DTE call and put prices see-saw against each other: when one side rises, the other tends to fall, and vice versa. Support and resistance are the most important piece of the whole system — every other layer exists only to judge whether a level is holding or breaking, and whether that read can be trusted.

**The core pattern:**

- The **weak side** approaches its resistance (or support) level.
- If there is **no velocity, no volume, and no holding time** at that level → the weak side gets **rejected** and reverses.
- **Rejection is the trigger.** Right after a real rejection, the **strong side moves fast**.
- The moment of rejection is the **best entry point on the strong side**, because premium is cheapest right then — before the move gets priced in. Waiting until after the strong side has already started moving means paying up.
- If the weak side instead **breaks its level with velocity AND volume together**, it is no longer the weak side — the move is real, and the other (previously strong) side will **continue to rise**. This is not a trap; don't fade it.
- If a breakout is seen on the strong side while the weak side's support is still intact, that breakout is a **fake breakout / liquidity trap** — it will snap back.
- Repeated failed attempts at the same level reinforce the read (more rejections = more confidence it's genuinely weak); the read only flips once an actual break happens.

### The fork

| Condition | What happens | What it means |
|---|---|---|
| Support intact, weak side rejected | Weak side snaps back, strong side accelerates fast | Best entry — cheap premium, high-confidence trade |
| Support breaks with velocity + volume | Weak side converts into real strength | No trap — genuine directional move, don't fade it |

### The mechanism, simplified

If price reaches a support (or resistance) level and velocity/volume die off there, that's the direct, mechanical reason price stops moving — that dying-off *is* consolidation, not a separate phenomenon that happens to occur near a level.

**Support/resistance is fractal — every timeframe has its own level.** Even a very short window (e.g. 15 seconds) has its own local support and resistance. Consolidation at that short-timeframe scale simply means price isn't breaking its own short-timeframe support or resistance — the same rejection-vs-break fork applies at 15-second resolution just as it does at the 15-minute/indicator-level view. The agent should be able to recognize this pattern at multiple scales, not only at whatever single level the chart indicator happens to draw.

**The multi-timeframe noise trap.** Because each timeframe has its own level, a short timeframe can show what looks like real movement — e.g. price already reaching resistance on a 15-second chart — while the longer timeframe (e.g. 5-minute chart) shows no real net movement at all: price round-trips back to its original place. This is where people lose money — reacting to short-term wild swings as if they were real, tradeable moves, when the bigger-picture chart never actually moved. Candle stacking plus the sheet data together is what catches this: a short-timeframe move that isn't also confirmed by real stacking/velocity/volume on the longer timeframe is noise, not signal, and should be read as part of the no-trade zone.

## 2. The four confirming signals

No single one of these is sufficient alone — the pattern is only trusted when they line up together:

1. **Body stacking** — do candle bodies stack cleanly in one direction (real conviction), or is price just chopping (consolidation)? This is the visual tell for whether a rejection is trustworthy. Concretely: a long wick with little or no body follow-through at a level means price *reached* that level but had no power to continue through it — it's the classic fakeout most people get fooled by, since the wick alone looks dramatic even though nothing actually broke.

**Edge case (the reverse failure mode):** sometimes the chart read doesn't clearly show or explain a big wick, but the sheet data independently shows the price level actually went up — the numbers confirm a real move even when the visual read doesn't make it obvious. This is the mirror image of the wick-fakeout case above: there, the chart *overstates* what happened; here, it can *understate* it. Neither evidence stream is reliably sufficient alone in either direction, which is why both the chart-reasoning agent and the data-reasoning agent need to run independently and get cross-checked, rather than trusting either one on its own.
2. **Velocity** — how fast is the weak side moving into/through the level?
3. **Volume** — how much size is behind the move?
4. **Holding time** — dwell time *at* the level after reaching it (not time spent climbing to it). Zero holding time = no strength = confirms rejection. Consolidating/holding at the level without breaking also confirms weakness. Only a break *with* velocity and volume converts the read.

**Timing rule this implies:** the wick reaches a level first — that's the fast, leading move, and by itself it means nothing. The body follows more slowly afterward, if the move is real. Most people get fooled because they react to the wick the instant it touches a level; the correct sequence is to let the wick happen first and only enter once the body actually confirms — enter slowly, on the lagging confirmation, not the leading wick.

**The typical outcome:** most of the time, the body never reaches where the wick went — not even slowly. That's a clean no-trade read. Less often, the body does follow, but slowly — that's a cautious/reduced-size trade, not a full-conviction one. Only rarely does the body follow cleanly and confidently, which is the real, full-conviction setup. This gives the agent a genuine three-way outcome (no-trade / cautious trade / full trade) rather than a binary, consistent with no-trade being the expected default and clean setups being the rare exception.

## 3. Consolidation zone (risk filter)

Price often sits in a tight range where even a 15-minute candle body barely moves — only the wicks move, the body stays flat/compressed. This is a low-confidence, high-risk environment: a "rejection" seen inside consolidation is more likely noise than signal, because there's no clear directional context to confirm it against. This is one of the things the chart-reading side should specifically flag as a warning.

## 4. System architecture (final)

This is not a rule-following system — every component below is a **reasoning** component. Nothing here is "if X then Y" thresholds; each part is meant to weigh evidence and form a judgment, the way the underlying trade thesis itself is a judgment, not a formula.

### 4.1 Inputs (two live streams, continuously running)

- **Google Sheet stream** — live call and put price + volume data, fed by TradingView, already connected to Python on a VPS.
- **Chart stream** — the TradingView chart itself, read on a refresh cycle (discussed at 60 seconds). A narrowly-scoped LLM/vision step reads the chart image and extracts structured facts: support/resistance level(s), indicator readings, and candle body stacking. This is the LLM's *entire* role — pure extraction of what Python cannot derive from numbers alone. Playwright is the mechanism that connects Python to both the chart and the sheet on the VPS.

### 4.2 Two reasoning agents (parallel, independent)

Both agents are answering the same underlying question — *is this consolidation, real momentum, a rejection, or a break-and-reverse?* — from different evidence, at multiple timeframes (as short as 15 seconds up through the 15-minute/indicator view), because support/resistance is fractal and each timeframe has its own level.

**Chart-reasoning agent**
- Works from what the LLM extracted off the chart: support/resistance level, candle body stacking, indicator readings.
- Reasons about: is stacking clean and directional (conviction) or flat/overlapping (consolidation)? Is price dwelling at a level (holding time) or snapping away? Does a move look like a genuine break or a liquidity-trap fakeout?
- Should evaluate this at more than one timeframe, since a short-timeframe read can look meaningful while the longer timeframe shows no real movement (the multi-timeframe noise trap).

**Data-reasoning agent**
- Works from the live sheet numbers: call/put price, velocity, volume.
- Reasons about: what does velocity/volume look like right now — does it match a consolidation signature (flat, low conviction), a momentum signature (directional, real force), or a rejection signature (spike at a level, then reversal)?
- Tracks the call/put see-saw correlation directly — is one side's move being mirrored by the expected reaction on the other side?

### 4.3 The boss (reconciliation, not a rule engine)

The boss's job is a single reasoning question: **do the chart agent's read and the data agent's read describe the same pattern?**

- If both independently point to the same state (both bullish, both bearish, both consolidation, both confirming a break-and-reversal) → high confidence, issue that call.
- If they disagree, or either read is ambiguous → that disagreement is itself the signal. It does not get silently resolved or defaulted; it should be surfaced and, in the large majority of cases, resolves to a **no-trade call**, since no-trade is the expected default state, not the exception.
- The boss is not picking a winner between the two agents — it's checking whether the same underlying pattern shows up twice, from two independent forms of evidence.

### 4.4 Self-learning loop

Every time the boss reaches a conclusion — trade or no-trade — the system should log the inputs that led there (level type, velocity, volume, holding time, candle stacking read, which timeframe) alongside what actually happened afterward. Over time, this feedback lets both agents refine what a genuine consolidation/momentum/rejection/reversal signature actually looks like in practice, rather than relying on fixed thresholds set once and never revisited.

### 4.5 Live reasoning output

Rather than a binary alert, the system should narrate its read continuously in plain language as conditions evolve — what each agent is currently seeing, whether they agree, and why the current state is or isn't tradeable. This reasoning-made-visible output is itself part of the deliverable, not just an internal log.

---

## 5. Self-learning

Because one side's move causes a reaction on the other, and both call and put data are available, the agent should **observe and learn** these reactions over time rather than run on fixed thresholds forever. The outcome of any given reaction depends on: level (support/resistance), velocity, volume, and holding time. Logging these four inputs alongside what actually happened next (real rejection + fast move, vs. false signal) gives the agent a feedback loop to refine its judgment.

## 6. The synthesis: candle stacking + sheet data → no-trade zone

This is the connecting insight that ties sections 2 and 3 together:

- **Candle stacking** (from the chart) tells you what's *about* to happen — clean directional stacking = real conviction; flat/overlapping stacking = consolidation, nothing meaningful is happening.
- **Velocity, volume, and holding time** (from the sheet) confirm *whether* that stacking read is actually backed by real force behind the move.
- Put those together and the agent isn't just trying to call trades — its most valuable output may be correctly calling the **no-trade zone**: recognizing when candle stacking is unclear or contradicted by weak velocity/volume/holding-time, and explicitly saying "don't trade this," rather than only firing alerts when it sees a valid setup.

**This reframes what "the best agent" means:** it's not the one with the highest hit rate on trade calls — it's the one that's most reliable at identifying when conditions do *not* support a trade, since that's what keeps you out of the consolidation/liquidity-trap chop that erodes premium on 0DTE options. A false "no trade" call is far less costly than a false "trade" call.

**The two agents should each learn their own signature of the same question ("consolidation or real move?"), from different evidence:**

- **Visual agent (chart):** reads candle stacking directly — bodies compressed/close together = consolidation; bodies cleanly separated in one direction = real bullish/bearish momentum.
- **Data agent (sheet):** learns what velocity and volume look like *when candles are close together* (consolidation signature), versus what velocity and volume look like *when candles are actually moving bullish or bearish* (momentum signature).

Both agents are independently answering the same question from two different evidence types. Agreement between them is a much stronger signal than either alone — if the chart shows tight stacking but the data shows a velocity/volume spike that doesn't match, that disagreement itself is meaningful and should be surfaced, not silently resolved. Getting both sides built correctly is what makes the no-trade-zone call reliable.

**Core validation principle:** the pattern repeats consistently across both evidence types — it's the same underlying market behavior, just observed two different ways.

- Bullish/bearish candle stacking on the chart → the sheet data should show the matching bullish/bearish signature (velocity + volume in that direction)
- Consolidation zone on the chart → the sheet data should show the matching consolidation signature (flat/low velocity, no volume conviction)
- Rejection on the chart → the sheet data should show the matching rejection signature (velocity/volume spike right at the level, then reversal)
- **Break + reversal** — even when support actually breaks and price reverses, the same consistency applies: both the sheet data and the candle stacking should independently confirm that reversal (data shows the reversal's velocity/volume signature; candle bodies flip direction cleanly, not just a wick poke). This is arguably the trickiest moment to read correctly, since it's exactly where a fakeout could masquerade as a real reversal — so agreement between the two agents matters most here.

This is what makes the boss's "are they aligned?" check meaningful — it's not comparing two unrelated signals, it's checking whether two independent views of the *same* pattern actually agree. Agreement = high confidence. Disagreement = something is off, or it's a genuinely ambiguous/transitional moment that warrants a no-trade call rather than a forced decision.

## 7. Live reasoning / commentary

Design intent: this should not be a static rule-checker firing binary alerts ("if price > resistance, alert"). It should:

- Continuously track state at a level (holding, retesting, breaking) rather than checking single snapshots
- Distinguish genuine rejection from consolidation noise
- Recognize the *moment* of rejection as the actionable trigger, not just the eventual outcome
- Cross-check the chart-derived read against the sheet-derived read before committing to a call
- Learn from logged outcomes over time
- Narrate what it's seeing in plain language, live — reasoning made visible, not a black-box alert

## 8. Cost estimate (LLM chart-extraction only)

Using Claude Haiku 4.5 pricing ($1/M input tokens, $5/M output tokens) as an illustrative baseline, at a 60-second refresh during market hours (~6.5 hrs/day, ~22 trading days/month):

| Scope | Cost/call | Per trading day | Per month |
|---|---|---|---|
| Support/resistance only | ~$0.0018 | ~$0.70 | ~$15 |
| Full chart picture (levels + indicators + body stacking) | ~$0.005 | ~$1.95 | ~$43 |

**Key takeaways:**
- Cost is driven mainly by **call frequency**, not by how much is extracted per call — output tokens are cheap even when extracting more fields.
- Going from a 60s to a 15s refresh would roughly **4x** the cost, independent of scope.
- Image resolution matters — a full-resolution screenshot can cost 2–4x a cropped/downscaled one.
- Haiku (or an equivalent cheap vision model via Groq/Together) is likely sufficient, since chart extraction is a mechanical task, not one requiring frontier reasoning.
- Net: extracting the full picture instead of just support/resistance is a modest increase (tens of dollars/month), not a step-change — as long as the LLM stays scoped to extraction only, with reasoning kept in Python.

## 9. Infrastructure / integration notes

- Project repo: `github.com/la1ani/SPX_ACCEPTANCE_PLATFORM/tree/main/SPX_LLM_VISION_TRADER`
- Google Sheets + Python already running and connected on a VPS.
- Playwright will connect Python to the chart/Google Sheet on the VPS to supply Python (or the LLM step) with what it can't calculate on its own — namely support/resistance.
- AI API candidates considered for the extraction step: DeepSeek, Groq, Together.ai, OpenRouter, Claude Haiku — no final provider chosen yet.
- GitHub MCP: no first-party Anthropic-directory connector; available via a custom remote MCP (`https://api.githubcopilot.com/mcp/`) with OAuth, requires a paid plan.
- TradingView MCP: no official connector; a community bridge exists (Chrome DevTools Protocol-based) but may conflict with TradingView's ToS — Alpha Vantage and Crypto.com connectors are alternatives.

## 10. Open question from this discussion

You flagged that the architecture may have gotten more layered than necessary (chart-agent/data-agent/boss split, self-learning, live commentary) relative to the core thesis (support/resistance + rejection). The minimal version of the system is:

> LLM reads chart → gets support/resistance → Python tracks price against that level for velocity/volume/holding time → rejection or break → done.

Everything else in this document (two-agent/boss split, self-learning loop, live commentary, consolidation-zone filter as a separate module) is an extension on top of that minimal core — worth deciding which of these to build first vs. defer.
