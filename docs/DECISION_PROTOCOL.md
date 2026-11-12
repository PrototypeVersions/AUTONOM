# AUTONOM · Decision and execution protocol

**The market collector is NOT a GPT agent.** Running the workflow does not confer model access or create model decisions. No autonomous AI trade may be claimed unless the model actually submitted a recorded prospective order through an authenticated integration.

## Accounts and limits

Two independent forward-only paper accounts start at **$1,000 cash** each: `stocks` (U.S. equities) and `crypto` (selected supported spot coins). No real money, exchange accounts, leverage, short positions, borrowing or derivatives. Orders must have an amount in USD from $10 to $1,000. Each BUY may not bring per-asset exposure above 35% of the portfolio value at the simulated open. At most 10 simultaneous stock positions or 6 crypto positions. Fractional units are supported.

Estimated execution cost: 0.10% fee per fill plus 0.05% adverse price slippage. These are assumptions, not broker quotes. No guarantee that a trade could have executed at the simulated reference price or size.

## How to submit a prospective decision

Create a **new** JSON file in `decisions/inbox/<id>.json` matching the documented schema `decisions/example.json` (never put examples inside inbox). Each ID must be globally unique, 5–80 characters, letters, digits, underscores and hyphens; the file stem and JSON ID must match. `portfolio`: stocks/crypto. `action`: BUY/SELL/HOLD. BUY and SELL require `symbol` and `amount_usd`. HOLD requires no symbol. Required fields: `model`, `decision_at_utc` (timezone-aware ISO 8601 UTC), and a real forward-looking `thesis`. You can also add `risk_notes` and an array of source URLs.

The `model` field is the claimant's supplied text, **not an authenticated identity**. A filename or metadata that says GPT does not establish the decision came from GPT. No one should modify or backdate already recorded entries to make performance better.

## Strategy

Read [the stock plan](../strategy/stocks.md) or [the crypto plan](../strategy/crypto.md) before researching each cycle. File one decision per portfolio per run. Include the plan version and the concrete evidence for the decision. For a cash HOLD, record what would justify taking exposure and when to reassess. A strategy revision belongs in the matching plan and in the next decision's reasoning. Keep prior plan versions in Git and preserve all earlier decisions.

## First-seen time vs claimed decision time

The engine records its own first-seen UTC time during the GitHub Actions run. It does not use the author's claimed time to qualify a trade for earlier prices. A new decision is first recorded as *pending*.

A pending instruction can fill only when a **completed daily market bar that STARTED AFTER the engine first saw the decision** becomes available, using that new bar's open as a simulated reference execution price. The engine never fills an order at a bar available when the instruction was first seen. Scheduled runs may delay eligibility even when the decision file was committed earlier. A BUY requires opening marks for existing holdings from the same session as the order. Missing marks defer the order, and any order still unfilled seven calendar days after intake expires. No backfills.

Stock bars: completed U.S. regular sessions; daily OHLC from Stooq with Yahoo Finance fallback. Crypto: completed UTC calendar-day Coinbase Exchange USD candles. Market holidays, delayed runs, missing prices, API changes or provider outages may delay or prevent fills. Price-provider differences may make returns incomparable with a broker. This is paper trading only.

## Benchmarks and marks

SPY is the stock benchmark; BTC is the crypto benchmark. Each initializes from the first observed eligible closing bar after launch with a $1,000 notional. Historical equity marks use closing prices from the benchmark session for all held symbols. If any mark for that session is missing, the engine waits for matching data. The dashboard labels sources and timestamps. No prior historical prices are stitched into the forward performance record.

The files `data/events.json`, `data/state.json`, `data/history.json`, `data/market.json`, `data/status.json`, and `data/research.json` are versioned in Git. Event entries are logically append-only (past entries are retained) and Git commit history provides a change audit. This is not a cryptographically tamper-proof third-party ledger.

## What is (and isn't) automated

The GitHub Actions workflow updates public price bars, reads public RSS headlines, accepts committed decisions and calculates paper trades/marks. It requires no OpenAI API key. **A language model does not run inside GitHub Actions by itself.** Separate scheduled ChatGPT tasks perform the model research and submit decisions through the GitHub connection. The engine records which files it accepts and when. The model label within a file is self-reported.

## Interpret with care

Stock and cryptocurrency returns involve substantial risk. Paper fills omit spreads and market impact beyond the above simplified assumptions, price data may be imperfect, and free public data endpoints can fail. Benchmark-relative and risk-adjusted comparisons matter more than attractive isolated trades. No profitable edge is established by this platform.
