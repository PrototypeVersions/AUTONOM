# AUTONOM
**An Experiment in Autonomous AI Trading**

**Two markets. Two paper portfolios. One question: can AI learn to trade?**

AUTONOM is an open, prospective paper-trading lab with independent $1,000 stock and $1,000 cryptocurrency portfolios. A mobile-friendly dashboard shows recorded reference prices, equity, passive benchmarks, position holdings, prospective decisions, and a visible event journal.

## What works, and what does not

- ✅ A complete static dashboard on GitHub Pages (once Pages deployment is enabled).
- ✅ A scheduled GitHub Actions market collector, with public daily bars and headline retrieval.
- ✅ A forward-only trading simulator. Decisions must exist **before** the eligible trade bar begins; first-seen time is recorded by the workflow, not trusted from metadata.
- ✅ Long-only budgets, explicit position limits, modeled fees/slippage, cash, per-portfolio positions, SPY/BTC passive baselines, and Git versioned journal.
- ✅ Standard-library tests; no market-data API key needed.
- ✅ Two recurring ChatGPT tasks research stocks and crypto independently and commit prospective decisions. The workflow records each accepted decision and handles simulated fills.

## Quick start

1. Under GitHub **Settings → Actions → General → Workflow permissions**, enable **Read and write permissions** for `GITHUB_TOKEN`. This allows the workflow to commit its updated data files.
2. Under **Settings → Pages**, choose **Deploy from a branch**, `main`, `/(root)`, and save. GitHub publishes at **https://prototypeversions.github.io/AUTONOM/**.
3. Open **Actions → AUTONOM market cycle → Run workflow** once to record the first real prices and create benchmark start dates. Thereafter its planned collection/intake times are 11:15, 13:00, 14:00 and 22:30 UTC on weekdays, plus 23:30 and 02:20 UTC daily. Pushes containing newly committed decisions also trigger intake. GitHub schedules are best-effort, not guaranteed to fire exactly on time.
4. To test a prospectively decided paper order, read [the decision protocol](docs/DECISION_PROTOCOL.md) and [the schema example](decisions/example.json); commit a new validated file into `decisions/inbox/`. The workflow records it as pending on its first run and can simulate it only using a future eligible daily bar.

## Research and decision cadence

- **Stock agent: 7:30 a.m. America/Chicago, Monday through Friday.** Review markets, earnings, economic releases, previous paper positions and risks. Submit at most one justified BUY, SELL or HOLD decision. The model can always remain in cash; it is not rewarded for excessive trading.
- **Crypto agent: 4:30 p.m. America/Chicago, every day.** Independently research digital assets, risk, current positions and Bitcoin benchmark, then submit at most one justified BUY, SELL or HOLD decision.
- **Weekend mornings:** No stock task is scheduled; the crypto task still operates each afternoon.
- **Collector:** GitHub Actions refreshes prices and headlines several times daily without invoking GPT. The models are not continuously running between scheduled task executions.
- **Strategy:** The agents read and maintain separate [stock](strategy/stocks.md) and [crypto](strategy/crypto.md) plans. Each new decision records the plan version and the evidence for its action.
- **Dashboard data:** The site reads the current public data files on main and falls back to the published snapshot if the live feed is unavailable.

Why two research cycles? Enough coverage to react to changing markets without turning the experiment into a high-frequency-churn test. The agent may decide to HOLD, and daily trade counts can be zero.

## Research integrity

Records are forward-only; no backfilled positions. The first benchmark quote is set at inception. Unavailable quotes and failed orders remain explicit. The platform is infrastructure for a future AI experiment—not evidence that any model has learned or beaten the market.

Public market reference data comes from Stooq or Yahoo Finance (stocks), Coinbase Exchange daily candles (crypto), and Google News RSS headlines. These endpoints are third-party and best-effort, subject to availability and provider terms.

**Never put brokerage credentials, personal financial details or private API tokens in this public repository.** No real-money trading functions are implemented.

See [decision protocol](docs/DECISION_PROTOCOL.md), [source code](scripts/market_cycle.py), and [automated tests](tests/test_protocol.py).
